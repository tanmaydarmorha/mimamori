"""Gemma counter-copilot capability spike (Step 0 of the review-response plan; see docs/decisions.md).

Runs every customer turn in conversations.json through a local Ollama model, validates the JSON
output against schema.json, checks quotes against the transcript, and writes raw results.

--v2 uses the design from schemas/ instead: system_prompt_v2.md, schemas/copilot-turn.json, the seed
playbooks and question bank in schemas/examples/, and a check that the chosen question id exists.

Usage: python run_spike.py [--v2] [--model gemma4:12b] [--think] [--temperature 0] [--conversations file] [--tag name]
Requires: Ollama running locally, `pip install jsonschema`.
"""

import argparse
import json
import re
import time
import unicodedata
import urllib.request
from pathlib import Path

import jsonschema

HERE = Path(__file__).parent
SCHEMAS = HERE.parent.parent / "schemas"
OLLAMA_URL = "http://localhost:11434/api/chat"


def load(name):
    return json.loads((HERE / name).read_text())


def norm(text):
    return re.sub(r"\s+", "", unicodedata.normalize("NFKC", text))


def build_user_message(conv, upto, playbooks, bank=None):
    lines = []
    for i, turn in enumerate(conv["turns"][: upto + 1], start=1):
        lines.append(f"t{i} (teller): {turn['teller']}")
        lines.append(f"c{i} (customer): {turn['customer']}")
    return (
        f"<request>\n{conv['request']}\n</request>\n\n"
        f"<verified_facts>\n{json.dumps(conv['facts'], ensure_ascii=False, indent=1)}\n</verified_facts>\n\n"
        f"<approved_playbooks>\n{json.dumps(playbooks, ensure_ascii=False, indent=1)}\n</approved_playbooks>\n\n"
        + (f"<question_bank>\n{json.dumps(bank, ensure_ascii=False, indent=1)}\n</question_bank>\n\n" if bank else "")
        + f"<transcript>\n" + "\n".join(lines) + "\n</transcript>\n\n"
        f"The newest customer turn is c{upto + 1}. Reply with the JSON object."
    )


def call_model(model, system, user, think, temperature):
    body = {
        "model": model,
        "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
        "stream": False,
        "think": think,
        "options": {"temperature": temperature, "seed": 7, "num_ctx": 16384},
    }
    req = urllib.request.Request(OLLAMA_URL, data=json.dumps(body).encode(), headers={"Content-Type": "application/json"})
    started = time.time()
    with urllib.request.urlopen(req, timeout=600) as resp:
        data = json.loads(resp.read())
    return data["message"]["content"], time.time() - started


def parse_json(raw):
    text = raw.strip()
    fenced = re.match(r"^```(?:json)?\s*(.*?)\s*```$", text, re.S)
    if fenced:
        return json.loads(fenced.group(1)), "fenced"
    return json.loads(text), "clean"


def check_quotes(output, conv):
    results = []
    for ind in output.get("indicators", []):
        idx = int(ind["turn_id"][1:]) - 1
        source = conv["turns"][idx]["customer"] if 0 <= idx < len(conv["turns"]) else ""
        results.append({
            "turn_id": ind["turn_id"],
            "quote": ind["quote"],
            "exact": ind["quote"] in source,
            "normalised": norm(ind["quote"]) in norm(source),
        })
    return results


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="gemma4:12b")
    ap.add_argument("--think", action="store_true")
    ap.add_argument("--temperature", type=float, default=0.0)
    ap.add_argument("--conversations", default="conversations.json")
    ap.add_argument("--v2", action="store_true")
    ap.add_argument("--tag", default="")
    args = ap.parse_args()

    bank = None
    if args.v2:
        system = (HERE / "system_prompt_v2.md").read_text()
        schema = json.loads((SCHEMAS / "copilot-turn.json").read_text())
        seed = json.loads((SCHEMAS / "examples" / "playbooks.json").read_text())
        general = json.loads((SCHEMAS / "examples" / "question-bank-general.json").read_text())
        keep = ["id", "hypothesis", "name", "impersonates", "script_phrases", "victim_instructions", "cover_stories", "payment_methods"]
        playbooks = [{k: pb[k] for k in keep} for pb in seed]
        questions = general["questions"] + [q for pb in seed for q in pb["question_bank"]["questions"]]
        bank = [{"id": q["id"], "ja": q["ja"], "purpose": q["purpose"], "separates": q["separates"]} for q in questions]
        bank_ids = {q["id"] for q in questions}
    else:
        system = (HERE / "system_prompt.md").read_text()
        schema = load("schema.json")
        playbooks = load("playbooks.json")
    conversations = load(args.conversations)

    suffix = "" if args.conversations == "conversations.json" else "-" + Path(args.conversations).stem
    tag = args.tag or f"{'v2-' if args.v2 else ''}{args.model.replace(':', '-')}{'-think' if args.think else ''}-t{args.temperature}{suffix}"
    out_path = HERE / "results" / f"{tag}.jsonl"
    out_path.parent.mkdir(exist_ok=True)

    with out_path.open("w") as out:
        for conv in conversations:
            for i in range(len(conv["turns"])):
                user = build_user_message(conv, i, playbooks, bank)
                raw, seconds = call_model(args.model, system, user, args.think, args.temperature)
                record = {"conv": conv["id"], "turn": f"c{i + 1}", "seconds": round(seconds, 1), "raw": raw}
                try:
                    output, shape = parse_json(raw)
                    record["json_shape"] = shape
                    record["output"] = output
                    jsonschema.validate(output, schema)
                    record["schema_valid"] = True
                    record["quotes"] = check_quotes(output, conv)
                    if bank:
                        record["question_id_valid"] = output["next_question_id"] in bank_ids
                except (json.JSONDecodeError, jsonschema.ValidationError) as err:
                    record["schema_valid"] = False
                    record["error"] = str(err).splitlines()[0][:300]
                out.write(json.dumps(record, ensure_ascii=False) + "\n")
                out.flush()
                status = "ok " if record["schema_valid"] else "BAD"
                out_ = record.get("output", {}) if record["schema_valid"] else {}
                detail = f"q={out_.get('next_question_id')}" if args.v2 else f"pause={out_.get('recommend_pause', '-')}"
                print(f"{conv['id']} c{i + 1}: {status} {detail} {seconds:.1f}s", flush=True)
    print(f"wrote {out_path}")


if __name__ == "__main__":
    main()
