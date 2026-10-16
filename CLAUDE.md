# Mimamori: instructions for Claude Code sessions

You are working in the Mimamori monorepo. The build plan is
[`docs/plans/build-kickoff.md`](docs/plans/build-kickoff.md): read **Shared rules** and your own
**Agent** section there. **`docs/decisions.md` overrides everything else**; if a requirement seems to
conflict with it, stop and report. The endpoint contracts are
[`docs/architecture/api-contracts.md`](docs/architecture/api-contracts.md). Don't change
`libs/mimamori-common`, `schemas/`, `seed/` or the contracts yourself: report what you need.

## Shared rules (repeated from the kickoff)

- **Synthetic data only.** Python 3.12, FastAPI, Pydantic v2, `pytest`, plain `pip` + `venv` (no `uv`).
  Web UI: React + TypeScript + Vite behind nginx.
- Import models, rules, config, stores, model and speech clients from `mimamori_common`; never redefine them.
- Region from `MIMAMORI_REGION`, never hard-coded. No secrets or service-account keys in the repo.
- **Data boundary:** only `scoring` and `case-svc` touch `case-db`. `conversation-svc` never reads it and
  gets only the contact brief. Gemini never sees customer records.
- **Models only suggest.** Code verifies quotes and facts, computes risk and the pause (`risk-v1`), and fills
  every word a teller reads or a contact hears from an approved bank or template. No probability numbers in any UI.
- **Constrained decoding** on every structured model call. **Untrusted text** (payee names, memos,
  transcripts, alert prose) goes in a delimited data block (`mimamori_common.llm.data_block`), never in instructions.
- **A human decides** every pause, release, police summary and freeze; log who and why.
- **No Gemini Live API.** Voice is STT → text model → templates → rule check → TTS.
- **Local first:** runs and passes tests with no GCP (in-memory stores, Ollama, `FakeClient`, typed speech).

## Layout of a deployable

`services/<name>/` or `jobs/<name>/` with `README.md`, `pyproject.toml` (or `package.json`), `tests/`,
`Dockerfile`. Container listens on `$PORT` (default 8080), `GET /healthz`; jobs exit 0 on success.
**Docker build context is the repo root**; `COPY` only what you need:

```dockerfile
FROM python:3.12-slim
WORKDIR /app
COPY libs/mimamori-common/ libs/mimamori-common/
RUN pip install --no-cache-dir "./libs/mimamori-common[web,cloud]"
COPY services/<name>/ services/<name>/
RUN pip install --no-cache-dir ./services/<name>
COPY schemas/ schemas/        # only if you load schema files at runtime
COPY seed/ seed/              # only if you read the seed (core-bank-mock)
ENV PORT=8080
CMD ["sh", "-c", "uvicorn <module>:app --host 0.0.0.0 --port $PORT"]
```

## CI: one workflow per deployable (`.github/workflows/ci-<name>.yml`)

`paths:` must list exactly what the Dockerfile copies (add `schemas/**` / `seed/**` only if copied).
**Use block style for `concurrency:` and `with:`**: `${{ }}` inside a one-line `{...}` is invalid YAML.

```yaml
name: ci-<name>
on:
  push:
    branches: [main]
    paths: [<folder>/**, libs/mimamori-common/**, .github/workflows/ci-<name>.yml, .github/workflows/_build-deploy.yml]
  pull_request:
    paths: [<same list>]
  workflow_dispatch:
concurrency:
  group: ci-<name>-${{ github.ref }}
  cancel-in-progress: true
jobs:
  ci:
    uses: ./.github/workflows/_build-deploy.yml
    with:
      name: <name>
      path: <folder>
      kind: service   # or: job
    secrets: inherit
```

## Working here

```bash
source .venv/bin/activate         # created at the repo root; pip install -e "libs/mimamori-common[web,dev]"
python -m pytest libs/mimamori-common/tests
```

Work only in your folder and your workflow file. Commit on `feat/<name>`. Report: what you built, how
to run it, test results, and any change you need in `libs/`, `schemas/` or another service's API.
