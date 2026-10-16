"""The ported rules must give the same decisions on the recorded spike outputs as the spike did
(schemas/README.md: no pause on any legitimate turn, Tanaka pauses at c4 in every run)."""

import json

import pytest

from mimamori_common.rules import RULE_VERSION, assess_risk, merge_indicators, verify_quotes

from .conftest import SPIKE, load_json

# (results file, conversations file): runs 1, 2, 3 and 3b of spikes/gemma-copilot/RESULTS.md
RUNS = {
    "run1": ("gemma4-12b-t0.0.jsonl", "conversations.json"),
    "run2": ("gemma4-12b-t0.0-conversations_stt.jsonl", "conversations_stt.json"),
    "run3": ("v2-gemma4-12b-t0.0-conversations_stt.jsonl", "conversations_stt.json"),
    "run3b": ("v2b-gemma4-12b-t0.0-conversations_stt.jsonl", "conversations_stt.json"),
}
EXPECTED = {"A": "scam", "B": "legitimate", "C": "legitimate", "D": "scam"}


def replay(run):
    results, conversations = RUNS[run]
    convs = {c["id"]: c for c in load_json(SPIKE / conversations)}
    cards: dict[str, list] = {}
    pauses: dict[str, list[str]] = {}
    for line in (SPIKE / "results" / results).read_text().splitlines():
        rec = json.loads(line)
        if not rec.get("output"):
            continue
        conv = convs[rec["conv"]]
        n = int(rec["turn"][1:])
        turns = {f"c{i}": t["customer"] for i, t in enumerate(conv["turns"][:n], start=1)}
        kept, _ = verify_quotes(rec["output"].get("indicators", []), turns)
        cards[rec["conv"]] = merge_indicators(cards.get(rec["conv"], []), kept)
        risk = assess_risk(cards[rec["conv"]], rec["output"].get("cover_story", {}), conv["facts"])
        assert risk["rule_version"] == RULE_VERSION
        assert risk["pause_recommended"] == (risk["level"] == "high")
        if risk["pause_recommended"]:
            pauses.setdefault(rec["conv"], []).append(rec["turn"])
    return pauses


@pytest.mark.parametrize("run", RUNS)
def test_tanaka_pauses_at_c4(run):
    assert replay(run)["A"][0] == "c4"


@pytest.mark.parametrize("run", RUNS)
def test_no_pause_on_any_legitimate_turn(run):
    pauses = replay(run)
    assert "B" not in pauses and "C" not in pauses


@pytest.mark.parametrize("run", RUNS)
def test_son_in_trouble_pauses_at_c3_or_c4(run):
    assert replay(run)["D"][0] in {"c3", "c4"}


def test_pause_never_lifts_once_fired():
    """Accumulation: after the first pause, later turns stay high (the spike's flicker is gone)."""
    for run in RUNS:
        for conv, turns in replay(run).items():
            numbers = [int(t[1:]) for t in turns]
            assert numbers == list(range(numbers[0], numbers[-1] + 1)), (run, conv, turns)
