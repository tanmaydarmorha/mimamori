"""Copilot evaluation on Gemini: the real case-svc code path (copilot, quote rule, risk-v1, investigation agent) with
the deployed model settings, against the in-memory test stubs for the other services. Nothing in the cloud demo is
touched; only Vertex AI is called.

    MIMAMORI_PROJECT_ID=<project> .venv/bin/python evals/copilot/run_eval.py [--runs 3] [--only A,E]

Writes evals/copilot/results/<timestamp>.jsonl (one line per turn) and prints the summary table.
"""

from __future__ import annotations

import argparse
import json
import os
import statistics
import sys
import time
from dataclasses import replace
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "services/case-svc/tests"))

from fastapi.testclient import TestClient  # noqa: E402

from mimamori_common.config import Settings  # noqa: E402
from mimamori_common.llm import _build  # noqa: E402
from mimamori_common.store import reset_memory_stores  # noqa: E402

from case_svc.app import create_case_app  # noqa: E402
from case_svc.config import SvcConfig  # noqa: E402
from case_svc.deps import build_deps  # noqa: E402

from conftest import DEMO_NOW, HERO_SIGNALS, REPLAYS, SCENARIOS, STAFF, Env  # noqa: E402
from fakes import FakeBank, FakeConversation, FakeScoring, compute_baseline  # noqa: E402

HERE = Path(__file__).parent
SETUPS = {**SCENARIOS,
          "D_transfer": dict(customer_ref="cust-0010", account_id="acct-0010", payee_account="acct-mule-0001", amount=2_000_000)}
PAYEE_SIGNALS = [s for s in HERO_SIGNALS if s["tool"] == "counterpart_graph"]


class Timed:
    """Wraps the model client to record each call's latency."""

    def __init__(self, inner):
        self.inner, self.name, self.calls, self.tokens = inner, inner.name, [], []
        post = inner._rest.post

        async def counted(url, body, info):  # keep Vertex's usageMetadata for the cost estimate
            data, seconds = await post(url, body, info)
            u = data.get("usageMetadata", {})
            self.tokens.append((u.get("promptTokenCount", 0), u.get("candidatesTokenCount", 0)))
            return data, seconds

        inner._rest.post = counted

    async def generate_json(self, system, user, schema, **kw):
        t = time.monotonic()
        res = await self.inner.generate_json(system, user, schema, **kw)
        self.calls.append(time.monotonic() - t)
        return res

    async def generate_text(self, system, user, **kw):
        t = time.monotonic()
        res = await self.inner.generate_text(system, user, **kw)
        self.calls.append(time.monotonic() - t)
        return res


def conversations() -> list[dict]:
    spike = {c["id"]: c for c in json.loads((ROOT / "spikes/gemma-copilot/conversations.json").read_text())}
    signal_turn = {"A": 4, "D": 2}
    out = []
    for lang, recs in REPLAYS.items():
        for cid, rec in recs.items():
            expected = spike[cid]["expected"]
            out.append({"id": cid if lang == "ja" else f"{cid}-en", "language": lang, "setup": cid,
                        "signals": "hero" if cid == "A" else "none", "expected": "legitimate" if expected == "legitimate" else "scam",
                        "signal_turn": signal_turn.get(cid), "label": spike[cid]["label"],
                        # the spike's clean transcript, not the replay fixture's simulated speech-to-text noise
                        "customer_turns": [t["customer"] for t in spike[cid]["turns"]] if lang == "ja" else rec["customer_turns"]})
    return out + json.loads((HERE / "conversations_new.json").read_text())


def make_env(model) -> tuple[Env, TestClient]:
    reset_memory_stores()
    settings = replace(Settings.from_env(), demo_now=DEMO_NOW, service_name="case-svc")
    bank = FakeBank(settings.now())
    conv, scoring = FakeConversation(), FakeScoring(bank)
    cfg = SvcConfig(investigation_inline=True, case_code="4821")
    deps = build_deps(settings, cfg, copilot=model, investigator=model, core_transport=bank.transport,
                      scoring_transport=scoring.transport, conversation_transport=conv.transport)
    client = TestClient(create_case_app(deps))
    client.__enter__()
    for ref in ("cust-tanaka-0001", "cust-0005", "cust-0008", "cust-0010"):
        deps.store.repo.put_baseline(ref, compute_baseline(bank, ref).model_dump(mode="json"))
    return Env(client, deps, bank, conv, scoring, model, model), client


def run_one(conv: dict, model: Timed, run: int) -> list[dict]:
    env, client = make_env(model)
    try:
        signals = {"hero": HERO_SIGNALS, "payee": PAYEE_SIGNALS, "none": []}[conv["signals"]]
        model.calls.clear()
        model.tokens.clear()
        case_id = env.open_case(signals=signals, transfer_id=f"tr-eval-{conv['id']}-{run}", **SETUPS[conv["setup"]])
        inv_calls, inv_seconds = len(model.calls), sum(model.calls)
        inv_tokens = list(model.tokens)
        if conv["language"] != "ja":
            r = client.patch(f"/cases/{case_id}/language", json={"language": conv["language"], "actor": "teller-sato"}, headers=STAFF)
            assert r.status_code == 200, r.text
        state = env.deps.store.state(case_id)
        rows = []
        for i, text in enumerate(conv["customer_turns"], 1):
            before = len(model.calls)
            resp = client.post(f"/cases/{case_id}/turns", json={"speaker": "customer", "text": text})
            ok = resp.status_code == 200
            card = resp.json().get("card") if ok else None
            state = env.deps.store.state(case_id)
            rows.append({"conv": conv["id"], "run": run, "turn": i, "ok": ok, "status": resp.status_code,
                         "level": card["risk"]["level"] if card else None,
                         "pause": bool(card and card["risk"]["pause_recommended"]),
                         "fired": [f["condition"] for f in card["risk"]["fired"]] if card else [],
                         "indicators": len(state["indicators"]),
                         "quote_drops": sum(1 for d in state["dropped"] if d["reason"] == "quote_not_found"),
                         "hypothesis": state.get("leading_hypothesis"),
                         "seconds": sum(model.calls[before:]),
                         "inv_calls": inv_calls if i == 1 else None, "inv_seconds": inv_seconds if i == 1 else None,
                         "inv_status": state.get("investigation", {}).get("status") if i == 1 else None,
                         "inv_drops": sum(1 for d in state["dropped"] if d["reason"] != "quote_not_found") if i == 1 else None,
                         "error": None if ok else resp.text[:300]})
        quotes_total = sum(1 for _ in state["indicators"]) + rows[-1]["quote_drops"]
        rows[-1]["quotes_total"] = quotes_total
        rows[-1]["tokens_investigation"] = [sum(t[0] for t in inv_tokens), sum(t[1] for t in inv_tokens)]
        rows[-1]["tokens_case"] = [sum(t[0] for t in model.tokens), sum(t[1] for t in model.tokens)]
        return rows
    finally:
        client.__exit__(None, None, None)


def summarise(convs: list[dict], rows: list[dict], runs: int) -> str:
    by = {}
    for r in rows:
        by.setdefault((r["conv"], r["run"]), []).append(r)
    lines = ["| Conv | Expected | Label | Paused (runs) | First pause turn | Signal turn |", "|---|---|---|---|---|---|"]
    tp = fn = fp = tn = 0
    delays = []
    for c in convs:
        firsts = []
        for run in range(1, runs + 1):
            turns = by.get((c["id"], run), [])
            first = next((t["turn"] for t in turns if t["pause"]), None)
            firsts.append(first)
            if c["expected"] == "scam":
                tp, fn = tp + (first is not None), fn + (first is None)
                if first is not None and c["signal_turn"]:
                    delays.append(first - c["signal_turn"])
            else:
                fp, tn = fp + (first is not None), tn + (first is None)
        paused = sum(f is not None for f in firsts)
        lines.append(f"| {c['id']} | {c['expected']} | {c['label']} | {paused}/{runs} | "
                     f"{', '.join('-' if f is None else f'c{f}' for f in firsts)} | {'c' + str(c['signal_turn']) if c['signal_turn'] else '-'} |")
    turn_secs = [r["seconds"] for r in rows if r["ok"]]
    inv = [r for r in rows if r["inv_calls"] is not None]
    errors = [r for r in rows if not r["ok"]]
    kept = sum(r.get("quotes_total", 0) - r["quote_drops"] for r in rows if "quotes_total" in r)
    total = sum(r.get("quotes_total", 0) for r in rows if "quotes_total" in r)
    q = lambda xs, p: sorted(xs)[min(len(xs) - 1, int(p * len(xs)))]  # noqa: E731
    lines += ["",
              f"- Scam conversations paused: **{tp}/{tp + fn}** runs; legitimate conversations paused (false alarms): **{fp}/{fp + tn}** runs",
              f"- Turns from first scam signal to pause recommendation: {statistics.mean(delays):.1f} on average (0 = same turn)" if delays else "- no delays",
              f"- Quotes kept by the word-for-word check: {kept}/{total}",
              f"- Copilot turn model time: median {statistics.median(turn_secs):.2f} s, p90 {q(turn_secs, 0.9):.2f} s ({len(turn_secs)} turns)",
              f"- Investigation: median {statistics.median([r['inv_seconds'] for r in inv]):.1f} s, "
              f"{statistics.mean([r['inv_calls'] for r in inv]):.1f} model calls; agent status {sorted({r['inv_status'] for r in inv})}; "
              f"findings dropped by verification: {sum(r['inv_drops'] for r in inv)}",
              f"- Failed turns (HTTP errors): {len(errors)}"]
    cases = [r["tokens_case"] for r in rows if "tokens_case" in r]
    if cases:
        tin, tout = statistics.mean(c[0] for c in cases), statistics.mean(c[1] for c in cases)
        # Gemini 2.5 Flash list price on Vertex AI (USD per 1M tokens): input 0.30, output 2.50
        usd = tin * 0.30 / 1e6 + tout * 2.50 / 1e6
        lines.append(f"- Tokens per case (investigation + all copilot turns): {tin:,.0f} in / {tout:,.0f} out, "
                     f"about ${usd:.4f} (¥{usd * 150:.1f}) at list price")
    return "\n".join(lines)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--runs", type=int, default=3)
    ap.add_argument("--only", default="")
    args = ap.parse_args()
    os.environ.setdefault("MIMAMORI_GEMINI_THINKING_BUDGET", "0")
    settings = Settings.from_env()
    model = Timed(_build("gemini", settings))
    convs = [c for c in conversations() if not args.only or c["id"] in args.only.split(",")]
    out = HERE / "results" / f"{datetime.now():%Y%m%d-%H%M%S}.jsonl"
    out.parent.mkdir(exist_ok=True)
    rows = []
    with out.open("w") as f:
        for run in range(1, args.runs + 1):
            for c in convs:
                got = run_one(c, model, run)
                rows += got
                for r in got:
                    f.write(json.dumps(r, ensure_ascii=False) + "\n")
                print(f"run {run} {c['id']}: {' '.join(('P' if r['pause'] else (r['level'] or 'ERR')[0].upper()) for r in got)}", flush=True)
    summary = summarise(convs, rows, args.runs)
    (out.with_suffix(".md")).write_text(f"Model: {model.name}, thinking budget {settings.gemini_thinking_budget}, "
                                        f"region {settings.gemini_location or settings.region}, {args.runs} runs\n\n{summary}\n")
    print(summary)


if __name__ == "__main__":
    main()
