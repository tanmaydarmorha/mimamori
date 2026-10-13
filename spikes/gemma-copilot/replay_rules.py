"""Replay recorded copilot outputs through the code-side rules (rules.py). No model calls.

Usage: python replay_rules.py results/<run>.jsonl conversations.json
"""

import json
import sys

from rules import assess_risk, merge_indicators, verify_quotes


def main(results_path, conversations_path):
    convs = {c["id"]: c for c in json.load(open(conversations_path))}
    card = {}
    print(f"{'turn':6} {'model pause':12} {'rule level':10} {'rule pause':10} fired / quote fixes")
    for line in open(results_path):
        r = json.loads(line)
        if not r.get("output"):
            print(f"{r['conv']} {r['turn']:3}  (no output)")
            continue
        conv = convs[r["conv"]]
        n = int(r["turn"][1:])
        turns = {f"c{i}": t["customer"] for i, t in enumerate(conv["turns"][:n], start=1)}
        kept, dropped = verify_quotes(r["output"].get("indicators", []), turns)
        card[r["conv"]] = merge_indicators(card.get(r["conv"], []), kept)
        risk = assess_risk(card[r["conv"]], r["output"].get("cover_story", {}), conv["facts"])
        notes = [f"moved {k['quote'][:12]}… to {k['turn_id']}" for k in kept if k["turn_id_corrected"]]
        notes += [f"dropped {d['quote'][:12]}…" for d in dropped]
        model_pause = r["output"].get("recommend_pause", "-")
        print(f"{r['conv']} {r['turn']:3}  {str(model_pause):12} {risk['level']:10} {str(risk['pause_recommended']):10} {', '.join(risk['fired'])} {'; '.join(notes)}")


if __name__ == "__main__":
    main(*sys.argv[1:3])
