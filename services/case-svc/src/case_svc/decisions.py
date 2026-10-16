"""Human decisions (DA 11): the teller pauses or releases, with a stated basis and rationale, and every
decision is audited with who and why. Code never decides and never blocks: a pause with a single evidence
source is allowed and logged as a warning."""

from __future__ import annotations

import logging
from datetime import datetime

from mimamori_common.models import (
    DecisionRecord, DecisionRequest, DecisionResponse, DismissIndicatorBody, Hold, HoldPatch, HoldRequest,
    HoldWindow, TransferPatch,
)

from . import card as cardlib
from .bank import load_bank
from .deps import Deps
from .errors import conflict, not_found

log = logging.getLogger("case_svc.decisions")


def wishes_apply(wishes: dict | None, case: dict, state: dict) -> tuple[bool, str]:
    """Does the customer's cooling-off clause cover this request? (wishes.cooling_off.applies_to / min_amount_jpy)"""
    if not wishes:
        return False, "no active advance wishes on file"
    co = wishes["cooling_off"]
    if not co["enabled"]:
        return False, "cooling-off is not enabled in the customer's wishes"
    req = case["request"]
    if req["amount_jpy"] < co["min_amount_jpy"]:
        return False, "amount is below the wishes' minimum"
    applies = set(co["applies_to"])
    if req["kind"] == "cash_withdrawal":
        ok = "cash_withdrawal" in applies
    else:
        new_payee = cardlib.fact_values(state).get("get_baseline.new_payee")  # unknown counts as new
        ok = "any_transfer" in applies or ("transfer_to_new_payee" in applies and new_payee is not False)
    return ok, "" if ok else "the request type is not covered by the customer's wishes"


def hold_terms(deps: Deps, basis: str, wishes: dict | None) -> tuple[HoldWindow, list[str]]:
    if basis == "advance_wishes":
        co = wishes["cooling_off"]
        window = HoldWindow(minimum_hours=co["minimum_hours"], extend_to_next_business_day_close=co["extend_to_next_business_day_close"],
                            cap_hours=co["cap_hours"])
        return window, list(co["override"])
    # Bank policy: a voluntary wait. No overrides, so the customer can end it with a plain release (contract: PATCH /holds).
    s = deps.svc
    return HoldWindow(minimum_hours=s.policy_minimum_hours, extend_to_next_business_day_close=s.policy_extend_to_close,
                      cap_hours=s.policy_cap_hours), []


def _next_decision_id(case: dict) -> str:
    return f"dec-{case['case_id'].split('case-')[1]}-{len(case['decisions']) + 1}"


async def decide(deps: Deps, case_id: str, body: DecisionRequest, via: str) -> DecisionResponse:
    store = deps.store
    async with store.lock(case_id):
        case, state = store.case(case_id), store.state(case_id)
        now = store.now()
        warnings: list[str] = []
        hold: Hold | None = None
        if body.action == "pause":
            if case["status"] != "open":
                raise conflict("case_not_open", f"case is {case['status']}")
            wishes = store.repo.get_active_wishes(case["customer_ref"])
            if body.basis == "advance_wishes":
                ok, why = wishes_apply(wishes, case, state)
                if not ok:
                    raise conflict("wishes_not_applicable", f"{why}; use basis bank_policy")
            window, overrides = hold_terms(deps, body.basis, wishes)
            if len(cardlib.evidence_families(state)) < 2:
                warnings.append("single_source_pause")
                log.warning("single_source_pause: case %s paused by %s with evidence from %s only",
                            case_id, body.teller_id, sorted(cardlib.evidence_families(state)))
            hold = await deps.core.place_hold(HoldRequest(
                account_id=case["account_id"], transfer_id=case["transfer_id"], case_id=case_id, placed_by=body.teller_id,
                window=window, overrides=overrides))
            case["hold"] = hold.model_dump(mode="json")
            case["status"] = "paused"
        else:
            hold = await _release(deps, case, body, now)
        record = DecisionRecord(
            decision_id=_next_decision_id(case), case_id=case_id, action=body.action, basis=body.basis,
            release_reason=body.release_reason, rationale=body.rationale, decided_by=body.teller_id,
            manager_id=body.manager_id, decided_at=now, warnings=warnings)
        case["decisions"].append(record.model_dump(mode="json"))
        card = store.card(case_id)
        store.save_case(case)
        store.audit(
            case_id, f"decision.{body.action}", body.teller_id, body.rationale, via=via, basis=body.basis,
            release_reason=body.release_reason, manager_id=body.manager_id, second_confirmed_by=body.second_confirmed_by,
            warnings=warnings, hold_id=hold.hold_id if hold else None, decision_id=record.decision_id,
            risk_level_at_decision=card["risk"]["level"] if card else None,
            pause_recommended_at_decision=card["risk"]["pause_recommended"] if card else None)
        store.emit(case_id, "decision_logged", record.model_dump(mode="json"))
        store.emit(case_id, "hold_placed" if body.action == "pause" else "hold_updated",
                   {"hold": hold.model_dump(mode="json") if hold else None})
    response = DecisionResponse(decision=record, status=case["status"], hold=hold, warnings=warnings)
    if body.action == "pause":
        from .contact import start_call_after_pause  # local: contact imports this module's helpers

        await start_call_after_pause(deps, case_id, body.teller_id)
    return response


async def _release(deps: Deps, case: dict, body: DecisionRequest, now: datetime) -> Hold | None:
    if case["status"] == "open":  # no hold: the teller cleared it
        if body.release_reason != "cleared_by_teller":
            raise conflict("no_active_hold", "there is no hold to override")
        await deps.core.patch_transfer(case["transfer_id"], TransferPatch(action="execute", actor=body.teller_id, reason=body.rationale))
        case["status"] = "released"
        return None
    if case["status"] != "paused" or not case["hold"]:
        raise conflict("case_not_paused", f"case is {case['status']}")
    held = Hold.model_validate(case["hold"])
    reason = body.release_reason
    if reason == "customer_override_after_contact_reached":
        cv = case.get("contact_view")
        if "after_contact_reached" not in held.overrides:
            raise conflict("override_not_allowed", "this hold was not placed with the contact-reached override")
        if not (cv and cv["reached"]):
            raise conflict("contact_not_reached", "the trusted contact has not been reached (number and case code verified)")
        patch = HoldPatch(action="override_after_contact_reached", reason=body.rationale, actor=body.teller_id, contact_reached=True)
    elif reason == "manager_review_second_confirmation":
        if "after_manager_review_and_second_confirmation" not in held.overrides:
            raise conflict("override_not_allowed", "this hold was not placed with the manager-review override")
        if body.second_confirmed_by in (body.manager_id, held.placed_by):
            raise conflict("second_confirmation_invalid", "the second confirmer must differ from the manager and from whoever placed the hold")
        patch = HoldPatch(action="override_after_manager_review", reason=body.rationale, actor=body.teller_id,
                          manager_id=body.manager_id, second_confirmed_by=body.second_confirmed_by)
    else:  # cleared_by_teller: a plain release, allowed before ends_at only for a bank-policy hold (no overrides)
        if held.overrides and now < held.ends_at:
            raise conflict("hold_active", f"a wishes-based hold ends at {held.ends_at.isoformat()}; use an override to end it early")
        patch = HoldPatch(action="release", reason=body.rationale, actor=body.teller_id)
    hold = await deps.core.patch_hold(held.hold_id, patch)
    case["hold"] = hold.model_dump(mode="json")
    case["status"] = "released"
    return hold


async def dismiss_indicator(deps: Deps, case_id: str, claim_id: str, body: DismissIndicatorBody, via: str) -> None:
    """The only way a verified indicator leaves the card (accumulation rule). Audited with who and why."""
    store = deps.store
    async with store.lock(case_id):
        case, state = store.case(case_id), store.state(case_id)
        ind = next((i for i in state["indicators"] if i["id"] == claim_id), None)
        if ind is None:
            raise not_found("indicator claim", claim_id)
        state["indicators"] = [i for i in state["indicators"] if i["id"] != claim_id]
        state["dismissed"].append({"claim_id": claim_id, "type": ind["type"], "quote": ind["quote"], "by": body.teller_id,
                                   "reason": body.reason, "at": store.now().isoformat()})
        card = cardlib.build_card(case, state, load_bank(deps.intel), store.now())
        case["risk_level"] = card["risk"]["level"]
        store.save_case(case)
        store.save_state(case_id, state)
        store.save_card(card)
        store.audit(case_id, "indicator.dismissed", body.teller_id, body.reason, via=via, claim_id=claim_id,
                    indicator=ind["type"], turn_id=ind["turn_id"])
        store.emit(case_id, "card_updated", {"card": card, "source": "dismissal"})
