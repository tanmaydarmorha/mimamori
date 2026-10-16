"""Opening a case (from Scoring's alert), the seeded card, and assembling the `Case` view."""

from __future__ import annotations

import asyncio
import logging

from mimamori_common.models import Case, OpenCaseRequest, OpenCaseResponse

from . import card as cardlib
from .bank import FALLBACK_QUESTION_ID, load_bank, question_view
from .deps import Deps
from .errors import ApiProblem, not_found
from .investigation.agent import run_investigation

log = logging.getLogger("case_svc.cases")
_tasks: set[asyncio.Task] = set()


def case_view(deps: Deps, case_id: str) -> Case:
    doc = deps.store.case(case_id)
    card = deps.store.card(case_id)
    line = None
    if card and card["risk"]["pause_recommended"] and card["risk"].get("hold_line_id"):
        found = load_bank(deps.intel).hold_lines.get(card["risk"]["hold_line_id"])
        line = found and {"id": found["id"], "ja": found["ja"], "en": found["en"]}
    return Case.model_validate({**doc, "card": card, "hold_line": line})


async def open_case(deps: Deps, req: OpenCaseRequest) -> OpenCaseResponse:
    store = deps.store
    existing = store.find_by_transfer(req.transfer_id)
    if existing:  # POST /cases is idempotent per transfer
        return OpenCaseResponse(case_id=existing["case_id"], status=existing["status"])

    payee_account_id = None
    request = req.request.model_dump(mode="json")
    if request.get("payee") and request["payee"]["relation"] == "same_bank":
        try:
            transfer = await deps.core.get_transfer(req.transfer_id)
            payee_account_id = transfer.request.payee.account_id if transfer.request.payee else None
        except ApiProblem as err:
            log.warning("could not read transfer %s at open: %s", req.transfer_id, err.detail)

    async with store.lock("open-case"):
        existing = store.find_by_transfer(req.transfer_id)
        if existing:
            return OpenCaseResponse(case_id=existing["case_id"], status=existing["status"])
        case_id = store.next_case_id()
        case = {
            "case_id": case_id, "status": "open", "language": "ja", "customer_ref": req.customer_ref,
            "opened_at": req.opened_at.isoformat(), "amount_jpy": request["amount_jpy"], "risk_level": None,
            "account_id": req.account_id, "transfer_id": req.transfer_id, "request": request,
            "signals": [s.model_dump(mode="json") for s in req.signals], "transcript": [], "decisions": [],
            "hold": None, "call_id": None, "case_code": None, "contact_view": None, "verification_failed": False,
            "contact_suspected": None, "freeze_request": None,
        }
        state = cardlib.new_state(case_id, payee_account_id)
        # Seeded card: Scoring's signals are facts with their tool and field; the investigation re-checks them.
        cardlib.set_facts(state, [{"tool": s["tool"], "field": s["field"], "value": s["value"], "statement_en": s["statement_en"]}
                                  for s in case["signals"]])
        view = load_bank(deps.intel)
        first = view.questions.get(FALLBACK_QUESTION_ID)
        if first:
            payee = request.get("payee")
            state["next_question"] = question_view(first, payee, deps.settings)
            state["suggested_question_ids"].append(first["id"])
        card = cardlib.build_card(case, state, view, store.now())
        case["risk_level"] = card["risk"]["level"]
        store.save_case(case)
        store.save_state(case_id, state)
        store.save_card(card)
        store.emit(case_id, "case_opened", {"case_id": case_id, "transfer_id": req.transfer_id, "amount_jpy": case["amount_jpy"],
                                           "signals": case["signals"]})
        store.emit(case_id, "card_updated", {"card": card, "source": "seed"})
        store.audit(case_id, "case.opened", "scoring", "alert from pre-transaction check", transfer_id=req.transfer_id)

    if deps.svc.investigation_enabled:
        if deps.svc.investigation_inline:
            await run_investigation(deps, case_id)
        else:
            task = asyncio.create_task(run_investigation(deps, case_id))
            _tasks.add(task)
            task.add_done_callback(_tasks.discard)
    return OpenCaseResponse(case_id=case_id, status="open")


def require_case(deps: Deps, case_id: str) -> dict:
    try:
        return deps.store.case(case_id)
    except ApiProblem:
        raise not_found("case", case_id)
