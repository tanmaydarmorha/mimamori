"""Validate the example documents against the schemas, plus the cross-document rules JSON Schema
can't express. Usage: python schemas/validate.py   (needs `pip install jsonschema`)."""

import json
import re
import sys
from pathlib import Path

import jsonschema
from referencing import Registry, Resource

HERE = Path(__file__).parent
EXAMPLES = HERE / "examples"

# example file -> (schema file, JSON pointer inside the schema or "", is the example a list?)
EXAMPLE_SCHEMAS = {
    "question-bank-general.json": ("question-bank.json", "", False),
    "playbooks.json": ("playbook.json", "", True),
    "evidence-card-tanaka.json": ("evidence-card.json", "", False),
    "advance-wishes-tanaka.json": ("advance-wishes.json", "", False),
    "contact-brief-tanaka.json": ("contact-brief.json", "", False),
    "call-turn-tanaka.json": ("call-turn.json", "", False),
    "call-templates.json": ("call-turn.json", "#/$defs/template", True),
    "contact-view-tanaka.json": ("contact-view.json", "", False),
}

FORBIDDEN_WORDING = re.compile("認知|判断能力|物忘れ|記憶|ボケ|嘘|だまされていませんか|騙されていませんか")


def load(path):
    return json.loads(Path(path).read_text())


def main():
    schemas = {p.name: load(p) for p in HERE.glob("*.json")}
    registry = Registry().with_resources((s["$id"], Resource.from_contents(s)) for s in schemas.values())
    errors = []

    for example, (schema_name, pointer, is_list) in EXAMPLE_SCHEMAS.items():
        schema = {"$ref": schemas[schema_name]["$id"] + pointer}
        validator = jsonschema.Draft202012Validator(schema, registry=registry, format_checker=jsonschema.FormatChecker())
        docs = load(EXAMPLES / example)
        for i, doc in enumerate(docs if is_list else [docs]):
            for err in validator.iter_errors(doc):
                errors.append(f"{example}[{i}] {'/'.join(map(str, err.path))}: {err.message[:160]}")

    # Cross-document rules.
    general = load(EXAMPLES / "question-bank-general.json")
    playbooks = load(EXAMPLES / "playbooks.json")
    questions = general["questions"] + [q for pb in playbooks for q in pb["question_bank"]["questions"]]
    hold_lines = general["hold_lines"] + [h for pb in playbooks for h in pb["question_bank"]["hold_lines"]]
    ids = [q["id"] for q in questions] + [h["id"] for h in hold_lines]
    errors += [f"duplicate wording id {i}" for i in {i for i in ids if ids.count(i) > 1}]
    for item in questions + hold_lines:
        if FORBIDDEN_WORDING.search(item["ja"]):
            errors.append(f"forbidden wording in {item['id']}")
        used = set(re.findall(r"{(\w+)}", item["ja"]))
        if used != set(item.get("slots", used)):
            errors.append(f"{item['id']}: slots {item.get('slots')} don't match placeholders {sorted(used)}")
    for pb in playbooks:
        if pb.get("hypothesis") and not pb["id"].startswith(f"pb.{pb['hypothesis']}."):
            errors.append(f"{pb['id']}: id should start with pb.{pb['hypothesis']}.")
        prefix = f"q.{pb['hypothesis']}." if pb.get("hypothesis") else None
        for q in pb["question_bank"]["questions"]:
            if prefix and not q["id"].startswith(prefix):
                errors.append(f"{pb['id']}: question {q['id']} should start with {prefix}")

    card = load(EXAMPLES / "evidence-card-tanaka.json")
    claim_ids = {c["id"] for c in card["claims"]}
    for c in card["claims"]:
        for g in c.get("grounds", []):
            if g not in claim_ids:
                errors.append(f"evidence card: inference {c['id']} cites missing claim {g}")
    for h in card["hypotheses"]:
        errors += [f"evidence card: hypothesis {h['name']} cites missing {c}" for c in h["supporting_claims"] if c not in claim_ids]
    for f in card["risk"]["fired"]:
        errors += [f"evidence card: rule {f['condition']} cites missing {c}" for c in f["claims"] if c not in claim_ids]
    if card["next_question"] and card["next_question"]["question_id"] not in ids:
        errors.append("evidence card: next_question id not in any bank")
    if card["risk"]["hold_line_id"] and card["risk"]["hold_line_id"] not in ids:
        errors.append("evidence card: hold_line_id not in any bank")
    if card["risk"]["pause_recommended"] != (card["risk"]["level"] == "high"):
        errors.append("evidence card: pause_recommended must equal level == high")

    templates = load(EXAMPLES / "call-templates.json")
    intents = schemas["call-turn.json"]["$defs"]["intent"]["enum"]
    missing = set(intents) - {t["intent"] for t in templates}
    errors += [f"call templates: no template for intent {m}" for m in sorted(missing)]
    for t in templates:
        if re.search(r"[0-9０-９]|[一二三四五六七八九十百千万億]円", t["ja"] + t["fallback_ja"]):
            errors.append(f"call template {t['intent']} contains an amount")
        if re.search(r"[0-9]|\b(?:one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|twenty|thirty|forty|fifty|sixty|seventy|eighty|ninety|hundred|thousand|million|billion|lakh|crore)\b|[¥$₹€]|\b(?:yen|rupees?|dollars?)\b", t["en"] + t["fallback_en"], re.I):
            errors.append(f"call template {t['intent']} contains an amount (en)")
        slots = [set(re.findall(r"\{([a-z_]+)\}", t[k])) for k in ("ja", "en")]
        fslots = [set(re.findall(r"\{([a-z_]+)\}", t[k])) for k in ("fallback_ja", "fallback_en")]
        ren = lambda xs: {x.replace("_ja", "").replace("_en", "") for x in xs}
        if ren(slots[0]) != ren(slots[1]) or ren(fslots[0]) != ren(fslots[1]):
            errors.append(f"call template {t['intent']}: ja/en slots differ")

    brief = load(EXAMPLES / "contact-brief-tanaka.json")
    wishes = load(EXAMPLES / "advance-wishes-tanaka.json")
    leaked = set(brief["disclosable"]) - set(wishes["disclosure"]["may_disclose"])
    errors += [f"contact brief discloses {f}, not allowed by the wishes" for f in sorted(leaked)]
    view = load(EXAMPLES / "contact-view-tanaka.json")
    if view["reached"] != (view["verification"]["caller_number_match"] and view["verification"]["case_code_match"]):
        errors.append("contact view: reached must equal both verification checks")
    errors += [f"contact view: disclosed {f} not in brief" for f in view["disclosed"] if f not in brief["disclosable"]]

    if errors:
        print("\n".join(errors))
        sys.exit(1)
    print(f"ok: {len(EXAMPLE_SCHEMAS)} example files, {len(schemas)} schemas, {len(questions)} questions, {len(hold_lines)} hold lines")


if __name__ == "__main__":
    main()
