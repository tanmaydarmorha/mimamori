"""The evidence card is a view derived from the case's internal state: verified facts, verified quotes
(indicators), inferences with their grounds, the cover-story check and the next question. Risk is computed
here in code (`risk-v1`, mimamori_common.rules); nothing the model says about likelihood is used.

Internal state (case-db `case_state`) is the source of truth, so claim IDs stay stable: a fact keeps the ID
of its `tool.field`, a quote keeps the ID of its (type, turn, text)."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from mimamori_common.rules import CORE_GROUPS, PRESSURE, assess_risk

from .bank import BankView

# Statement text for known tool fields is written by code, so the words next to a verified value can't
# disagree with it. Unknown fields fall back to the model's statement.
FACT_TEXT: dict[tuple[str, str], str] = {
    ("get_baseline", "amount_vs_median_ratio"): "This request is about {value} times the customer's typical monthly withdrawal.",
    ("get_baseline", "new_payee"): "The payee is new for this customer: {value}.",
    ("get_baseline", "customer_tenure_years"): "Customer for {value} years.",
    ("get_baseline", "median_monthly_withdrawal_jpy"): "Typical monthly withdrawals are ¥{value:,}.",
    ("get_baseline", "p95_withdrawal_jpy"): "95th percentile withdrawal is ¥{value:,}.",
    ("get_baseline", "largest_payment_12m_jpy"): "Largest payment in the last 12 months was ¥{value:,}.",
    ("get_baseline", "contractor_payments_count_12y"): "Payments to contractors in 12 years: {value}.",
    ("get_baseline", "renovation_loan_enquiries_count"): "Renovation loan enquiries on record: {value}.",
    ("get_baseline", "transfers_to_new_payees_12m"): "Transfers to new payees in the last 12 months: {value}.",
    ("get_baseline", "matches_seasonal_item"): "Matches a seasonal pattern in the baseline: {value}.",
    ("recent_transactions", "transactions_count_90d"): "Transactions in the last 90 days: {value}.",
    ("recent_transactions", "transfers_out_count_90d"): "Outgoing transfers in the last 90 days: {value}.",
    ("recent_transactions", "largest_transfer_out_90d_jpy"): "Largest outgoing transfer in the last 90 days: ¥{value:,}.",
    ("recent_transactions", "payments_to_this_payee_count_12y"): "Earlier payments to this payee in 12 years: {value}.",
    ("recent_transactions", "contractor_payments_count_12m"): "Payments to contractors in the last 12 months: {value}.",
    ("explain_payee", "payee_holder_type"): "The payee account holder looks like a {value}.",
    ("explain_payee", "payee_account_age_days"): "The payee account was opened {value} days ago.",
    ("explain_payee", "payee_account_status"): "The payee account status is {value}.",
    ("check_lists", "watchlist_matches_count"): "Watchlist matches for the payee: {value}.",
    ("counterpart_graph", "account_age_days"): "The payee account was opened {value} days ago.",
    ("counterpart_graph", "distinct_payers_7d"): "{value} different customers paid this account in the last 7 days (including this request).",
    ("counterpart_graph", "distinct_other_payers_7d"): "{value} other customers paid this account in the last 7 days.",
    ("search_playbooks", "matching_playbooks_count"): "Approved playbooks matching this payment method: {value}.",
    ("get_advance_wishes", "wishes_on_file"): "Advance wishes on file: {value}.",
    ("get_advance_wishes", "cooling_off_enabled"): "Cooling-off pause enabled in the wishes: {value}.",
    ("get_advance_wishes", "contact_number_changed_recently"): "The trusted contact's number changed recently: {value}.",
    ("teller_notes", "notes_count"): "Teller notes on this customer: {value}.",
    ("teller_notes", "contact_flagged_notes_count"): "Teller notes flagging the trusted contact: {value}.",
}

BENIGN = {
    ("get_baseline", "contractor_payments_count_12y"): lambda v: isinstance(v, int) and v > 0,
    ("get_baseline", "matches_seasonal_item"): lambda v: v is True,
    ("recent_transactions", "payments_to_this_payee_count_12y"): lambda v: isinstance(v, int) and v > 0,
    ("counterpart_graph", "account_age_days"): lambda v: isinstance(v, int) and v > 365,
    ("explain_payee", "payee_account_age_days"): lambda v: isinstance(v, int) and v > 365,
}
RISKY_COUNTERPART_FIELDS = {("counterpart_graph", "account_age_days"), ("counterpart_graph", "distinct_payers_7d")}
EVIDENCE_FAMILY = {"get_baseline": "bank_records", "recent_transactions": "bank_records", "explain_payee": "bank_records",
                   "counterpart_graph": "bank_records", "check_lists": "reference_lists", "search_playbooks": "playbooks",
                   "get_advance_wishes": "bank_records", "teller_notes": "bank_records"}


def fact_statement(tool: str, field: str, value: Any, fallback: str) -> str:
    template = FACT_TEXT.get((tool, field))
    if template:
        try:
            return template.format(value=value)
        except (ValueError, TypeError):
            pass
    return fallback


def new_state(case_id: str, payee_account_id: str | None = None) -> dict:
    return {
        "case_id": case_id, "payee_account_id": payee_account_id, "card_version": 0,
        "facts": [], "fact_ids": {}, "indicators": [], "quote_ids": {}, "inferences": [], "dropped": [],
        "dismissed": [], "counters": {"f": 0, "q": 0, "i": 0},
        "cover_story": {"stated_reason": None, "consistent_with_history": "unknown", "matches_playbook": None},
        "leading_hypothesis": "legitimate", "rationale_en": None, "suggested_question_ids": [],
        "next_question": None, "police_notified": False, "contact_calls": 0,
        "investigation": {"status": "pending", "tools_called": [], "model": None, "notes": []},
    }


def _next_id(state: dict, prefix: str) -> str:
    state["counters"][prefix] += 1
    return f"{prefix}{state['counters'][prefix]}"


def set_facts(state: dict, facts: list[dict]) -> None:
    """Replace the verified facts. Each item: tool, field, value, statement_en. IDs are stable per tool.field."""
    out = []
    for f in facts:
        key = f"{f['tool']}.{f['field']}"
        fid = state["fact_ids"].get(key) or state["fact_ids"].setdefault(key, _next_id(state, "f"))
        out.append({"id": fid, "kind": "fact",
                    "statement_en": fact_statement(f["tool"], f["field"], f["value"], f["statement_en"]),
                    "source": {"tool": f["tool"], "field": f["field"], "value": f["value"]}, "verified": True})
    state["facts"] = out


def add_indicators(state: dict, kept: list[dict]) -> None:
    dismissed = {(d["type"], d["quote"]) for d in state["dismissed"]}
    for ind in kept:
        if (ind["type"], ind["quote"]) in dismissed:
            continue  # a teller dismissed it; the model re-listing it does not bring it back
        key = f"{ind['type']}|{ind['turn_id']}|{ind['quote']}"
        if key in state["quote_ids"]:
            continue
        qid = _next_id(state, "q")
        state["quote_ids"][key] = qid
        state["indicators"].append({"id": qid, "type": ind["type"], "turn_id": ind["turn_id"], "quote": ind["quote"],
                                    "turn_id_corrected": bool(ind.get("turn_id_corrected"))})


def add_dropped(state: dict, claim: dict, reason: str) -> None:
    entry = {"claim": claim, "reason": reason}
    if entry not in state["dropped"]:
        state["dropped"].append(entry)


def set_inferences(state: dict, origin: str, items: list[dict]) -> None:
    """items: statement_en and refs (["fact:tool.field", "quote:<quote id key>"]). Replaces this origin's inferences."""
    keep = [i for i in state["inferences"] if i["origin"] != origin]
    for it in items:
        keep.append({"id": _next_id(state, "i"), "origin": origin, "statement_en": it["statement_en"], "refs": it["refs"]})
    state["inferences"] = keep


def fact_values(state: dict) -> dict[str, Any]:
    return {f"{f['source']['tool']}.{f['source']['field']}": f["source"]["value"] for f in state["facts"]}


def evidence_families(state: dict) -> set[str]:
    fams = {EVIDENCE_FAMILY.get(f["source"]["tool"], "bank_records") for f in state["facts"]}
    if state["indicators"]:
        fams.add("customer_statements")
    return fams


def _group_types(groups: list[str]) -> set[str]:
    return set().union(*(CORE_GROUPS[g] for g in groups)) if groups else set()


def _fired(raw: list[str], quotes: list[dict], facts: list[dict]) -> list[dict]:
    def q_ids(types: set[str]) -> list[str]:
        return [q["id"] for q in quotes if q["source"]["text"] and q["indicator"] in types]

    cover = q_ids({"cover_story"}) + [f["id"] for f in facts if f["source"]["tool"] == "get_baseline"]
    risky = [f["id"] for f in facts if (f["source"]["tool"], f["source"]["field"]) in RISKY_COUNTERPART_FIELDS]
    out = []
    for cond in raw:
        head, _, rest = cond.partition(":")
        parts = rest.split("+")
        claims: list[str] = []
        for p in parts:
            if p in CORE_GROUPS:
                claims += q_ids(CORE_GROUPS[p])
            elif p == "pressure":
                claims += q_ids(PRESSURE)
            elif p == "cover_mismatch":
                claims += cover
            elif p == "risky_counterpart":
                claims += risky
        out.append({"condition": cond, "claims": list(dict.fromkeys(claims))})
    return out


def build_card(case: dict, state: dict, bank: BankView, now: datetime) -> dict:
    """Derive the evidence card (schemas/evidence-card.json) from state. Bumps the card version."""
    facts = state["facts"]
    quotes = [{"id": i["id"], "kind": "quote", "indicator": i["type"],
               "source": {"turn_id": i["turn_id"], "text": i["quote"]},
               "turn_id_corrected": i["turn_id_corrected"], "verified": True} for i in state["indicators"]]
    fact_by_key = {f"{f['source']['tool']}.{f['source']['field']}": f["id"] for f in facts}
    quote_by_key = {k: v for k, v in state["quote_ids"].items()}
    live_quotes = {q["id"] for q in quotes}
    inferences = []
    for inf in state["inferences"]:
        grounds = []
        for ref in inf["refs"]:
            kind, _, key = ref.partition(":")
            gid = fact_by_key.get(key) if kind == "fact" else quote_by_key.get(key)
            if gid and (kind == "fact" or gid in live_quotes):
                grounds.append(gid)
        if grounds:  # an inference whose grounds are gone (dismissed quote) disappears with them
            inferences.append({"id": inf["id"], "kind": "inference", "statement_en": inf["statement_en"],
                               "grounds": grounds, "shown_as": "hypothesis"})

    risk_raw = assess_risk(state["indicators"], state["cover_story"], fact_values(state))
    leading = state["leading_hypothesis"]
    matched = state["cover_story"].get("matches_playbook")
    risk = {"level": risk_raw["level"], "pause_recommended": risk_raw["pause_recommended"],
            "rule_version": risk_raw["rule_version"], "fired": _fired(risk_raw["fired"], quotes, facts)}
    if risk["pause_recommended"]:
        line = bank.choose_hold_line(leading, matched)
        risk["hold_line_id"] = line["id"] if line else None

    benign = [f["id"] for f in facts if BENIGN.get((f["source"]["tool"], f["source"]["field"]), lambda v: False)(f["source"]["value"])]
    scam_support = [q["id"] for q in quotes] + [f["id"] for f in facts if (f["source"]["tool"], f["source"]["field"]) in RISKY_COUNTERPART_FIELDS]
    names = [leading] if leading != "legitimate" else []
    names.append("legitimate")
    if len(names) < 2:
        names.append("other_scam")
    hypotheses = []
    for name in names:
        pb = bank.playbook(matched) if matched and (bank.playbook(matched) or {}).get("hypothesis") == name else bank.playbook_for(name)
        hypotheses.append({"name": name, "playbook_id": pb["id"] if pb else None,
                           "supporting_claims": benign if name == "legitimate" else (scam_support if name == leading else [])})

    state["card_version"] += 1
    return {
        "case_id": case["case_id"], "customer_ref": case["customer_ref"], "card_version": state["card_version"],
        "updated_at": now.isoformat(), "request": case["request"],
        "claims": facts + quotes + inferences, "hypotheses": hypotheses, "risk": risk,
        "next_question": state["next_question"], "dropped": state["dropped"],
    }
