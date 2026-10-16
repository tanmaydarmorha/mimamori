# case-svc

The case service: counter copilot, investigation agent, decisions and holds, police summary, family-call
brief, analyst approvals. Contract: [`docs/architecture/api-contracts.md`](../../docs/architecture/api-contracts.md).
Only this service and Scoring open `case-db`; it reads approved playbooks from `intel-db` and writes a
playbook's status only through the analyst endpoint.

## Run

```bash
python3 -m venv .venv && .venv/bin/pip install -e "libs/mimamori-common[web,dev]" -e "services/case-svc[dev]"
.venv/bin/python -m pytest services/case-svc/tests                 # deterministic, no GCP, no model
.venv/bin/python -m pytest services/case-svc/tests -m ollama -s     # manual: real gemma4:12b via Ollama (30-100 s per turn)
PORT=8083 .venv/bin/uvicorn --factory case_svc.app:create_case_app --port 8083
docker build -f services/case-svc/Dockerfile . && docker run -p 8083:8080 <image>
```

Local mode seeds the in-memory stores at startup (`CASE_SVC_SEED_ON_START=0` to skip). Other env vars:
`MIMAMORI_CASE_CODE` (fixed 4-digit code for the demo, random per call if unset), `CASE_SVC_INVESTIGATION=0`,
`CASE_SVC_INVESTIGATION_MAX_STEPS` (default 10; a run normally takes 2 model calls, the limit is a safety net), `MIMAMORI_GEMINI_THINKING_BUDGET` (shared with conversation-svc; default 0 = thinking off for Gemini, `-1` = model default), `CASE_SVC_POLICY_*` (bank-policy hold window: 4 h, extend, cap 24 h),
`CASE_SVC_CONTACT_PHONE_CHANGE_DAYS` (30), `MIMAMORI_REFERENCE_JA` (JSON, customer ref to "お母様"). Shared settings
(model backends, URLs, region, demo clock) are `mimamori_common.config`.

## How it works

| Module | Does |
|---|---|
| `copilot.py` | One schema-constrained model call per customer turn (`copilot-turn.json`, prompt `prompts/copilot_system_v2.md` = spike v2 plus a data-block line), then code: quote rule, accumulation, `risk-v1`, bank wording. Already-suggested questions are removed from the bank the model sees; an unknown ID falls back to `q.general.purpose` and is logged and audited. |
| `card.py` | The evidence card is derived from internal state (`case_state`), so claim IDs are stable. Fact text for known tool fields is written by code. |
| `investigation/` | Google ADK `LlmAgent` + `InMemoryRunner` over a `BaseLlm` adapter around our `ModelClient` (works offline: no credentials, no network but Ollama/Vertex Gemma). Eight read-only tools return computed counts. `verify.py` checks every fact against its tool field and drops ungrounded ones (`no_citation`, `value_mismatch`, `ungrounded_inference`). Alert signals are re-checked by code. |
| `decisions.py` | Pause / release with basis and rationale. Wishes basis: hold carries the wishes' overrides; a plain release before `ends_at` is refused. Bank-policy basis: `overrides: []`. Single-source pause allowed with a logged warning. Everything audited with who and why. |
| `contact.py` | Contact-suspected checks, brief built in code, case code, `POST /calls`, outcome. |
| `analyst.py` | Freeze request/decision (analyst role), playbook approval, wishes freeze during an open case (DA 12). |

## Additions beyond the contract table

`POST /cases/{id}/notes` (teller notes; `contact_flagged` feeds the contact check), `POST /cases/{id}/police-notified`
(so the brief can say police were notified), `GET /cases/{id}/events?follow=false` (replay then close, for tests and curl).
`get_baseline` asks Scoring (`POST /v1/baselines/{ref}/refresh`) when `case-db` has no baseline (one process per service).
`check_lists` reads the latest `ref-db` snapshot read-only.


## Logs

INFO lines: one per model call (`model call model=… kind=json|text seconds=… attempts=…`, from `mimamori_common.llm`) and one when an investigation ends (`investigation done case=… model_calls=… tools=… seconds=…`).
