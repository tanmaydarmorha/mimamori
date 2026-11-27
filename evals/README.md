# Evaluations

Measurements behind the claims in the README, deck and pitch. Synthetic data only.

## Copilot quality on Gemini (`copilot/`)

The real case-svc code path (copilot, quote rule, `risk-v1`, ADK investigation agent) with the deployed
model settings (Gemini 2.5 Flash on Vertex AI, thinking off), against the in-memory test stubs for the
other services. Only Vertex AI is called; the cloud demo is not touched.

```bash
MIMAMORI_PROJECT_ID=<project> .venv/bin/python evals/copilot/run_eval.py --runs 3   # about 10 min, about $0.70
```

Conversations: the four spike conversations (Japanese) and three of them in English, plus
`copilot/conversations_new.json`: a coached victim who avoids every obvious keyword, a grandchild
"accident settlement", an English regulator impersonation, and three false-alarm traps (a police-officer
neighbour, a surprise kept "secret", an irritated customer in a hurry). Results: `copilot/results/`.

**2026-11-28, 14 conversations × 3 runs:**

| | |
|---|---|
| Scam conversations paused | **18/18** runs |
| Legitimate conversations paused (false alarms) | **0/24** runs |
| Turns from first scam signal to pause | 0.7 on average; same turn in A, D, G (0.2 after the F fix below) |
| Quotes kept by the word-for-word check | 224/224 |
| Copilot turn, model time | median 1.58 s, p90 2.26 s (198 turns) |
| Investigation agent | median 6.4 s, p90 11.8 s, 8 tools; one finding per case dropped by verification (a list field stated as a single value) |
| Tokens per case | 24.5k in / 3.3k out: **about $0.016 (¥2.3)** at list price |

Gap found, then fixed: in F (grandchild accident, transfer) the pause first came at c5 (secrecy).
The model tagged "his number changed" only as `changed_contact_number` (pressure), not also as
`impersonated_relative`, so no core group fired earlier. One added example in each language's copilot
prompt says that quote is both. **Rerun (same day, 14 × 3):** 18/18 scams paused, 0/24 false alarms,
222/222 quotes; F now pauses at c2, c2, c4; signal-to-pause 0.2 turns on average. `risk-v1` unchanged.
(This rerun shared the Vertex quota with demo runs, so its latencies include 429 retries: use the
first run's timings.)

## Scoring throughput (`load/`)

Pre-transaction scoring through the public web-ui proxy (nginx → scoring → core-bank-mock, Firestore),
small counter transfers from every seeded customer: fully scored, no case, no model.

```bash
.venv/bin/python evals/load/score_load.py --url https://<web-ui> --stages 10,25,50,100 --seconds 45
```

**2026-11-28, one scoring instance (max-instances 1), load generated from a laptop over the internet:**

| Concurrent | Req/s | p50 ms | p95 ms | Scoring's own p50/p95 ms | Errors |
|---|---|---|---|---|---|
| 10 | 54 | 177 | 325 | 42/126 | 0 |
| 25 | 47 | 436 | 838 | 16/34 | 0 |
| 50 | 46 | 994 | 1625 | 15/33 | 0 |
| 100 | 47 | 2077 | 2774 | 16/35 | 0 |

One instance sustains about 47 checks/s (about 170,000 an hour) with no errors; past that, requests
queue for the single worker while scoring's own time stays at about 16 ms.

**Scale-out, same day, scoring max-instances raised to 4 for the test (then set back to 1):**

| Concurrent | Req/s | p50 ms | p95 ms | Scoring's own p50/p95 ms | Errors |
|---|---|---|---|---|---|
| 25 | 59 | 384 | 928 | 241/794 | 0 |
| 50 | 130 | 121 | 1253 | 37/1079 | 0 |
| 100 | 146 | 277 | 2653 | 116/235 | 0 |
| 200 | 142 | 538 | 4978 | 139/203 | 0 |

About 3× the throughput (47 → 146 checks/s) with no code change and no errors. It levels off at about
145/s while scoring's own time rises from 16 to about 130 ms, which points at what scoring calls: the
single-instance core-bank mock (it keeps state in memory, so it can't scale out; a bank's real core
system takes its place). The slow first stage is new instances starting up (each warms the baselines
at start-up).

## Accessibility (`demo/`, `DEMO_AXE=1`)

`DEMO_AXE=1` makes the demo runner check every window with axe-core (WCAG 2.2 AA + best practice) after
each step and write `demo/out/axe-<scenario>-<time>.json`. 2026-11-28, the full hero flow (teller,
phone, analyst; 25 steps): 31 distinct violations before the fixes, **0 after**.
