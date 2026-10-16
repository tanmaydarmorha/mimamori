# mimamori-common

Shared code for every deployable: import it, never redefine it.

```bash
pip install -e "libs/mimamori-common[dev]"        # local + tests (no GCP)
pip install -e "libs/mimamori-common[web]"        # + FastAPI scaffolding (services)
pip install -e "libs/mimamori-common[cloud]"      # + Firestore, Cloud STT/TTS, google-auth
python -m pytest libs/mimamori-common/tests
```

| Module | What |
|---|---|
| `models` | Pydantic v2 models. `models/generated/` is **generated from `schemas/*.json`** (`python libs/mimamori-common/scripts/generate_models.py`; CI fails on drift, never hand-edit). `models/api.py` holds the HTTP envelopes ([contracts](../../docs/architecture/api-contracts.md)); `models/baseline.py` the customer baseline and watchlist snapshot. Readable aliases (`EvidenceCard`, `CopilotTurn`, `ContactBrief`, …) are in `models/__init__.py`. |
| `rules` | `verify_quotes`, `merge_indicators`, `assess_risk`, `RULE_VERSION = "risk-v1"`: the spike's `rules.py`, unchanged in behaviour. Regression-tested against the recorded spike outputs. |
| `config` | `Settings.from_env()`: the only place defaults live. `Settings.now()` honours `MIMAMORI_DEMO_NOW`. |
| `store` | `CaseRepo` / `IntelRepo` / `RefRepo` over `InMemoryStore` or `FirestoreStore`. `open_case_repo` refuses services with no `case-db` grant. |
| `llm` | `ModelClient` (`generate_json` constrained to a schema, `generate_text`): `OllamaClient`, `VertexGemmaClient`, `GeminiClient`, `FakeClient`; `data_block()` for untrusted text. |
| `speech` | `SpeechToText` (`TypedInput`, `CloudSttV2`), `TextToSpeech` (`TextOnly`, `CloudTts`). |
| `schemas`, `seed` | Locate and load `schemas/` and `seed/` (env var, `/app/...` in a container, or the repo). |
| `web` | `create_app(name)` (health, CORS) and `caller_role(headers)`. |

## Settings

| Env var | Default | |
|---|---|---|
| `MIMAMORI_REGION` | `asia-south1` | Never hard-code a region. Production: `asia-northeast1`. |
| `MIMAMORI_ENV` | `local` | `cloud` flips the defaults below to Firestore, Vertex Gemma, Gemini, Cloud speech. |
| `MIMAMORI_PROJECT_ID` | | GCP project (cloud only). |
| `MIMAMORI_STORE` | `memory` (`firestore` in cloud) | `FIRESTORE_EMULATOR_HOST` points Firestore at the emulator. |
| `MIMAMORI_CASE_DB` / `_INTEL_DB` / `_REF_DB` | `case-db` / `intel-db` / `ref-db` | Firestore database IDs. |
| `MIMAMORI_SERVICE` | `mimamori` | Service name; used by the `case-db` guard and logs. |
| `CORE_BANK_URL`, `SCORING_URL`, `CASE_SVC_URL`, `CONVERSATION_SVC_URL` | `http://localhost:8081…8084` | |
| `MIMAMORI_COPILOT_BACKEND` | `ollama` (`vertex_gemma` in cloud) | Case service model: `ollama \| vertex_gemma \| gemini \| fake`. |
| `MIMAMORI_GENERAL_BACKEND` | `ollama` (`gemini` in cloud) | Conversation service and jobs: `ollama \| gemini \| fake`. |
| `OLLAMA_URL`, `OLLAMA_MODEL` | `http://localhost:11434`, `gemma4:12b` | |
| `VERTEX_GEMMA_ENDPOINT_ID`, `GEMINI_MODEL`, `MIMAMORI_GEMINI_LOCATION` | | Cloud models. |
| `MIMAMORI_SPEECH` | `typed` (`cloud` in cloud) | `MIMAMORI_STT_MODEL` (`chirp_2`), `MIMAMORI_STT_LANGUAGE` (`ja-JP`). |
| `MIMAMORI_MODEL_MAX_RETRIES` | `4` | Retries of Vertex calls on 429/500/503 and network errors (1, 2, 4, 8 s with jitter; `Retry-After` honoured up to 30 s); all within `MIMAMORI_MODEL_TIMEOUT_S`. |
| `SCORING_TIMEOUT_S`, `LARGE_TRANSFER_THRESHOLD_JPY`, `BUSINESS_DAY_CLOSE` | `0.5`, `1000000`, `15:00` | Core-bank behaviour. |
| `MIMAMORI_DEMO_NOW` | | Fixed demo clock, e.g. `2026-10-13T11:42:00+09:00`. |
| `MIMAMORI_SCHEMAS_DIR`, `MIMAMORI_SEED_DIR` | | Override where `schemas/` and `seed/` are found. |

## Not yet verified against the real services

`VertexGemmaClient`, `GeminiClient`, `CloudSttV2` and `CloudTts` follow the documented REST / gRPC
shapes but have not run against GCP (no project exists yet). `FirestoreStore` was run against the
Firestore emulator (the seed loader and a read-back, named databases included), not real Firestore. The Gemini
default model name, Gemma endpoint request format and Chirp availability in `asia-south1` are open
items from `docs/decisions.md`. `OllamaClient` is exercised by `pytest -m ollama` (manual).
