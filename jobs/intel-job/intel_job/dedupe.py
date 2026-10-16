"""De-duplication. An alert is a duplicate when its URL is already a source of a stored playbook, its
id is taken (never overwrite an existing playbook, least of all an approved one), or it says nearly
the same thing as a stored or just-written playbook of the same hypothesis."""

from __future__ import annotations

SIMILARITY = 0.6


def _phrases(pb: dict) -> set[str]:
    return {p.strip() for p in pb.get("script_phrases", []) if p.strip()}


def _jaccard(a: set[str], b: set[str]) -> float:
    return len(a & b) / len(a | b) if a and b else 0.0


def duplicate_reason(candidate: dict, existing: list[dict]) -> str | None:
    urls = {s["url"] for pb in existing for s in pb.get("sources", [])}
    if any(s["url"] in urls for s in candidate["sources"]):
        return "alert URL already ingested"
    for pb in existing:
        if pb["id"] == candidate["id"]:
            return f"id {pb['id']} already exists (status {pb.get('status')})"
    for pb in existing:
        if pb.get("hypothesis") == candidate.get("hypothesis") and _jaccard(_phrases(pb), _phrases(candidate)) >= SIMILARITY:
            return f"near-duplicate of {pb['id']}"
    return None
