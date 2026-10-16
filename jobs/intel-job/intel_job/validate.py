"""Validation of a candidate playbook: the JSON Schema, the Pydantic `Playbook` model, and the
cross-rules from `schemas/validate.py` (id and question-id prefixes, banned wording, slot
placeholders, unique wording ids). Returns a list of problems; empty means valid."""

from __future__ import annotations

import importlib.util
import json
import re
from datetime import date
from functools import lru_cache

import jsonschema
from pydantic import ValidationError
from referencing import Registry, Resource

from mimamori_common.models import Playbook
from mimamori_common.schemas import schemas_dir

SCAM_HYPOTHESES = ("fake_police", "relative_in_trouble", "gold_bullion", "other_scam")


@lru_cache(maxsize=1)
def _forbidden_wording() -> re.Pattern:
    """Single source of truth: the regex in schemas/validate.py."""
    spec = importlib.util.spec_from_file_location("mimamori_schema_validate", schemas_dir() / "validate.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.FORBIDDEN_WORDING


@lru_cache(maxsize=1)
def _validator() -> jsonschema.Draft202012Validator:
    schemas = {p.name: json.loads(p.read_text(encoding="utf-8")) for p in schemas_dir().glob("*.json")}
    registry = Registry().with_resources((s["$id"], Resource.from_contents(s)) for s in schemas.values())
    schema = {"$ref": schemas["playbook.json"]["$id"]}
    return jsonschema.Draft202012Validator(schema, registry=registry, format_checker=jsonschema.FormatChecker())


def validate_playbook(pb: dict, *, taken_wording_ids: set[str] = frozenset(), today: date | None = None) -> list[str]:
    problems: list[str] = []
    for err in _validator().iter_errors(pb):
        problems.append(f"schema {'/'.join(map(str, err.path)) or '(root)'}: {err.message[:160]}")
    try:
        Playbook.model_validate(pb)
    except ValidationError as err:
        problems += [f"model {'/'.join(map(str, e['loc']))}: {e['msg'][:160]}" for e in err.errors()]
    if problems:  # cross-rules assume the structure is sound
        return problems

    hyp = pb.get("hypothesis")
    if hyp not in SCAM_HYPOTHESES:
        problems.append(f"hypothesis must be one of {SCAM_HYPOTHESES}, got {hyp!r}")
    else:
        if not pb["id"].startswith(f"pb.{hyp}."):
            problems.append(f"{pb['id']}: id should start with pb.{hyp}.")
        for q in pb["question_bank"]["questions"]:
            if not q["id"].startswith(f"q.{hyp}."):
                problems.append(f"question {q['id']} should start with q.{hyp}.")
        for h in pb["question_bank"]["hold_lines"]:
            if not h["id"].startswith(f"h.{hyp}."):
                problems.append(f"hold line {h['id']} should start with h.{hyp}.")

    bank = pb["question_bank"]
    items = bank["questions"] + bank["hold_lines"]
    ids = [i["id"] for i in items]
    problems += [f"duplicate wording id {i}" for i in sorted({i for i in ids if ids.count(i) > 1})]
    problems += [f"wording id {i} already exists in intel-db" for i in sorted(set(ids) & set(taken_wording_ids))]
    forbidden = _forbidden_wording()
    for item in items:
        if forbidden.search(item["ja"]):
            problems.append(f"forbidden wording in {item['id']}")
        used = set(re.findall(r"{(\w+)}", item["ja"]))
        if used != set(item.get("slots", used)):
            problems.append(f"{item['id']}: slots {item.get('slots')} don't match placeholders {sorted(used)}")

    today = today or date.today()
    for s in pb["sources"]:
        if date.fromisoformat(s["published_at"]) > today:
            problems.append(f"source {s['url']} published_at {s['published_at']} is in the future")
    return problems
