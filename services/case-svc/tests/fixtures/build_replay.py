"""Build the replay fixtures from the Gemma spike (run 3b: schema v2, one naming style, STT-noise transcripts).

    python services/case-svc/tests/fixtures/build_replay.py

Writes replay.json next to this file: for each spike conversation (A Tanaka, B car for a grandchild, C genuine
renovation, D son in trouble) the customer turns and the recorded model output per turn. CI replays these
through `FakeClient`, so the tests are deterministic and need no model.

One recorded output is not schema-valid (D c5: a hypothesis name used as an indicator type; the spike's
"1 of 20"). Constrained decoding cannot produce that, so the builder drops the invalid indicator and marks the
turn `patched`; the unpatched record is kept in `raw_invalid` for the test that checks the service retries.
"""

import json
from pathlib import Path

import jsonschema

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[3]
SPIKE = REPO / "spikes" / "gemma-copilot"
SCHEMA = json.loads((REPO / "schemas" / "copilot-turn.json").read_text())


def main() -> None:
    convs = {c["id"]: c for c in json.loads((SPIKE / "conversations_stt.json").read_text())}
    records = [json.loads(line) for line in (SPIKE / "results" / "v2b-gemma4-12b-t0.0-conversations_stt.jsonl").read_text().splitlines()]
    out: dict = {}
    for conv_id, conv in convs.items():
        out[conv_id] = {"label": conv["label"], "expected": conv["expected"],
                        "customer_turns": [t["customer"] for t in conv["turns"]], "outputs": [], "patched": []}
    for r in records:
        entry = out[r["conv"]]
        output = r["output"]
        try:
            jsonschema.validate(output, SCHEMA)
        except jsonschema.ValidationError:
            entry["patched"].append(r["turn"])
            entry.setdefault("raw_invalid", {})[r["turn"]] = output
            valid_types = set(SCHEMA["$defs"]["indicator_type"]["enum"])
            output = {**output, "indicators": [i for i in output["indicators"] if i["type"] in valid_types]}
            jsonschema.validate(output, SCHEMA)
        entry["outputs"].append(output)
    (HERE / "replay.json").write_text(json.dumps(out, ensure_ascii=False, indent=1) + "\n")
    print({k: (len(v["outputs"]), v["patched"]) for k, v in out.items()})


if __name__ == "__main__":
    main()
