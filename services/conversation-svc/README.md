# conversation-svc

The family notice and the verified callback. **No `case-db` access**: its only input about a case is
`CallRequest` on `POST /calls` (the contact brief, built in code by case-svc); its only output is
`POST /cases/{id}/contact-outcome` (`contact_view` or `verification_failed`). State is in memory.

Contract: [`docs/architecture/api-contracts.md`](../../docs/architecture/api-contracts.md). Flow:
[`c4-dynamic-tanaka.md`](../../docs/architecture/c4-dynamic-tanaka.md) section C.

## Run

```bash
python3 -m venv .venv && .venv/bin/pip install -e "libs/mimamori-common[web,dev]" -e "services/conversation-svc[dev]"
PORT=8084 CASE_SVC_URL=http://localhost:8083 .venv/bin/uvicorn conversation_svc.main:app --port 8084   # Ollama gemma4:12b, typed speech
.venv/bin/python -m pytest services/conversation-svc/tests            # no GCP, no Ollama
.venv/bin/python -m pytest services/conversation-svc/tests -m ollama  # manual, needs gemma4:12b
docker build -f services/conversation-svc/Dockerfile .                # context = repo root
```

Config is `mimamori_common.config.Settings` (`MIMAMORI_GENERAL_BACKEND=ollama|gemini|fake`,
`MIMAMORI_SPEECH=typed|cloud`, `CASE_SVC_URL`, ...). Service-only knobs: `CONVERSATION_MODEL_TIMEOUT_S`
(15), `CONVERSATION_MAX_TURNS` (20), `CONVERSATION_MAX_FAILED_ATTEMPTS` (3).

## What it does

1. `POST /calls`: stores the call, sends the **notice**: branch, "about your mother", the published
   number, the case code. Nothing else (CR 4). It asks the family to check the bank by calling the
   published number; it does not claim to prove identity (CR 24).
2. `WS /phone`: first message is `PhoneCallback`. The caller number (compared as E.164) **and** the
   case code must match the brief, and the menu choice must be the callback item. Otherwise
   `PhoneVerification{ok:false}`, `PhoneEnded{verification_failed}`, `verification_failed` to case-svc,
   and nothing is disclosed (the reply never says which check failed). Three failed attempts lock the call.
3. On success the first line is the fixed opening (automated assistant, call recorded; CR 26), then per turn:
   STT -> **model classifies intent** (constrained to `call-turn.json`; the caller's words are in a
   `data_block`; the model never sees the brief) -> **code picks and fills the template** from
   `schemas/examples/call-templates.json` using only fields that are in the brief, allowed by the call
   policy and true (otherwise the template's fallback) -> the model's connecting phrase (<= 30 chars)
   is kept only if it passes the phrase check -> **rule check** (no amounts in any form: digits in any
   width, kanji numerals, 万/円, kana such as さんびゃくまんえん; no account numbers; the text must be exactly
   an approved filled template, optionally led by the checked phrase) -> TTS.
4. The call ends on hangup, after the `coming_to_branch` template, or after the turn cap. The
   `contact_view` (`nature: information`, `reached`, signals, `disclosed` = brief fields actually spoken)
   is posted once.

Defence in depth beyond the contract: a keyword backstop forces `how_much` / `account_details` when the
caller asks about amounts, balances, accounts or payees whatever the model said; invalid or failed model
output uses the `other` template; a connecting phrase must be Japanese letters only and may not mention
facts, assurances or instructions.

## Fixed in code, not in `schemas/`

`fixed_text.py` holds the opening line, the notice and the `reason_category` wording, because
`call-templates.json` has no slot for them. Requested `schemas/` change: see the build report.

## Not verified

Gemini (`GeminiClient`), Cloud STT/TTS and real audio have not run. `get_stt()` builds a 2-channel
recogniser (counter audio); phone audio is mono, so a `channels` option is needed before cloud STT works here.
