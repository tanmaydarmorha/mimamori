# API contracts

The contracts every service builds against. Request and response bodies are the Pydantic models in
[`libs/mimamori-common/src/mimamori_common/models/api.py`](../../libs/mimamori-common/src/mimamori_common/models/api.py)
(`from mimamori_common.models import ...`); data contracts (evidence card, brief, wishes, ...) are
generated from [`schemas/`](../../schemas/README.md). Flows: [`c4-dynamic-tanaka.md`](c4-dynamic-tanaka.md).
Boundaries: [`c4-containers.md`](c4-containers.md). Decisions override everything:
[`../decisions.md`](../decisions.md).

**Changing a contract:** change the schema in `schemas/` and the shared models in `libs/` first,
then this file, then the services.

## Conventions

| | |
|---|---|
| Ports (local) | `web-ui` 8080 (nginx), `core-bank-mock` 8081, `scoring` 8082, `case-svc` 8083, `conversation-svc` 8084, Firestore emulator 8086. A container listens on `$PORT`; compose sets it. |
| Service URLs | Env vars `CORE_BANK_URL`, `SCORING_URL`, `CASE_SVC_URL`, `CONVERSATION_SVC_URL` (`Settings` in `mimamori_common.config`). Never hard-code. |
| Health | Every container: `GET /healthz` → `Health`. Use `mimamori_common.web.create_app(name)`. |
| Format | JSON, UTF-8. Times are timezone-aware ISO 8601 (JST in the demo). Money is integer JPY. |
| Errors | HTTP status + `ApiError {error, detail}`. 404 unknown ID, 409 wrong state, 422 body fails validation, 503 a dependency is down. |
| Roles | `X-Mimamori-Role: teller \| analyst \| system` and `X-Mimamori-User`. In the cloud IAP supplies them; locally the console's role switcher sets them. Read with `mimamori_common.web.caller_role`. Analyst-only endpoints reject anything else with 403. Service-to-service calls send `system`. The `user` goes into every audit entry. |
| Browser access | The browser only talks to `web-ui`'s nginx, which proxies `/api/core/`, `/api/scoring/`, `/api/case/`, `/api/conversation/` to the service URLs (WebSocket upgrade on, `proxy_buffering off` for SSE). Services also allow CORS from `MIMAMORI_CORS_ORIGINS` for local development. |
| IDs | `case-YYYY-MMDD-NNNN`, `tr-…` transfer, `hold-…`, `frz-…` freeze, `dec-…` decision, `call-NNNN-N`. Customer / account refs as in the seed (`cust-tanaka-0001`, `acct-tanaka-0001`). |
| Idempotency | `POST /cases` is keyed by `transfer_id`: a repeat returns the existing case. |
| Clock | Use `Settings.now()`. `MIMAMORI_DEMO_NOW=2026-10-13T11:42:00+09:00` fixes the demo clock so seeded ages hold. |
| Data boundary | Only `scoring` and `case-svc` open `case-db` (`open_case_repo` refuses other service names). `conversation-svc` receives only `CallRequest`. |

## Endpoints

### core-bank-mock (`services/core-bank-mock`)

Core banking is an external system; this is its mock. It reads `seed/bank/` into its **own** store.

| Endpoint | Called by | Request → response | Notes |
|---|---|---|---|
| `POST /transfers` | web-ui (teller keys it in), channels | `TransferRequest` → `TransferResponse` | `counter` or amount ≥ `LARGE_TRANSFER_THRESHOLD_JPY` → calls Scoring `/v1/score` within `SCORING_TIMEOUT_S`. `alert` → status `pending_alert`, `case_id` returned, money does not move. Timeout / error → proceed, `scoring: "unavailable"`, log it (fail open, DA 7). Other channels → execute, then `/v1/events` (`scoring: "not_checked"`). |
| `GET /transfers/{id}` | web-ui, case-svc | → `Transfer` | |
| `PATCH /transfers/{id}` | case-svc | `TransferPatch` → `Transfer` | `execute` (teller cleared it, no hold) or `cancel`. |
| `GET /customers`, `GET /customers/{ref}` | scoring, case-svc, web-ui | → `Customer`(s) | Read-only. |
| `GET /accounts?customer_ref=`, `GET /accounts/{id}` | same | → `Account`(s) | `balance_jpy` is never copied into a brief, card or notice. |
| `GET /accounts/{id}/transactions?since=&until=&limit=&order=` | scoring, case-svc tools | → `list[BankTransaction]` | `since`/`until` inclusive. Oldest first by default; `limit` keeps the most recent N; no default cap (a 12-year history must come back whole, `limit=100000` is honoured); `order=desc` available. |
| `GET /accounts/{id}/payers?days=7` | scoring, case-svc | → `PayersResponse` | Distinct payers of **completed** transfers into the account in the window. For the mule this is the **six** prior payers. |
| `POST /holds` | case-svc | `HoldRequest` → `Hold` | Window computed here, see **Hold window** below. Transfer → `held`. |
| `GET /holds/{id}` | case-svc, web-ui | → `Hold` | |
| `PATCH /holds/{id}` | case-svc | `HoldPatch` → `Hold` | `keep`, `release`, or an override. `override_after_contact_reached` needs `contact_reached=true`; `override_after_manager_review` needs `manager_id` and a different `second_confirmed_by`; otherwise 409. A release executes the transfer (`released`). **Plain `release` before `ends_at` is allowed only for a hold with an empty `overrides` list** (a bank-policy voluntary wait: case-svc sends `overrides: []`); for a wishes-based hold it is 409 `hold_active` and only the overrides end it early. After `ends_at` a plain release is always allowed. A second confirmer must differ from `manager_id` and the hold's `placed_by`. |
| `POST /freezes` | case-svc, after analyst approval | `FreezeBody` → `Freeze` | Account `status: "frozen"`. |

**Hold window.** Inputs: `placed`, `window.minimum_hours`, `extend_to_next_business_day_close`,
`window.cap_hours`; business closes at `BUSINESS_DAY_CLOSE` (15:00 JST) on days not in
`seed/business-calendar.json` and not Sat/Sun.

```
minimum_ends_at = placed + minimum_hours
ends_at = minimum_ends_at
if extend: ends_at = max(minimum_ends_at, first business-day close at or after minimum_ends_at)
cap_ends_at = placed + cap_hours
ends_at = min(ends_at, cap_ends_at)
```
Test vectors (4 h minimum, cap 24 h, extend on): Tue 09:30 → Tue 15:00; Tue 11:50 → Wed 11:50 (cap);
Tue 14:30 → Wed 14:30 (cap); Fri 14:30 → Sat 14:30 (cap; the next close is Monday); with
`extend=false`, Tue 14:30 → Tue 18:30.

### scoring (`services/scoring`)

No LLM, min 1 instance, < 200 ms per score. Reads `core-bank-mock` (transactions, payers) and
`ref-db` (watchlist); writes baselines and scores to `case-db`.

| Endpoint | Called by | Request → response | Notes |
|---|---|---|---|
| `POST /v1/score` | core-bank-mock | `ScoreRequest` → `ScoreResponse` | Pre-transaction. On `alert`, Scoring calls case-svc `POST /cases` itself and returns `case_id`. |
| `POST /v1/events` | core-bank-mock | `ScoreRequest` → `EventResponse` | Post-transaction. Never opens a case in the prototype; `matched_baseline` explains why a large item was fine (`seasonal:april_school_fee`). |
| `POST /v1/baselines/refresh`, `POST /v1/baselines/{customer_ref}/refresh` | operator / startup | → `list[Baseline]` / `Baseline` | The baseline job (DA 14). Also computed lazily on first use. |

Signals (`ScoreSignal`, become fact claims, same `tool`/`field`/`value`). For the hero case:
`get_baseline.amount_vs_median_ratio = 60`, `get_baseline.new_payee = true`,
`counterpart_graph.account_age_days = 4`, `counterpart_graph.distinct_payers_7d = 7`.
Replaying history (evaluation, tests) Scoring derives fan-in from the payee account's `transfer_in` rows as of the replayed time, because `/payers?days=` is anchored at the bank's now. **`distinct_payers_7d` counts the payer asking now**: the six completed payers from `/payers` plus
the requesting customer if not already among them. The "six others" on the outreach list are the
payers excluding the case customer.

### case-svc (`services/case-svc`)

| Endpoint | Called by | Request → response | Notes |
|---|---|---|---|
| `POST /cases` | scoring | `OpenCaseRequest` → `OpenCaseResponse` | Opens the case, starts the investigation, emits `case_opened`. |
| `GET /cases?status=` | web-ui | → `list[CaseSummary]` | |
| `GET /cases/{id}` | web-ui | → `Case` | `card` is the evidence card, `hold_line` the filled approved hold line (text for `card.risk.hold_line_id`); its `request` has no name, age or balance. |
| `GET /cases/{id}/events` | web-ui | SSE of `CaseEvent` | `event:` = type, `id:` = seq, `data:` = the JSON. Replays from `?after=<seq>` or `Last-Event-ID`, then streams (`?follow=false` replays and closes). |
| `WS /cases/{id}/audio` | web-ui | binary frames in, JSON text frames out | In: LINEAR16 16 kHz, 2 interleaved channels (0 customer microphone, 1 teller) under Cloud STT; under `typed` speech, each frame is one UTF-8 utterance, optionally prefixed `teller:`. Out: `{"type":"transcript","turn_id","speaker","text","is_final"}`. Cards still arrive over SSE. |
| `POST /cases/{id}/turns` | web-ui (typed fallback) | `TurnRequest` → `TurnResponse` | Customer turn → copilot call → quote rule → accumulation → risk rule → bank question → card update. Teller turn → transcript only. |
| `POST /cases/{id}/decision` | web-ui (teller) | `DecisionRequest` → `DecisionResponse` | A human decides (DA 11). `pause` places a hold with the window from the customer's wishes (`basis=advance_wishes`) or the bank-policy default (`bank_policy`). A pause with a single indicator source is allowed with `warnings: ["single_source_pause"]`, logged, never blocked. `release` follows the override rules above. Triggers the family call automatically after a `pause` when wishes allow it. |
| `POST /cases/{id}/claims/{claim_id}/dismiss` | web-ui (teller) | `DismissIndicatorBody` → `Case` | The only way a verified indicator leaves the card. Audited. |
| `POST /cases/{id}/police-summary` | web-ui (teller) | `PoliceSummaryRequest` → `PoliceSummaryResponse` | On the officers' request; only the requested sections; officer name and title are logged (APPI 27(1)(i)). |
| `POST /cases/{id}/contact-call` | web-ui (teller) | → `Case` | Manual (re)trigger of steps 7a–7b: contact check → brief built in code → `POST /calls`. |
| `POST /cases/{id}/contact-outcome` | conversation-svc | `ContactOutcomeRequest` → `Case` | `contact_view` (information, never an instruction) or `verification_failed`. `contact_view.reached` enables the `after_contact_reached` override. |
| `GET /cases/{id}/outreach` | web-ui (analyst) | → `list[OutreachItem]` | Empty until a freeze is approved. The `outreach_ready` event carries the same list as `data.outreach`. |
| `POST /cases/{id}/notes` | web-ui (teller) | teller note, optional `contact_flagged` | Feeds the contact-suspected check. |
| `PATCH /cases/{id}/language` | web-ui (teller) | `SetLanguageRequest {language: ja\|en, actor}` → `Case` | The case's conversation language (default `ja`). 409 `language_locked` once the case has a turn; audited as `case.language_set`. Also on `CaseSummary.language`. |
| `POST /cases/{id}/police-notified` | web-ui (teller) | → `Case` | Sets `police_notified` for the brief. |
| `GET /cases/{id}/audit` | web-ui | → audit entries | Who, what, why, when. |
| `POST /cases/{id}/freeze-request` | web-ui | `FreezeRequestBody` → `FreezeRequest` | |
| `GET /freeze-requests?status=` | web-ui (analyst) | → `list[FreezeRequest]` | Analyst role. |
| `POST /cases/{id}/freeze-decision` | web-ui (analyst) | `FreezeDecisionBody` → `FreezeDecisionResponse` | Analyst role. On `approve`: core-bank `POST /freezes`, then `GET /accounts/{mule}/payers` → `outreach` (the other payers, six in the demo). |
| `GET /playbooks?status=` | web-ui | → `list[Playbook]` | |
| `PATCH /playbooks/{id}` | web-ui (analyst) | `PlaybookPatch` → `Playbook` | Analyst role. Only `approved` playbooks reach the copilot. |
| `PUT /customers/{ref}/wishes` | web-ui | `AdvanceWishes` → `WishesChangeResponse` | With an open case the new version is stored `frozen_pending_review`, the previous contact is notified, event `wishes_frozen` (DA 12). |

`CaseEvent.type`: `case_opened`, `card_updated`, `transcript_turn`, `decision_logged`,
`hold_placed`, `hold_updated`, `police_summary_issued`, `contact_notice_sent`, `contact_outcome`,
`verification_failed`, `freeze_requested`, `freeze_decided`, `outreach_ready`, `wishes_frozen`.

**Rules the case service owns** (reference: `mimamori_common.rules`): `verify_quotes` →
`merge_indicators` → `assess_risk` (`risk-v1`) on every customer turn; the model returns
`CopilotTurn` under constrained decoding and only an ID from the approved bank (already-suggested
IDs removed from the bank it sees; an unknown ID falls back to `q.general.purpose` and is logged);
code fills slots and the hold line. No probability numbers anywhere.

### conversation-svc (`services/conversation-svc`)

No `case-db` access. State is in memory (or its own store); it never sees anything but `CallRequest`.

| Endpoint | Called by | Request → response | Notes |
|---|---|---|---|
| `POST /calls` | case-svc | `CallRequest` → `CallResponse` | Stores the call, sends the **notice** (reveals nothing: branch, "about your mother", published number, case code). |
| `GET /notices?to=<e164>` | web-ui (simulated phone) | → `list[Notice]` | What Yuki's simulated phone shows and plays. |
| `WS /phone` | web-ui (simulated phone) | `PhoneClientMessage` in, `PhoneServerMessage` out | Every `PhoneSay` and `Notice` carries `text` (in the case language), `language` and `gloss_en` (English gloss for display; set only when `language` is `ja`; a model lead-in is not translated and the gloss says so). First message `PhoneCallback {caller_number, menu_choice: "returning_a_call_about_a_case", case_code}`. Both must match the brief (`locked_phone_e164`, `case_code`) or the call ends with `PhoneVerification{ok:false}`, `PhoneEnded{verification_failed}` and `verification_failed` goes to case-svc, nothing disclosed. On success: the fixed opening line (automated assistant, call recorded), then `PhoneTurn` (typed `text`, or binary audio frames) ↔ `PhoneSay`. Ends with `contact_view` posted to case-svc. |

Behaviour pinned down by the build: the call ends with `PhoneEnded{completed}` after the
`coming_to_branch` turn (or on hangup, or after 20 turns), so the socket closes and the UI should
expect that. `verification_failed` may be posted to case-svc once per failed attempt (up to 3) for
one `call_id`; case-svc must accept repeats. The callback menu item is labelled 「ご連絡への折り返し」
in the notice and in the simulated phone. Phone audio is mono: `get_stt(settings, channels=1)`.
Until `schemas/` has opening / notice template kinds, the fixed opening, notice and reason-category
wording live in `services/conversation-svc/src/conversation_svc/fixed_text.py`.

Per turn: STT → model classifies intent (`CallTurn`, constrained) → **code** picks and fills the
template from the brief (fallback wording when a field isn't in `disclosable`) → the model writes a
connecting phrase of ≤ 30 characters → rule check (no amounts in any form, no account numbers,
nothing outside the brief) → TTS.

### web-ui (`services/web-ui`)

Calls only the endpoints above, through nginx. Teller console, analyst console, simulated phone at
`/phone` (notice, call back, menu, case code, conversation). Role switcher locally; IAP in cloud.

### watchlist-loader, intel-job, sim-job

Jobs: exit 0 on success.

- `watchlist-loader` → `ref-db` only (`RefRepo.put_snapshot(WatchlistSnapshot)`); a malformed source
  fails the job and leaves the last good snapshot.
- `intel-job` → `intel-db` only, `Playbook` with `status: "pending"` (never `approved`), `published_at` kept.
- `sim-job` → `core-bank-mock` (synthetic seed), `case-svc` (`/cases`, `/turns`, `/decision`), Gemini
  for role-play and a separate judge prompt. Synthetic-only.

## Audio formats

- **Language (WI-005):** the brief carries `language` and `customer_reference` (in that language; `branch.name_en` is used for an English notice). The notice, the opening line, every template and the rule check come from that language's approved pack, never from the model. `CallResponse.notice_text_ja` keeps its name but holds the notice in the case language.
- `Notice.audio_b64` and `PhoneSay.audio_b64`: base64 of `audio/mpeg` (what `CloudTts` produces); absent under `typed` speech.
- `WS /phone` binary frames: mono 16 kHz LINEAR16. `WS /cases/{id}/audio`: 16 kHz LINEAR16, 2 interleaved channels (a single browser microphone fills channel 0, channel 1 silent).

## Who am I

`web-ui`'s nginx serves `/whoami` (echoes the IAP-supplied headers as role and user) and `/config.json`
(`env`, `speech`). Services trust `X-Mimamori-*` only from `web-ui` and other services.

## Shared library

`libs/mimamori-common` is the only place for models, rules, config, stores, model clients and speech
clients. Selection is by config: `MIMAMORI_STORE=memory|firestore`, `MIMAMORI_COPILOT_BACKEND` /
`MIMAMORI_GENERAL_BACKEND=ollama|vertex_gemma|gemini|fake`, `MIMAMORI_SPEECH=typed|cloud`.
See its README for the table of settings.
