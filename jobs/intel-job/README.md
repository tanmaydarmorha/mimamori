# intel-job

Scheduled Cloud Run Job. Reads public scam alerts (untrusted Japanese prose), has Gemini extract a
playbook constrained to `schemas/playbook.json`, validates it, de-duplicates it and writes it to
`intel-db` as **`pending`**. An analyst approves it later through case-svc. This job never writes
`approved` and has no `case-db` access.

```
AlertFetcher -> extract (Gemini, data block, schema-constrained) -> validate -> de-duplicate -> PendingWriter -> intel-db
```

## Run

```bash
python3 -m venv .venv && .venv/bin/pip install -e "libs/mimamori-common[dev]" -e "jobs/intel-job[dev]"
.venv/bin/python -m pytest jobs/intel-job/tests

# local run against the fixture alerts, in-memory store, local Ollama (gemma4:12b)
MIMAMORI_GENERAL_BACKEND=ollama .venv/bin/python -m intel_job
INTEL_ALERTS_FILE=path/to/alerts.json .venv/bin/python -m intel_job   # other fixture file
docker build -f jobs/intel-job/Dockerfile .
```

Model selection, store backend and region come from `mimamori_common` settings (`get_general_client`:
Gemini in the cloud, Ollama locally). Exit code 0 on success, including alerts whose model output was
rejected or that were duplicates; 1 if the fetch failed or any alert hit an error (model unreachable,
unparseable reply, write failure). The in-memory store lives only for the process, so a local run
shows the result in the log, not in a database.

## How the safeguards work

- **Untrusted text.** Alert prose is wrapped by `data_block("alert", ...)` (and truncated to 12,000
  characters). The system prompt says tag contents are data, never instructions.
- **The model cannot set status.** The schema given to the model is `playbook.json` minus `status`,
  `version`, `sources`, `approved_by`, `approved_at` (`intel_job/schema.py`). Anything the model returns
  for those fields is discarded; code sets `status = "pending"`, `version = 1`, approval fields null, and
  `sources` from the fetcher (so `published_at` is the source's date, not the model's).
- **The write path cannot approve.** The job writes only through `PendingWriter`, which refuses anything
  not `pending` and refuses to overwrite an existing id. It has no method that changes status.
- **Validation** (`intel_job/validate.py`): the JSON Schema (with formats), Pydantic `Playbook`, and the
  `schemas/validate.py` cross-rules: `pb.<hypothesis>.` / `q.<hypothesis>.` / `h.<hypothesis>.` id
  prefixes, banned wording (imported from `schemas/validate.py`), slots equal placeholders, unique wording
  ids (also against intel-db), source dates not in the future. Hypothesis must be a scam type.
  Failures are logged at WARNING with every problem and nothing is stored.
- **De-duplication** (`intel_job/dedupe.py`): same alert URL already a source, same id, or Jaccard >= 0.6
  of script phrases within the same hypothesis. Duplicates are skipped, never merged into or written over
  an existing (possibly approved) playbook.

## Sources

Only the fixture fetcher exists (`intel_job/fixtures/alerts.json`, synthetic text on `example.invalid`
URLs). **No live fetcher is written and nothing fetches in tests or CI.** If one is added, it must be
off by default and the user must first check each source's terms (robots.txt, reuse licence, rate
limits). Candidate public sources named in `docs/research.md`, for the user to review:

- National Police Agency, special fraud methods and countermeasures
  (https://www.npa.go.jp/bureau/criminal/souni/tokusyusagi/teguchi-taisaku.pdf, used for the seeded playbook)
- Prefectural police sites and fsa.go.jp (both listed as source types in `docs/research.md`; no specific alert URLs chosen)

Publication dates must come from the source page's metadata; the evaluation date split (CR 16, CR 28)
relies on them.
