"""Analyst side: freeze requests and decisions (CR 21), playbook approval, and the wishes freeze (DA 12)."""

from __future__ import annotations

import logging

from mimamori_common.models import (
    AdvanceWishes, FreezeBody, FreezeDecisionBody, FreezeDecisionResponse, FreezeRequest, FreezeRequestBody,
    OutreachItem, Playbook, PlaybookPatch, WishesChangeResponse,
)

from .casestore import OPEN_STATUSES
from .deps import Deps
from .errors import ApiProblem, conflict, not_found

log = logging.getLogger("case_svc.analyst")


async def _payee_account(deps: Deps, case: dict, state: dict) -> str:
    if state.get("payee_account_id"):
        return state["payee_account_id"]
    payee = case["request"].get("payee")
    if not payee or payee["relation"] != "same_bank":
        raise conflict("payee_not_same_bank", "only a same-bank account can be frozen by the bank")
    transfer = await deps.core.get_transfer(case["transfer_id"])
    if not (transfer.request.payee and transfer.request.payee.account_id):
        raise conflict("payee_account_unknown", "the transfer carries no payee account")
    state["payee_account_id"] = transfer.request.payee.account_id
    return state["payee_account_id"]


async def request_freeze(deps: Deps, case_id: str, body: FreezeRequestBody, via: str) -> FreezeRequest:
    store = deps.store
    async with store.lock(case_id):
        case, state = store.case(case_id), store.state(case_id)
        current = case.get("freeze_request")
        if current and current["status"] == "pending":
            raise conflict("freeze_pending", "a freeze request for this case is already pending")
        account_id = await _payee_account(deps, case, state)
        n = len(store.repo.list_freeze_requests()) + 1
        fr = FreezeRequest(freeze_id=f"frz-{case_id.split('case-')[1]}-{n}", case_id=case_id, account_id=account_id,
                           requested_by=body.requested_by, reason=body.reason, requested_at=store.now(), status="pending")
        doc = fr.model_dump(mode="json")
        store.repo.put_freeze_request(doc)
        case["freeze_request"] = doc
        store.save_case(case)
        store.save_state(case_id, state)
        store.audit(case_id, "freeze.requested", body.requested_by, body.reason, via=via, freeze_id=fr.freeze_id, account_id=account_id)
        store.emit(case_id, "freeze_requested", {"freeze_id": fr.freeze_id, "account_id": account_id})
        return fr


async def decide_freeze(deps: Deps, case_id: str, body: FreezeDecisionBody, via: str) -> FreezeDecisionResponse:
    store = deps.store
    async with store.lock(case_id):
        case, state = store.case(case_id), store.state(case_id)
        doc = case.get("freeze_request")
        if not doc:
            raise not_found("freeze request for case", case_id)
        if doc["status"] != "pending":
            raise conflict("freeze_already_decided", f"freeze request is {doc['status']}")
        now = store.now()
        freeze = None
        outreach: list[OutreachItem] = []
        if body.decision == "approve":
            freeze = await deps.core.freeze(FreezeBody(account_id=doc["account_id"], case_id=case_id, approved_by=body.analyst_id,
                                                       rationale=body.rationale))
            payers = await deps.core.payers(doc["account_id"], days=7)
            outreach = [OutreachItem(customer_ref=p.customer_ref, display_name_ja=p.display_name_ja, account_id=p.account_id,
                                     last_paid_at=p.last_paid_at, total_jpy=p.total_jpy)
                        for p in payers.payers if p.customer_ref != case["customer_ref"]]
        doc.update(status="approved" if body.decision == "approve" else "rejected", decided_by=body.analyst_id,
                   decided_at=now.isoformat(), decision_rationale=body.rationale)
        store.repo.put_freeze_request(doc)
        case["freeze_request"] = doc
        store.save_case(case)
        state["outreach"] = [o.model_dump(mode="json") for o in outreach]
        store.save_state(case_id, state)
        store.audit(case_id, f"freeze.{doc['status']}", body.analyst_id, body.rationale, via=via, freeze_id=doc["freeze_id"],
                    account_id=doc["account_id"], outreach_count=len(outreach))
        store.emit(case_id, "freeze_decided", {"freeze_id": doc["freeze_id"], "status": doc["status"]})
        if body.decision == "approve":
            store.emit(case_id, "outreach_ready", {"count": len(outreach), "outreach": [o.model_dump(mode="json") for o in outreach]})
        return FreezeDecisionResponse(freeze_request=FreezeRequest.model_validate(doc), freeze=freeze, outreach=outreach)


# ------------------------------------------------------------------------------------------------ playbooks

TRANSITIONS = {"pending": {"approved", "rejected"}, "approved": {"retired"}, "rejected": set(), "retired": set()}


def patch_playbook(deps: Deps, playbook_id: str, body: PlaybookPatch, via: str) -> Playbook:
    """The only place a playbook becomes `approved` (the intelligence job writes `pending` and never more)."""
    pb = deps.intel.get_playbook(playbook_id)
    if pb is None:
        raise not_found("playbook", playbook_id)
    if body.status not in TRANSITIONS.get(pb["status"], set()):
        raise conflict("invalid_transition", f"{pb['status']} -> {body.status} is not allowed")
    now = deps.store.now().isoformat()
    updated = deps.intel.set_playbook_status(playbook_id, body.status, approved_by=body.analyst_id, approved_at=now)
    deps.store.audit("playbooks", f"playbook.{body.status}", body.analyst_id, body.note, via=via, playbook_id=playbook_id,
                     previous_status=pb["status"])
    return Playbook.model_validate(updated)


# ------------------------------------------------------------------------------------------------ wishes (DA 12)

def put_wishes(deps: Deps, customer_ref: str, wishes: AdvanceWishes, via: str) -> WishesChangeResponse:
    """New wishes version. While a case is open for the customer it is stored `frozen_pending_review`, the active
    version stays in force, and the previous contact is told. Otherwise it supersedes the active version."""
    if wishes.customer_ref != customer_ref:
        raise ApiProblem(422, "customer_mismatch", "body customer_ref differs from the path")
    store, repo = deps.store, deps.store.repo
    versions = repo.list_wishes(customer_ref)
    active = repo.get_active_wishes(customer_ref)
    doc = wishes.model_dump(mode="json")
    doc.update(version=max((v["version"] for v in versions), default=0) + 1,
               supersedes_version=active["version"] if active else None, recorded_at=store.now().isoformat())
    open_cases = store.open_cases_for(customer_ref)
    if open_cases and active:
        reason = f"change attempted during open case {', '.join(c['case_id'] for c in open_cases)}"
        doc.update(status="frozen_pending_review", frozen_reason=reason)
        repo.put_wishes(doc)
        previous = min(active["trusted_contacts"], key=lambda c: c["priority"])
        for c in open_cases:
            store.audit(c["case_id"], "wishes.frozen", via, reason, via=via, new_version=doc["version"], active_version=active["version"])
            store.emit(c["case_id"], "wishes_frozen", {"new_version": doc["version"], "active_version": active["version"],
                                                       "previous_contact_id": previous["contact_id"],
                                                       "previous_contact_notified": True})
        log.warning("wishes for %s frozen pending review: %s", customer_ref, reason)
        return WishesChangeResponse(customer_ref=customer_ref, version=doc["version"], status="frozen_pending_review",
                                    frozen_reason=reason)
    doc.update(status="active", frozen_reason=None)
    if active:
        repo.put_wishes({**active, "status": "superseded"})
    repo.put_wishes(doc)
    return WishesChangeResponse(customer_ref=customer_ref, version=doc["version"], status="active")
