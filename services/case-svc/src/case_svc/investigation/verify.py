"""Code checks every fact the investigation model proposes against the tool result it cites, and drops
inferences that don't rest on a verified fact (CR 8, CR 27, DA 10). Pure functions."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


def values_equal(claimed: Any, actual: Any) -> bool:
    if isinstance(claimed, bool) or isinstance(actual, bool):
        return isinstance(claimed, bool) and isinstance(actual, bool) and claimed == actual
    if isinstance(claimed, (int, float)) and isinstance(actual, (int, float)):
        return claimed == actual
    return claimed == actual


@dataclass
class Verified:
    facts: list[dict] = field(default_factory=list)  # tool, field, value, statement_en
    inferences: list[dict] = field(default_factory=list)  # statement_en, refs
    dropped: list[dict] = field(default_factory=list)  # claim, reason


def verify_findings(facts: list[dict], inferences: list[dict], results: dict[str, dict]) -> Verified:
    """`results` holds what the tools actually returned in this run. A fact is kept only if its tool was run, its
    field exists in that result (absence is a field too, e.g. a count of 0) and the value is equal."""
    out = Verified()
    seen: set[str] = set()
    for f in facts:
        tool, name = f.get("tool"), f.get("field")
        key = f"{tool}.{name}"
        result = results.get(tool)
        if result is None or name not in result:
            out.dropped.append({"claim": {"tool": tool, "field": name, "value": f.get("value"), "statement_en": f.get("statement_en", "")},
                                "reason": "no_citation"})
        elif not values_equal(f.get("value"), result[name]):
            out.dropped.append({"claim": {"tool": tool, "field": name, "value": f.get("value"), "statement_en": f.get("statement_en", "")},
                                "reason": "value_mismatch"})
        elif key not in seen:
            seen.add(key)
            out.facts.append({"tool": tool, "field": name, "value": result[name], "statement_en": f.get("statement_en", "")})
    verified_keys = seen
    for inf in inferences:
        refs = [f"fact:{g}" for g in inf.get("grounds", []) if g in verified_keys]
        if refs:
            out.inferences.append({"statement_en": inf["statement_en"], "refs": refs})
        else:
            out.dropped.append({"claim": {"statement_en": inf.get("statement_en", ""), "grounds": inf.get("grounds", [])},
                                "reason": "ungrounded_inference"})
    return out
