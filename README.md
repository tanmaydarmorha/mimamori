# Mimamori 見守り

A prototype counter copilot and family-call assistant for transfer-fraud prevention at a Japanese
bank. **All data is synthetic.** Decisions: [`docs/decisions.md`](docs/decisions.md) (overrides the
PDF). Architecture: [`docs/architecture/`](docs/architecture/). Docs index: [`docs/README.md`](docs/README.md).

## Layout

| Path | What |
|---|---|
| `libs/mimamori-common/` | Shared models, rules (`risk-v1`), config, stores, model and speech clients |
| `services/core-bank-mock/` | Mock core banking (external system) |
| `services/scoring/` | Baselines, smart limits, counterpart graph, watchlist match. No LLM |
| `services/case-svc/` | Counter copilot, investigation agent, decisions, brief builder, approvals |
| `services/conversation-svc/` | Notice, verified callback, intent → templates → rule check |
| `services/web-ui/` | Teller console, analyst console, simulated phone |
| `jobs/watchlist-loader/`, `jobs/intel-job/`, `jobs/sim-job/` | Scheduled / on-demand jobs |
| `schemas/` | JSON Schema data contracts + examples (`python schemas/validate.py`) |
| `seed/` | Synthetic seed data and loader |
| `spikes/gemma-copilot/` | The step-0 Gemma spike and its recorded outputs |
| `docs/` | Decisions, architecture (C4 + [API contracts](docs/architecture/api-contracts.md)), plans, reviews |
| `infra/` | What a cloud deploy needs (nothing is created) |

## Run locally (no GCP)

Needs Python 3.12, Docker, and Ollama with `gemma4:12b` (`ollama serve`, `ollama pull gemma4:12b`).

One command for the whole stack: `scripts/dev.sh up` (Gemini on Vertex, needs
`gcloud auth application-default login`), or `scripts/dev.sh up --local` (Ollama, no GCP).
`scripts/dev.sh down` stops it; `status` and `logs` help when something fails. By hand:

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -e "libs/mimamori-common[dev]"
python -m pytest libs/mimamori-common/tests        # shared lib
python schemas/validate.py                         # schemas and examples

docker compose up -d firestore                     # Firestore emulator on :8086
docker compose run --rm seed                       # load case-db, intel-db, ref-db
docker compose up --build                          # every deployable that exists
```

Each deployable builds from the **repo root**: `docker build -f services/<name>/Dockerfile .`.
Open the teller console at http://localhost:8080 and the simulated phone at http://localhost:8080/phone.
A scripted, narrated demo of the whole flow (with video recording) is in [`demo/README.md`](demo/README.md): `scripts/demo.sh all --fresh`.
In-process (tests): `MIMAMORI_STORE=memory` (default), `MIMAMORI_COPILOT_BACKEND=fake`, `MIMAMORI_SPEECH=typed`.

## How the build is organised

[`docs/plans/build-kickoff.md`](docs/plans/build-kickoff.md): Phase 0 (shared foundation, on `main`),
then one branch and pull request per deployable.
