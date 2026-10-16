# sim-job

Simulation job (Cloud Run Job, **synthetic-only environment**, no `case-db` grant). It seeds synthetic
customers, role-plays counter conversations through case-svc's API, runs a **three-way evaluation**, and
writes one Markdown report: per-arm synthetic results with an explicit circularity note, and a
case-by-case failure analysis on public fake-police cases published after T = 2026-04-01.

Decisions it implements: `docs/decisions.md` Evaluation row, CR 6, 7, 16, 19, 28; research R1, R2.

## The three arms (one teller assumption for all)

| Arm | What it is | Flag that makes the teller pause |
|---|---|---|
| (a) today's counter check | NPA request to speak to high-value customers + Akita five-step routine + Okayama practice (research R1). Four approved questions (purpose, who asked, on the phone now, documents). **Amount threshold is a stated parameter** (`--threshold`, default ¥1,000,000, swept in the report); the age trigger is not modelled. | A published red flag heard in an answer (lexicon in `arm_a.py`, printed in the report) |
| (b) statistics only | Scoring alone, via `POST /transfers` on core-bank-mock | `scoring == "alert"` |
| (c) full Mimamori | Same `POST /transfers`; on alert Scoring opens a case; case-svc copilot per customer turn, code computes risk-v1 | `card.risk.pause_recommended` |

**Shared teller behaviour** (`teller.py`, `SimParams`): the teller asks the arm's questions (max 6), pauses
at the first raised flag if they act on flags (`--follow-p`, default 1.0; one per-scenario draw reused by
every arm), otherwise carries on, and clears and releases if nothing pauses. Every sim pause is posted to
case-svc with a rationale (a human decides, logged).

## Data

- **Synthetic set** (`scenarios.py`): 12 scam + 12 legitimate counter transactions. Spike conversations
  A-D are reused (customer lines only, keyed by question purpose so any approved question gets an answer).
  Ground truth is our own label: see the circularity note in the report.
- **Held-out set** (`data/heldout_cases.json`): the 11 narrative-rich fake-police cases research.md R2 found
  after T (9 replayable). **Fewer than the 20 targeted: R2b has not been done**, and the report says so.
  Each runnable case is replayed three ways (candid / coached / coached-papers; the NPA says coaching
  defeats today's check). Every assumption needed to replay a case is stored with the case and printed in the
  report. Reported as case-by-case failure analysis, never as rates.
- **Date split** (`heldout.py`): before any run, the approved playbooks are fetched from case-svc
  (`GET /playbooks?status=approved`) and every source `published_at` must be before T, none may cite a
  held-out case's URL. A violation exits 3 and nothing is run.
- **Judge** (`judge.py`): a separate prompt via `get_general_client` (Gemini in the cloud, Ollama locally).
  Rubric: decision reasonable on the transcript, missed red flags, wording problems. Outcomes (caught,
  missed, yen) are computed by code from the label.

## Run it

```bash
python3 -m venv .venv && .venv/bin/pip install -e "libs/mimamori-common[dev]" -e "jobs/sim-job[dev]"
.venv/bin/python -m pytest jobs/sim-job/tests

# 1. Pipeline check, no services needed. Uses in-package FAKE core-bank and case-svc: numbers are meaningless.
.venv/bin/python -m sim_job run --fake-services --out sim-report.md

# 2. Real evaluation. core-bank-mock's API is read-only, so the sim hands the services an extended seed.
.venv/bin/python -m sim_job seed --out /tmp/sim-seed
MIMAMORI_SEED_DIR=/tmp/sim-seed MIMAMORI_DEMO_NOW=2026-10-13T11:42:00+09:00 \
  docker compose up core-bank-mock scoring case-svc        # e.g.; fresh containers for every run, same seed dir for all three
MIMAMORI_GENERAL_BACKEND=ollama .venv/bin/python -m sim_job run --out sim-report.md
```

`--roleplay llm` replaces the scripted customers with the general model (not repeatable). `--judge off|fake|general`.
`--no-heldout` skips the held-out set. Exit codes: 0 report written, 2 services unreachable, 3 date split violated.
In the container the report goes to the job log (`--out -`).

Services read `MIMAMORI_SEED_DIR` and the demo clock. Customers are read from the seed at start, so restart
the services after `sim-job seed`, and use fresh containers per run (transfers, cases and holds are stateful).

## Layout

```
src/sim_job/  params, teller (shared assumption), personas (role-play), scenarios, seedgen, arm_a, arm_bc,
              clients (httpx, contract models), judge, runner, report, heldout, fakes, cli
data/heldout_cases.json   cases from research.md R2 with provenance and per-case assumptions
tests/        no network: fake ASGI services and FakeClient
```

## Not verified

Against the real core-bank-mock, scoring and case-svc (they live on other branches): the clients follow
`api-contracts.md` and validate responses with the shared models, and the fakes are built from the same
document, so a contract mismatch will show up as a `ServiceError` or validation error on the first live run.
No run with a real model (Ollama, Gemini) has been done. See the report's "Limits" section for the
evaluation's own limits.
