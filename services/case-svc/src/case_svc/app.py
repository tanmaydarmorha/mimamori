"""FastAPI app: routes for docs/architecture/api-contracts.md (case-svc rows) plus a few small additions
listed in the README (`notes`, `police-notified`, SSE `follow=false`)."""

from __future__ import annotations

import asyncio
import json
import logging
from contextlib import asynccontextmanager
from typing import Literal

from fastapi import Request, WebSocket, WebSocketDisconnect
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, ConfigDict, Field

from mimamori_common.models import (
    AdvanceWishes, ApiError, Case, SetLanguageRequest, CaseEvent, CaseSummary, ContactOutcomeRequest, DecisionRequest, DecisionResponse,
    DismissIndicatorBody, FreezeDecisionBody, FreezeDecisionResponse, FreezeRequest, FreezeRequestBody, OpenCaseRequest,
    OpenCaseResponse, OutreachItem, Playbook, PlaybookPatch, PoliceSummaryRequest, PoliceSummaryResponse, TurnRequest, TurnResponse,
    WishesChangeResponse,
)
from mimamori_common.speech import CloudSttV2, TypedInput
from mimamori_common.web import caller_role, create_app, configure_logging

from . import analyst, contact, copilot, decisions, police
from .cases import case_view, open_case
from .deps import Deps, build_deps
from .errors import ApiProblem, conflict

log = logging.getLogger("case_svc")


class NoteBody(BaseModel):
    """`POST /cases/{id}/notes` (addition): a teller note about the customer; `contact_flagged` feeds the contact check."""

    model_config = ConfigDict(extra="forbid")
    teller_id: str
    text: str = Field(min_length=1)
    flags: list[Literal["contact_flagged"]] = []
    contact_id: str | None = None


class PoliceNotifiedBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    teller_id: str


def _caller(request: Request, *, analyst_only: bool = False) -> str:
    try:
        role, user = caller_role(request.headers)
    except ValueError as err:
        raise ApiProblem(403, "forbidden", str(err))
    if analyst_only and role != "analyst":
        raise ApiProblem(403, "forbidden", "analyst role required")
    return user


def seed_local(deps: Deps) -> None:
    from mimamori_common.seed import load_all

    load_all(deps.settings)


def create_case_app(deps: Deps | None = None):
    deps = deps or build_deps()

    @asynccontextmanager
    async def lifespan(_app):
        if deps.svc.seed_on_start and deps.settings.store_backend == "memory":
            seed_local(deps)  # local mode: the in-memory stores start empty
        yield

    configure_logging("case_svc")
    app = create_app("case-svc", deps.settings, lifespan=lifespan)
    app.state.deps = deps
    store = deps.store

    @app.exception_handler(ApiProblem)
    async def _problem(_req, exc: ApiProblem):
        return JSONResponse(ApiError(error=exc.error, detail=exc.detail).model_dump(), status_code=exc.status)

    @app.exception_handler(RequestValidationError)
    async def _invalid(_req, exc: RequestValidationError):
        return JSONResponse(ApiError(error="validation_error", detail=str(exc.errors())[:500]).model_dump(), status_code=422)

    # ---------------------------------------------------------------------------------------- cases

    @app.post("/cases", response_model=OpenCaseResponse, tags=["cases"])
    async def post_case(body: OpenCaseRequest):
        return await open_case(deps, body)

    @app.get("/cases", response_model=list[CaseSummary], tags=["cases"])
    async def list_cases(status: str | None = None):
        return [CaseSummary.model_validate({k: c[k] for k in CaseSummary.model_fields if c.get(k) is not None}) for c in store.repo.list_cases(status)]

    @app.get("/cases/{case_id}", response_model=Case, tags=["cases"])
    async def get_case(case_id: str):
        return case_view(deps, case_id)

    @app.get("/cases/{case_id}/events", tags=["cases"])
    async def case_events(case_id: str, request: Request, after: int | None = None, follow: bool = True):
        """SSE. `event:` = type, `id:` = seq, `data:` = CaseEvent JSON. Replays after `?after=` or `Last-Event-ID`, then
        streams. `follow=false` closes after the replay (tests, curl)."""
        store.case(case_id)
        if after is None:
            after = int(request.headers.get("last-event-id") or 0)

        def frame(e: dict) -> str:
            ev = CaseEvent.model_validate(e)
            return f"id: {ev.seq}\nevent: {ev.type}\ndata: {ev.model_dump_json()}\n\n"

        async def gen():
            queue = store.hub.subscribe(case_id) if follow else None  # subscribe first so nothing falls in a gap
            try:
                last = after
                for e in store.repo.list_events(case_id, after):
                    yield frame(e)
                    last = e["seq"]
                while queue is not None:
                    try:
                        e = await asyncio.wait_for(queue.get(), 15)
                    except asyncio.TimeoutError:
                        yield ": keepalive\n\n"
                        continue
                    if e["seq"] > last:
                        yield frame(e)
                        last = e["seq"]
            finally:
                if queue is not None:
                    store.hub.unsubscribe(case_id, queue)

        return StreamingResponse(gen(), media_type="text/event-stream", headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})

    @app.post("/cases/{case_id}/turns", response_model=TurnResponse, tags=["copilot"])
    async def post_turn(case_id: str, body: TurnRequest):
        store.case(case_id)
        if body.speaker == "teller":
            turn = await copilot.teller_turn(deps, case_id, body.text)
            return TurnResponse(turn_id=turn["turn_id"], card=None)
        turn, card = await copilot.customer_turn(deps, case_id, body.text)
        return TurnResponse(turn_id=turn["turn_id"], card=card)

    @app.websocket("/cases/{case_id}/audio")
    async def audio(ws: WebSocket, case_id: str):
        try:
            store.case(case_id)
        except ApiProblem:
            await ws.close(code=4404)
            return
        await ws.accept()
        if deps.settings.speech_backend == "typed":
            stt = TypedInput()
        else:  # LINEAR16 16 kHz, 2 interleaved channels: 0 customer microphone, 1 teller
            stt = CloudSttV2(deps.settings.project_id or "", deps.settings.region, deps.settings.stt_model, deps.settings.stt_language)

        async def frames():
            while True:
                try:
                    msg = await ws.receive()
                except WebSocketDisconnect:
                    return
                if msg["type"] == "websocket.disconnect":
                    return
                data = msg.get("bytes") if msg.get("bytes") is not None else (msg.get("text") or "").encode()
                yield data

        try:
            async for result in stt.transcribe_stream(frames()):
                if not result.is_final:
                    await ws.send_json({"type": "transcript", "turn_id": None, "speaker": result.channel, "text": result.text, "is_final": False})
                    continue
                try:
                    if result.channel == "teller":
                        turn = await copilot.teller_turn(deps, case_id, result.text)
                    else:
                        turn, _card = await copilot.customer_turn(deps, case_id, result.text)  # the card goes out over SSE
                    await ws.send_json({"type": "transcript", "turn_id": turn["turn_id"], "speaker": result.channel,
                                        "text": result.text, "is_final": True})
                except ApiProblem as err:
                    await ws.send_json({"type": "error", "error": err.error, "detail": err.detail})
        except WebSocketDisconnect:
            pass

    @app.post("/cases/{case_id}/decision", response_model=DecisionResponse, tags=["decisions"])
    async def post_decision(case_id: str, body: DecisionRequest, request: Request):
        return await decisions.decide(deps, case_id, body, _caller(request))

    @app.post("/cases/{case_id}/claims/{claim_id}/dismiss", response_model=Case, tags=["decisions"])
    async def dismiss(case_id: str, claim_id: str, body: DismissIndicatorBody, request: Request):
        await decisions.dismiss_indicator(deps, case_id, claim_id, body, _caller(request))
        return case_view(deps, case_id)

    @app.post("/cases/{case_id}/police-summary", response_model=PoliceSummaryResponse, tags=["decisions"])
    async def police_summary(case_id: str, body: PoliceSummaryRequest, request: Request):
        store.case(case_id)
        return await police.issue_summary(deps, case_id, body, _caller(request))

    @app.patch("/cases/{case_id}/language", response_model=Case, tags=["cases"])
    async def set_language(case_id: str, body: SetLanguageRequest, request: Request):
        """Addition: the teller picks the case's conversation language (ja | en) before the first turn; it is locked after."""
        async with store.lock(case_id):
            case = store.case(case_id)
            if case["transcript"]:
                raise conflict("language_locked", "the conversation language can't change once the case has a turn")
            previous = case.get("language", "ja")
            case["language"] = body.language
            store.save_case(case)
            store.audit(case_id, "case.language_set", body.actor, f"language {previous} -> {body.language}", via=_caller(request),
                        language=body.language)
        return case_view(deps, case_id)

    @app.post("/cases/{case_id}/police-notified", response_model=Case, tags=["decisions"])
    async def police_notified(case_id: str, body: PoliceNotifiedBody, request: Request):
        """Addition: the teller records that the police were notified (may be disclosed to the contact if the wishes allow)."""
        async with store.lock(case_id):
            state = store.state(case_id)
            state["police_notified"] = True
            store.save_state(case_id, state)
            store.audit(case_id, "police.notified", body.teller_id, "teller notified the police", via=_caller(request))
        return case_view(deps, case_id)

    @app.post("/cases/{case_id}/notes", tags=["decisions"], status_code=201)
    async def add_note(case_id: str, body: NoteBody, request: Request):
        case = store.case(case_id)
        n = len(store.notes_for(case["customer_ref"])) + 1
        note = {"note_id": f"note-{case['customer_ref']}-{n}", "customer_ref": case["customer_ref"], "case_id": case_id,
                "at": store.now().isoformat(), **body.model_dump()}
        store.repo.store.set("teller_notes", note["note_id"], note)
        store.audit(case_id, "note.added", body.teller_id, body.text, via=_caller(request), flags=body.flags)
        return {"note_id": note["note_id"]}

    @app.get("/cases/{case_id}/outreach", response_model=list[OutreachItem], tags=["analyst"])
    async def outreach(case_id: str):
        """The other payers to the frozen account; empty until a freeze is approved."""
        store.case(case_id)
        return store.state(case_id).get("outreach", [])

    @app.post("/cases/{case_id}/contact-call", response_model=Case, tags=["contact"])
    async def contact_call(case_id: str, request: Request):
        store.case(case_id)
        await contact.start_call(deps, case_id, _caller(request), auto=False)
        return case_view(deps, case_id)

    @app.post("/cases/{case_id}/contact-outcome", response_model=Case, tags=["contact"])
    async def contact_outcome(case_id: str, body: ContactOutcomeRequest):
        await contact.record_outcome(deps, case_id, body)
        return case_view(deps, case_id)

    @app.get("/cases/{case_id}/audit", tags=["audit"])
    async def get_audit(case_id: str):
        store.case(case_id)
        return store.repo.list_audit(case_id)

    # ---------------------------------------------------------------------------------------- analyst

    @app.post("/cases/{case_id}/freeze-request", response_model=FreezeRequest, tags=["analyst"])
    async def freeze_request(case_id: str, body: FreezeRequestBody, request: Request):
        store.case(case_id)
        return await analyst.request_freeze(deps, case_id, body, _caller(request))

    @app.get("/freeze-requests", response_model=list[FreezeRequest], tags=["analyst"])
    async def list_freeze_requests(request: Request, status: str | None = None):
        _caller(request, analyst_only=True)
        return store.repo.list_freeze_requests(status)

    @app.post("/cases/{case_id}/freeze-decision", response_model=FreezeDecisionResponse, tags=["analyst"])
    async def freeze_decision(case_id: str, body: FreezeDecisionBody, request: Request):
        user = _caller(request, analyst_only=True)
        store.case(case_id)
        return await analyst.decide_freeze(deps, case_id, body, user)

    @app.get("/playbooks", response_model=list[Playbook], tags=["analyst"])
    async def list_playbooks(status: str | None = None):
        return deps.intel.list_playbooks(status)

    @app.patch("/playbooks/{playbook_id}", response_model=Playbook, tags=["analyst"])
    async def patch_playbook(playbook_id: str, body: PlaybookPatch, request: Request):
        return analyst.patch_playbook(deps, playbook_id, body, _caller(request, analyst_only=True))

    @app.put("/customers/{customer_ref}/wishes", response_model=WishesChangeResponse, tags=["wishes"])
    async def put_wishes(customer_ref: str, body: AdvanceWishes, request: Request):
        return analyst.put_wishes(deps, customer_ref, body, _caller(request))

    return app
