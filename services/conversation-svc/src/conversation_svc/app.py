"""FastAPI app: POST /calls, GET /notices, WS /phone (docs/architecture/api-contracts.md).

No case-db access: the only input about a case is `CallRequest`; the only output is the outcome
posted to case-svc. State lives in memory.
"""

from __future__ import annotations

import asyncio
import base64
import logging
import os
from dataclasses import dataclass

from fastapi import HTTPException, Query, WebSocket
from mimamori_common.config import Settings
from mimamori_common.llm import ModelClient, get_general_client
from mimamori_common.models import (
    PHONE_MENU_RETURN_CALL, CallRequest, CallResponse, ContactOutcomeRequest, ContactView, Notice,
    PhoneCallback, PhoneEnded, PhoneHangup, PhoneSay, PhoneTurn, PhoneVerification,
)
from mimamori_common.models.api import PhoneClientMessage
from mimamori_common.speech import SpeechToText, TextToSpeech, get_stt, get_tts
from mimamori_common.web import configure_logging, create_app
from pydantic import TypeAdapter, ValidationError

from .agent import TurnAgent
from .calls import CallRecord, CallStore
from .case_client import CaseSvcClient, OutcomeSink
from .classifier import Classifier
from .fixed_text import NEUTRAL_REFERENCE_EN, REFERENCE_EN_FOR_JA, NOTICE_TEMPLATE_EN, format_phone_national, text_for
from .outgoing_check import amount_problems, amount_problems_en
from .templates import TemplateBook
from .verify import codes_match, normalise_e164, numbers_match

log = logging.getLogger("conversation_svc")
SERVICE = "conversation-svc"
_client_message = TypeAdapter(PhoneClientMessage)


@dataclass
class Tunables:
    model_timeout_s: float = 15.0
    max_turns: int = 20
    max_failed_attempts: int = 3
    max_utterance_chars: int = 500

    @classmethod
    def from_env(cls) -> "Tunables":
        return cls(model_timeout_s=float(os.getenv("CONVERSATION_MODEL_TIMEOUT_S", cls.model_timeout_s)),
                   max_turns=int(os.getenv("CONVERSATION_MAX_TURNS", cls.max_turns)),
                   max_failed_attempts=int(os.getenv("CONVERSATION_MAX_FAILED_ATTEMPTS", cls.max_failed_attempts)))


def build_notice_text(request: CallRequest) -> tuple[str, tuple[str, ...], str | None]:
    """(text in the case language, literals allowed past the digit check, English gloss for a `ja` notice)."""
    brief = request.brief
    phone = format_phone_national(brief.branch.published_phone_e164)
    if brief.language.value == "en":
        branch = brief.branch.name_en or brief.branch.name_ja
        text = text_for("en").notice_template.format(branch=branch, customer_reference=brief.customer_reference,
                                                      published_phone=phone, case_code=brief.case_code)
        return text, (branch, brief.customer_reference, phone, brief.case_code), None
    text = text_for("ja").notice_template.format(branch=brief.branch.name_ja, customer_reference=brief.customer_reference,
                                                  published_phone=phone, case_code=brief.case_code)
    gloss = NOTICE_TEMPLATE_EN.format(branch=brief.branch.name_en or brief.branch.name_ja,
                                      customer_reference=REFERENCE_EN_FOR_JA.get(brief.customer_reference, NEUTRAL_REFERENCE_EN),
                                      published_phone=phone, case_code=brief.case_code)
    return text, (brief.branch.name_ja, brief.customer_reference, phone, brief.case_code), gloss


def build_contact_view(call: CallRecord, now) -> ContactView:
    s = call.signals
    return ContactView.model_validate({
        "case_id": call.request.brief.case_id, "call_id": call.call_id, "nature": "information",
        "verification": {"caller_number_match": True, "case_code_match": True}, "reached": True,
        "concerned": s.get("concerned"), "coming_to_branch": s.get("coming_to_branch"),
        "eta_minutes": s.get("eta_minutes"), "wants_callback_later": s.get("wants_callback_later"),
        "disclosed": list(dict.fromkeys(call.disclosed)), "recorded_at": now,
    })


def create_conversation_app(settings: Settings | None = None, *, model: ModelClient | None = None,
                            stt: SpeechToText | None = None, tts: TextToSpeech | None = None,
                            outcome_sink: OutcomeSink | None = None, store: CallStore | None = None,
                            tunables: Tunables | None = None):
    settings = settings or Settings.from_env()
    tunables = tunables or Tunables.from_env()
    store = store or CallStore()
    tts_by_lang = {lang: tts or get_tts(settings, lang) for lang in ('ja', 'en')}
    stt_by_lang = {lang: stt or get_stt(settings, language=lang) for lang in ('ja', 'en')}
    sink = outcome_sink or CaseSvcClient(settings.case_svc_url)
    agent = TurnAgent(Classifier(model or get_general_client(settings), tunables.model_timeout_s),
                      TemplateBook.load(), tunables.max_utterance_chars)

    configure_logging("conversation_svc")
    app = create_app(SERVICE, settings)
    app.state.store, app.state.agent, app.state.tts = store, agent, tts_by_lang

    async def speak_payload(text: str, language: str) -> str | None:
        try:
            audio = await tts_by_lang[language].synthesize(text)
        except Exception as err:  # the text still goes out; the phone shows it
            log.warning("tts failed: %s", type(err).__name__)
            return None
        return base64.b64encode(audio).decode() if audio else None

    @app.post("/calls", response_model=CallResponse, tags=["calls"])
    async def post_calls(request: CallRequest) -> CallResponse:
        call_id = request.brief.call_id
        existing = store.get(call_id)
        if existing is not None:
            if existing.request != request:
                raise HTTPException(409, f"call {call_id} already exists with a different brief")
            return CallResponse(call_id=call_id, status="notice_sent", notice_text_ja=existing.notice.text)
        text, literals, gloss = build_notice_text(request)
        language = request.brief.language.value
        if (amount_problems_en if language == "en" else amount_problems)(text, literals):  # unreachable unless the notice constant is edited badly
            raise HTTPException(422, "notice failed the rule check")
        notice = Notice(call_id=call_id, to_phone_e164=normalise_e164(request.brief.contact.locked_phone_e164),
                        sent_at=settings.now(), text=text, language=language, gloss_en=gloss,
                        published_phone_e164=request.brief.branch.published_phone_e164,
                        case_code=request.brief.case_code, audio_b64=await speak_payload(text, language))
        store.add(CallRecord(request=request, notice=notice))
        log.info("notice sent call=%s", call_id)
        return CallResponse(call_id=call_id, status="notice_sent", notice_text_ja=text)

    @app.get("/notices", response_model=list[Notice], tags=["calls"])
    async def get_notices(to: str = Query(description="E.164 number of the simulated phone")) -> list[Notice]:
        return store.notices_for(to)

    async def report(call: CallRecord, outcome: str) -> None:
        if call.outcome_sent:
            return
        call.outcome_sent = True
        body = (ContactOutcomeRequest(call_id=call.call_id, outcome="contact_view",
                                      contact_view=build_contact_view(call, settings.now()))
                if outcome == "contact_view" else
                ContactOutcomeRequest(call_id=call.call_id, outcome="verification_failed"))
        if not await sink.post_outcome(call.request.brief.case_id, body):
            log.error("could not deliver %s for call %s to case-svc", outcome, call.call_id)

    async def send(ws: WebSocket, message) -> bool:
        try:
            await ws.send_text(message.model_dump_json(exclude_none=True))
            return True
        except Exception:
            return False

    async def say(ws: WebSocket, text: str, intent: str, language: str, gloss: str | None = None) -> None:
        await send(ws, PhoneSay(text=text, language=language, gloss_en=gloss if language == "ja" else None,
                                audio_b64=await speak_payload(text, language), template_intent=intent))

    @app.websocket("/phone")
    async def phone(ws: WebSocket) -> None:
        await ws.accept()
        try:
            first = _client_message.validate_json(await ws.receive_text())
        except (ValidationError, ValueError, RuntimeError):
            await ws.close(code=1003)
            return
        if not isinstance(first, PhoneCallback):
            await ws.close(code=1003)
            return

        call = store.find_for_callback(first.caller_number, first.case_code)
        # Evaluate every check; the reply never says which one failed (DA 5).
        number_ok = bool(call) and numbers_match(first.caller_number, call.request.brief.contact.locked_phone_e164)
        code_ok = bool(call) and codes_match(first.case_code, call.request.brief.case_code)
        menu_ok = first.menu_choice == PHONE_MENU_RETURN_CALL
        if not (call and number_ok and code_ok and menu_ok and call.state == "notice_sent"):
            if call:
                call.failed_attempts += 1
                if call.failed_attempts >= tunables.max_failed_attempts:
                    call.state = "locked"
                call.outcome_sent = False
                await report(call, "verification_failed")
            await send(ws, PhoneVerification(ok=False))
            await send(ws, PhoneEnded(reason="verification_failed"))
            await ws.close()
            return

        call.state, call.started_at = "in_progress", settings.now()
        await send(ws, PhoneVerification(ok=True))
        language = call.request.brief.language.value
        await say(ws, text_for(language).opening, "opening", language, text_for("en").opening)

        events: asyncio.Queue = asyncio.Queue()
        audio_q: asyncio.Queue = asyncio.Queue()
        tasks: list[asyncio.Task] = []

        async def reader() -> None:
            try:
                while True:
                    frame = await ws.receive()
                    if frame["type"] == "websocket.disconnect":
                        break
                    if frame.get("bytes") is not None:
                        await audio_q.put(frame["bytes"])
                        if len(tasks) < 2:
                            tasks.append(asyncio.create_task(stt_pump()))
                        continue
                    try:
                        msg = _client_message.validate_json(frame.get("text") or "")
                    except (ValidationError, ValueError):
                        continue
                    if isinstance(msg, PhoneTurn) and msg.text:
                        await events.put(("utterance", msg.text))
                    elif isinstance(msg, PhoneHangup):
                        break
            except Exception:
                pass
            await events.put(("hangup", None))

        async def audio_iter():
            while (chunk := await audio_q.get()) is not None:
                yield chunk

        async def stt_pump() -> None:
            try:
                async for result in stt_by_lang[language].transcribe_stream(audio_iter()):
                    if result.is_final and result.channel == "customer" and result.text.strip():
                        await events.put(("utterance", result.text))
            except Exception as err:
                log.warning("stt failed: %s", type(err).__name__)

        tasks.append(asyncio.create_task(reader()))
        ended_reason = "hangup"
        try:
            while True:
                kind, payload = await events.get()
                if kind == "hangup":
                    break
                call.turns += 1
                reply = await agent.respond(call.request, payload)
                call.signals.update(reply.signals)
                call.disclosed.extend(reply.disclosed)
                call.intents.append(reply.intent)
                await say(ws, reply.text, reply.intent, language, reply.gloss_en)
                if reply.intent == "coming_to_branch" or call.turns >= tunables.max_turns:
                    ended_reason = "completed"
                    break
        finally:
            for t in tasks:
                t.cancel()
            call.state = "ended"
            await report(call, "contact_view")
            await send(ws, PhoneEnded(reason=ended_reason))
            try:
                await ws.close()
            except Exception:
                pass

    return app
