"""Reference implementation of the code-side copilot rules (schemas/README.md).

- verify_quotes: the quote rule (CR 17, CR 27; spike runs 1 and 2).
- merge_indicators: verified indicators accumulate on the card for the whole case (replay finding).
- assess_risk: the risk / pause rule (spike finding 1). Confidence and the pause recommendation are
  computed from verified indicators and facts, never from the model's own numbers.

Pure functions, no I/O, so the build can port them as they are.
"""

import re
import unicodedata

RULE_VERSION = "risk-v1"

CORE_GROUPS = {
    "impersonation": {"impersonated_official", "impersonated_relative"},
    "secrecy": {"secrecy_instruction"},
    "mechanism": {"safe_account_transfer", "cash_or_card_handover"},
}
PRESSURE = {"urgency", "third_party_pressure", "changed_contact_number"}

NEW_ACCOUNT_DAYS = 30
FAN_IN_7D = 5


def _norm(text):
    return re.sub(r"\s+", "", unicodedata.normalize("NFKC", text))


def verify_quotes(indicators, customer_turns):
    """Check each indicator's quote against the customer's turns.

    customer_turns: {"c1": "...", "c2": "..."}. Returns (kept, dropped).
    1. Exact substring of the cited turn: keep.
    2. Otherwise found (exactly, then normalised) in another customer turn: keep, move the turn ID.
    3. Otherwise (invented, reworded, or joined across turns): drop.
    """
    kept, dropped = [], []
    for ind in indicators:
        quote, cited = ind["quote"], ind["turn_id"]
        if quote in customer_turns.get(cited, ""):
            kept.append({**ind, "turn_id_corrected": False})
            continue
        found = next((t for t, text in customer_turns.items() if quote in text), None)
        if found is None:
            found = next((t for t, text in customer_turns.items() if _norm(quote) in _norm(text)), None)
        if found:
            kept.append({**ind, "turn_id": found, "turn_id_corrected": True})
        else:
            dropped.append({**ind, "reason": "quote_not_found"})
    return kept, dropped


def merge_indicators(card, new):
    """Add newly verified indicators to the card's list. Nothing is removed because the model
    stopped listing it on a later turn; only a teller dismissal removes an indicator."""
    seen = {(i["type"], i["turn_id"], i["quote"]) for i in card}
    return card + [i for i in new if (i["type"], i["turn_id"], i["quote"]) not in seen]


def assess_risk(indicators, cover_story, facts):
    """Risk level and pause recommendation from verified indicators and facts.

    high (pause recommended):
      H1: verified indicators from two or more core groups (impersonation, secrecy, mechanism), or
      H2: one core group + a pressure indicator + (cover story inconsistent with history, or a
          risky same-bank counterpart).
    elevated: any core group, an inconsistent cover story, or a risky counterpart.
    low: otherwise.
    """
    types = {i["type"] for i in indicators}
    groups = [g for g, members in CORE_GROUPS.items() if types & members]
    pressure = bool(types & PRESSURE)
    cover_mismatch = cover_story.get("consistent_with_history") == "no"
    age = facts.get("counterpart_graph.account_age_days")
    payers = facts.get("counterpart_graph.distinct_payers_7d")
    risky_counterpart = (age is not None and age <= NEW_ACCOUNT_DAYS) or (payers is not None and payers >= FAN_IN_7D)

    fired = []
    if len(groups) >= 2:
        fired.append("H1:" + "+".join(groups))
    if len(groups) == 1 and pressure and (cover_mismatch or risky_counterpart):
        fired.append("H2:" + groups[0] + "+pressure+" + ("cover_mismatch" if cover_mismatch else "risky_counterpart"))
    if fired:
        level = "high"
    elif groups or cover_mismatch or risky_counterpart:
        level = "elevated"
        fired += [f"E:{g}" for g in groups]
        fired += ["E:cover_mismatch"] if cover_mismatch else []
        fired += ["E:risky_counterpart"] if risky_counterpart else []
    else:
        level = "low"
    return {"level": level, "pause_recommended": level == "high", "rule_version": RULE_VERSION, "fired": fired}
