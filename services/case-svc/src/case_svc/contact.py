"""The family-call side (build step 3): contact-suspected checks, the brief built **in code**, the case code,
`POST /calls`, and the outcome coming back. The conversation service and Gemini only ever see the brief.

The brief has no field for the balance, account numbers, the payee or other customers (the schema has
`additionalProperties: false`), and a field is present only if the customer's wishes allow disclosing it."""

from __future__ import annotations

import logging
import unicodedata
from datetime import datetime, timedelta

from mimamori_common.models import CallPolicy, CallRequest, ContactBrief, ContactOutcomeRequest

from . import card as cardlib
from .config import NEUTRAL_REFERENCE_EN, NEUTRAL_REFERENCE_JA
from .deps import Deps
from .errors import ApiProblem, conflict

log = logging.getLogger("case_svc.contact")


def _norm(text: str) -> str:
    return unicodedata.normalize("NFKC", text).replace(" ", "").replace("　", "")


def amount_band(amount_jpy: int) -> str:
    return "under_1m" if amount_jpy < 1_000_000 else "1m_to_5m" if amount_jpy <= 5_000_000 else "over_5m"


def reason_category(state: dict, case: dict) -> str:
    types = {i["type"] for i in state["indicators"]}
    if types & {"impersonated_official"}:
        return "call_from_someone_claiming_authority"
    if cardlib.fact_values(state).get("get_baseline.new_payee") is True:
        return "unfamiliar_payee"
    return "unusual_amount"


def build_brief(deps: Deps, case: dict, state: dict, wishes: dict, contact: dict, call_id: str, case_code: str) -> dict:
    """Built in code from the policy. Nothing here comes from the model, the card's facts or the bank records
    beyond the coarse values the policy allows."""
    allowed = set(wishes["disclosure"]["may_disclose"])
    values = {
        "transaction_paused": case["status"] == "paused",
        "amount_band": amount_band(case["amount_jpy"]),
        "reason_category": reason_category(state, case),
        "customer_at_branch": case["request"]["channel"] == "counter",
        "police_notified": bool(state.get("police_notified")),
    }
    disclosable: dict = {}
    for name in allowed:
        if name in ("transaction_paused", "customer_at_branch", "police_notified"):
            if values[name]:  # only true statements are disclosed; "not notified" is not worth saying
                disclosable[name] = True
        else:
            disclosable[name] = values[name]
    language = case.get("language", "ja")
    reference = (deps.svc.reference_en.get(case["customer_ref"], NEUTRAL_REFERENCE_EN) if language == "en"
                 else deps.svc.reference_ja.get(case["customer_ref"], NEUTRAL_REFERENCE_JA))
    brief = {
        "case_id": case["case_id"], "call_id": call_id, "language": language, "built_at": deps.store.now().isoformat(), "built_by": "code",
        "case_code": case_code,
        "branch": {"name_ja": deps.settings.branch_name_ja, "name_en": deps.settings.branch_name_en, "published_phone_e164": deps.settings.branch_published_phone_e164},
        "contact": {"contact_id": contact["contact_id"], "relationship": contact["relationship"],
                    "locked_phone_e164": contact["phone_e164"]},
        "customer_reference": reference,
        "disclosable": disclosable,
    }
    ContactBrief.model_validate(brief)  # schema check: additionalProperties false, patterns
    return brief


async def contact_suspected(deps: Deps, case: dict, state: dict, contact: dict) -> str | None:
    """Reasons not to call: number changed recently, contact linked to the payee, flagged in teller notes."""
    changed = contact.get("phone_changed_at")
    if changed and datetime.fromisoformat(changed) >= deps.store.now() - timedelta(days=deps.svc.contact_phone_change_days):
        return "contact_number_changed_recently"
    if state.get("payee_account_id"):
        try:
            acct = await deps.core.get_account(state["payee_account_id"])
            holder = await deps.core.get_customer(acct.customer_ref)
            names = {_norm(holder.display_name_ja), _norm(holder.display_name_kana), _norm(acct.holder_name_kana)}
            if _norm(contact["display_name"]) in names:
                return "contact_linked_to_payee"
        except ApiProblem as err:
            log.warning("payee link check skipped for %s: %s", case["case_id"], err.detail)
    for n in deps.store.notes_for(case["customer_ref"]):
        if "contact_flagged" in n.get("flags", []) and n.get("contact_id") in (None, contact["contact_id"]):
            return "contact_flagged_in_notes"
    return None


async def start_call(deps: Deps, case_id: str, actor: str, *, auto: bool) -> dict:
    """Steps 7a-7b. Returns the case doc. Sets `contact_suspected` (and makes no call) when the check says so."""
    store = deps.store
    async with store.lock(case_id):
        case, state = store.case(case_id), store.state(case_id)
        wishes = store.repo.get_active_wishes(case["customer_ref"])  # a frozen_pending_review version is never used (DA 12)
        reason = None
        contact = None
        if not wishes:
            reason = "no_wishes_on_file"
        elif not wishes["outbound_notice_consent"]:
            reason = "no_notice_consent"
        else:
            contact = min(wishes["trusted_contacts"], key=lambda c: c["priority"])
            reason = await contact_suspected(deps, case, state, contact)
        case["contact_suspected"] = reason
        if reason:
            store.save_case(case)
            store.audit(case_id, "contact.no_call", actor, reason)
            return case
        call_id = f"call-{case_id.rsplit('-', 1)[1]}-{state['contact_calls'] + 1}"
        code = deps.case_code()
        brief = build_brief(deps, case, state, wishes, contact, call_id, code)
        request = CallRequest(brief=ContactBrief.model_validate(brief),
                              policy=CallPolicy(may_disclose=list(wishes["disclosure"]["may_disclose"])))
        try:
            await deps.conversation.post_call(request)
        except ApiProblem as err:
            store.audit(case_id, "contact.call_failed", actor, err.detail, automatic=auto)
            if auto:  # the pause stands; the teller can retry with POST /contact-call
                log.warning("automatic call failed for %s: %s", case_id, err.detail)
                return case
            raise
        state["contact_calls"] += 1
        case.update(call_id=call_id, case_code=code, contact_view=None, verification_failed=False)
        store.save_case(case)
        store.save_state(case_id, state)
        store.audit(case_id, "contact.call_started", actor, "notice sent to the trusted contact", call_id=call_id,
                    contact_id=contact["contact_id"], disclosable=sorted(brief["disclosable"]), automatic=auto)
        store.emit(case_id, "contact_notice_sent", {"call_id": call_id})
        return case


async def start_call_after_pause(deps: Deps, case_id: str, actor: str) -> None:
    try:
        await start_call(deps, case_id, actor, auto=True)
    except Exception:  # never turns a successful pause into an error
        log.exception("automatic contact call failed for %s", case_id)


async def record_outcome(deps: Deps, case_id: str, req: ContactOutcomeRequest) -> dict:
    store = deps.store
    async with store.lock(case_id):
        case = store.case(case_id)
        if req.call_id != case.get("call_id"):
            raise conflict("call_mismatch", f"call {req.call_id} is not this case's current call")
        if req.outcome == "verification_failed":
            case["verification_failed"] = True
            store.save_case(case)
            store.audit(case_id, "contact.verification_failed", "conversation-svc", "caller number or case code did not match",
                        call_id=req.call_id)
            store.emit(case_id, "verification_failed", {"call_id": req.call_id})
            return case
        view = req.contact_view.model_dump(mode="json")
        if view["case_id"] != case_id or view["call_id"] != req.call_id:
            raise conflict("call_mismatch", "contact_view does not belong to this case and call")
        v = view["verification"]
        view["reached"] = bool(view["reached"] and v["caller_number_match"] and v["case_code_match"])  # only both checks count
        case["contact_view"] = view
        store.save_case(case)
        store.audit(case_id, "contact.outcome", "conversation-svc", "information from the trusted contact (not an instruction)",
                    call_id=req.call_id, reached=view["reached"], disclosed=view.get("disclosed", []))
        store.emit(case_id, "contact_outcome", {k: view.get(k) for k in
                                                ("call_id", "reached", "concerned", "coming_to_branch", "eta_minutes", "wants_callback_later", "nature")})
        return case
