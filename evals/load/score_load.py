"""Load test of the pre-transaction scoring path on the deployed prototype: web-ui (nginx) -> scoring -> core-bank-mock
and Firestore. Small counter transfers from every seeded customer, so each request is fully scored but opens no case
and calls no model.

    .venv/bin/python evals/load/score_load.py --url https://<web-ui> [--stages 10,25,50,100] [--seconds 45]

Prints one row per concurrency stage: throughput, p50/p95/p99 end-to-end latency, scoring's own latency_ms, errors.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import statistics
import time
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[2]
ACCOUNTS = [a for a in json.loads((ROOT / "seed/bank/accounts.json").read_text())
            if a["account_id"].startswith(("acct-0", "acct-tanaka"))]
PAYEE = {"name_kana": "カ）ミライケンセツ", "relation": "same_bank", "account_id": "acct-co-0001"}


def pct(xs: list[float], p: float) -> float:
    xs = sorted(xs)
    return xs[min(len(xs) - 1, int(p * len(xs)))] if xs else float("nan")


async def stage(client: httpx.AsyncClient, url: str, workers: int, seconds: float, tag: str) -> dict:
    lat, svc, errors, n = [], [], {}, 0
    end = time.monotonic() + seconds

    async def worker(w: int) -> None:
        nonlocal n
        i = 0
        while time.monotonic() < end:
            acct = ACCOUNTS[(w + i) % len(ACCOUNTS)]
            body = {"transfer_id": f"tr-load-{tag}-{w}-{i}", "customer_ref": acct["customer_ref"], "account_id": acct["account_id"],
                    "channel": "counter", "kind": "transfer", "amount_jpy": 300, "payee": PAYEE,
                    "occurred_at": "2026-11-28T11:00:00+09:00"}
            i += 1
            t = time.monotonic()
            try:
                r = await client.post(f"{url}/api/scoring/v1/score", json=body)
                dt = time.monotonic() - t
                if r.status_code == 200:
                    lat.append(dt)
                    svc.append(r.json().get("latency_ms") or 0)
                else:
                    errors[r.status_code] = errors.get(r.status_code, 0) + 1
            except httpx.HTTPError as err:
                errors[type(err).__name__] = errors.get(type(err).__name__, 0) + 1
            n += 1

    began = time.monotonic()
    await asyncio.gather(*(worker(w) for w in range(workers)))
    took = time.monotonic() - began
    return {"workers": workers, "requests": n, "ok": len(lat), "rps": len(lat) / took,
            "p50_ms": pct(lat, .5) * 1000, "p95_ms": pct(lat, .95) * 1000, "p99_ms": pct(lat, .99) * 1000,
            "scoring_p50_ms": statistics.median(svc) if svc else None, "scoring_p95_ms": pct(svc, .95) if svc else None,
            "errors": errors}


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", required=True)
    ap.add_argument("--stages", default="10,25,50,100")
    ap.add_argument("--seconds", type=float, default=45)
    ap.add_argument("--tag", default=str(int(time.time())))
    args = ap.parse_args()
    limits = httpx.Limits(max_connections=500, max_keepalive_connections=500)
    async with httpx.AsyncClient(timeout=30, limits=limits) as client:
        rows = []
        for w in map(int, args.stages.split(",")):
            row = await stage(client, args.url.rstrip("/"), w, args.seconds, f"{args.tag}-{w}")
            rows.append(row)
            print(json.dumps(row), flush=True)
    print("\n| Concurrent | Req/s | p50 ms | p95 ms | p99 ms | Scoring p50/p95 ms | Errors |\n|---|---|---|---|---|---|---|")
    for r in rows:
        print(f"| {r['workers']} | {r['rps']:.0f} | {r['p50_ms']:.0f} | {r['p95_ms']:.0f} | {r['p99_ms']:.0f} | "
              f"{r['scoring_p50_ms']}/{r['scoring_p95_ms']} | {r['errors'] or 0} |")


if __name__ == "__main__":
    asyncio.run(main())
