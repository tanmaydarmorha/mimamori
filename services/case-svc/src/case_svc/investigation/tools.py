"""The eight read-only investigation tools named in schemas/evidence-card.json.

Every tool returns a flat dict of *computed* fields, counts included, so an absence is checkable
(CR 27: `contractor_payments_count_12y = 0` is a field, not a missing document). A tool can only read
the customer, account and payee of the case it was built for: the model chooses which tool to call and
nothing else, so it can't be steered to another customer's records. No tool writes anything."""

from __future__ import annotations

import unicodedata
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Any

from ..deps import Deps
from ..errors import ApiProblem

TOOL_NAMES = ["get_baseline", "recent_transactions", "explain_payee", "check_lists", "counterpart_graph",
              "search_playbooks", "get_advance_wishes", "teller_notes"]
COMPANY_PREFIXES = ("カ）", "ユ）", "（カ", "(カ", "カ)", "ユ)", "ｶ)")


@dataclass
class ToolEnv:
    deps: Deps
    case_id: str
    customer_ref: str
    account_id: str
    kind: str
    amount_jpy: int
    payee_name: str | None
    payee_relation: str | None
    payee_account_id: str | None


def _norm(text: str) -> str:
    return unicodedata.normalize("NFKC", text).replace(" ", "").replace("　", "")


async def get_baseline(env: ToolEnv, **_: Any) -> dict:
    d = env.deps
    b = d.store.repo.get_baseline(env.customer_ref)
    if b is None:  # Scoring owns baselines; in a one-process-per-service setup ask it to compute lazily
        try:
            b = await d.scoring.refresh_baseline(env.customer_ref)
        except ApiProblem:
            return {"baseline_available": False}
    median = b.get("median_monthly_withdrawal_jpy") or 0
    out: dict[str, Any] = {"baseline_available": True}
    for key in ("customer_tenure_years", "median_monthly_withdrawal_jpy", "p95_withdrawal_jpy", "largest_payment_12m_jpy",
                "contractor_payments_count_12y", "renovation_loan_enquiries_count", "transfers_to_new_payees_12m"):
        if key in b:
            out[key] = b[key]
    if median:
        out["amount_vs_median_ratio"] = round(env.amount_jpy / median)
    if env.payee_name:
        known = any((env.payee_account_id and p.get("account_id") == env.payee_account_id) or p["name_kana"] == env.payee_name
                    for p in b.get("known_payees", []))
        out["new_payee"] = not known
    month = d.settings.now().month
    out["matches_seasonal_item"] = any(
        s["month"] == month and abs(env.amount_jpy - s["typical_amount_jpy"]) * 100 <= s["tolerance_pct"] * s["typical_amount_jpy"]
        for s in b.get("seasonal_items", []))
    return out


async def recent_transactions(env: ToolEnv, **_: Any) -> dict:
    now = env.deps.settings.now()
    txs = await env.deps.core.transactions(env.account_id, since=(now - timedelta(days=365 * 12)).isoformat())
    last90 = [t for t in txs if t.booked_at >= now - timedelta(days=90)]
    out_transfers = [t for t in last90 if t.kind == "transfer_out"]
    to_payee = [t for t in txs if t.kind == "transfer_out" and (
        (env.payee_account_id and t.counterparty_account_id == env.payee_account_id)
        or (env.payee_name and t.counterparty_name_kana == env.payee_name))]
    # Running totals, computed as Scoring does (WI-012): this payment included, seasonal rows left out.
    svc = env.deps.svc
    b = env.deps.store.repo.get_baseline(env.customer_ref) or {}
    seasonal = b.get("seasonal_items", [])

    def is_seasonal(t) -> bool:
        return any(s["month"] == t.booked_at.month
                   and abs(t.amount_jpy - s["typical_amount_jpy"]) * 100 <= s["tolerance_pct"] * s["typical_amount_jpy"]
                   for s in seasonal)

    payee_since, out_since = now - timedelta(days=svc.payee_total_days), now - timedelta(hours=svc.outflow_window_hours)
    payee_total, payee_count, outflow_24h = env.amount_jpy, 1, env.amount_jpy
    for t in txs:
        if t.kind not in ("transfer_out", "withdrawal") or t.booked_at > now or is_seasonal(t):
            continue
        if t.booked_at >= out_since:
            outflow_24h += t.amount_jpy
        if env.kind == "transfer" and t.kind == "transfer_out" and t.booked_at >= payee_since and (
                (env.payee_account_id and t.counterparty_account_id == env.payee_account_id)
                or (env.payee_name and not env.payee_account_id and t.counterparty_name_kana == env.payee_name)):
            payee_total += t.amount_jpy
            payee_count += 1
    return {
        "payee_total_7d_jpy": payee_total,
        "payments_to_payee_7d": payee_count,
        "outflow_24h_jpy": outflow_24h,
        "transactions_count_90d": len(last90),
        "transfers_out_count_90d": len(out_transfers),
        "largest_transfer_out_90d_jpy": max((t.amount_jpy for t in out_transfers), default=0),
        "payments_to_this_payee_count_12y": len(to_payee),
        "contractor_payments_count_12m": sum(1 for t in txs if t.kind == "transfer_out" and t.counterparty_category == "contractor"
                                             and t.booked_at >= now - timedelta(days=365)),
    }


async def explain_payee(env: ToolEnv, **_: Any) -> dict:
    if not env.payee_name:
        return {"payee_present": False}
    out: dict[str, Any] = {"payee_present": True, "payee_relation": env.payee_relation,
                           "payee_holder_type": "company" if _norm(env.payee_name).startswith(tuple(_norm(p) for p in COMPANY_PREFIXES)) else "individual"}
    if env.payee_relation == "same_bank" and env.payee_account_id:
        acct = await env.deps.core.get_account(env.payee_account_id)  # balance is deliberately not read into the result
        opened = acct.opened_on
        age = (env.deps.settings.now().date() - date.fromisoformat(opened)).days
        out.update(payee_account_opened_on=opened, payee_account_age_days=age, payee_account_status=acct.status)
    return out


async def check_lists(env: ToolEnv, **_: Any) -> dict:
    snap = env.deps.ref.get_latest_snapshot()
    if snap is None:
        return {"watchlist_available": False}
    hits = [e for e in snap["entries"] if env.payee_name and (
        (e.get("name_kana") and _norm(e["name_kana"]) == _norm(env.payee_name))
        or (e.get("account_hint") and env.payee_account_id and env.payee_account_id in e["account_hint"]))]
    return {"watchlist_available": True, "watchlist_snapshot_id": snap["snapshot_id"], "watchlist_matches_count": len(hits)}


async def counterpart_graph(env: ToolEnv, **_: Any) -> dict:
    if env.payee_relation != "same_bank" or not env.payee_account_id:
        return {"visible": False}  # account age and fan-in are only visible for same-bank payees (CR 1)
    d = env.deps
    acct = await d.core.get_account(env.payee_account_id)
    payers = await d.core.payers(env.payee_account_id, days=7)
    others = {p.customer_ref for p in payers.payers if p.customer_ref != env.customer_ref}
    age = (d.settings.now().date() - date.fromisoformat(acct.opened_on)).days
    return {"visible": True, "account_age_days": age,
            "distinct_payers_7d": len(others) + 1,  # counts the payer asking now, as Scoring does
            "distinct_other_payers_7d": len(others)}


async def search_playbooks(env: ToolEnv, hypothesis: str = "", **_: Any) -> dict:
    approved = env.deps.intel.list_playbooks("approved")  # only approved playbooks are ever visible
    method = "cash_handover" if env.kind == "cash_withdrawal" else "transfer"
    matching = [p["id"] for p in approved if method in p["payment_methods"] and (not hypothesis or p.get("hypothesis") == hypothesis)]
    return {"approved_playbooks_count": len(approved), "matching_playbooks_count": len(matching), "matching_playbook_ids": matching}


async def get_advance_wishes(env: ToolEnv, **_: Any) -> dict:
    w = env.deps.store.repo.get_active_wishes(env.customer_ref)
    if not w:
        return {"wishes_on_file": False}
    now = env.deps.settings.now()
    days = env.deps.svc.contact_phone_change_days
    changed = any(c.get("phone_changed_at") and datetime.fromisoformat(c["phone_changed_at"]) >= now - timedelta(days=days)
                  for c in w["trusted_contacts"])
    return {"wishes_on_file": True, "wishes_version": w["version"], "cooling_off_enabled": w["cooling_off"]["enabled"],
            "trusted_contacts_count": len(w["trusted_contacts"]), "outbound_notice_consent": w["outbound_notice_consent"],
            "contact_number_changed_recently": changed}


async def teller_notes(env: ToolEnv, **_: Any) -> dict:
    notes = env.deps.store.notes_for(env.customer_ref)
    return {"notes_count": len(notes), "contact_flagged_notes_count": sum(1 for n in notes if "contact_flagged" in n.get("flags", []))}


TOOLS = {f.__name__: f for f in (get_baseline, recent_transactions, explain_payee, check_lists, counterpart_graph,
                                 search_playbooks, get_advance_wishes, teller_notes)}
assert set(TOOLS) == set(TOOL_NAMES)
