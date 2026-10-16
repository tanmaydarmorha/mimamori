# core-bank-mock

Mock core banking. In the C4 docs core banking is an external system; this is its stand-in so the
integration boundary stays visible. It serves the synthetic seed (`seed/bank/`) from its **own**
in-memory store (never `case-db`) and implements the `core-bank-mock` section of
[`docs/architecture/api-contracts.md`](../../docs/architecture/api-contracts.md).

## Run

```bash
python3 -m venv .venv && .venv/bin/pip install -e "libs/mimamori-common[web,dev]" -e "services/core-bank-mock[dev]"
.venv/bin/python -m pytest services/core-bank-mock/tests

# locally (the demo clock keeps "account opened 4 days ago" and "payers in the last 7 days" true)
MIMAMORI_DEMO_NOW=2026-10-13T11:42:00+09:00 SCORING_URL=http://localhost:8082 PORT=8081 \
  .venv/bin/uvicorn core_bank_mock.main:app --port 8081

docker build -f services/core-bank-mock/Dockerfile -t mimamori-core-bank-mock .   # from the repo root
docker run --rm -p 8081:8080 mimamori-core-bank-mock
```

Config (all via `mimamori_common.config.Settings`): `SCORING_URL`, `SCORING_TIMEOUT_S` (0.5),
`LARGE_TRANSFER_THRESHOLD_JPY` (1,000,000), `BUSINESS_DAY_CLOSE` (15:00), `MIMAMORI_DEMO_NOW`.
State resets on restart. Balances are static (the seed does not reconcile them with its history);
executed transfers append transactions only.

## Behaviour

- **`POST /transfers`**: `counter`, or amount >= threshold, is checked first with Scoring `POST /v1/score`
  (whole-call deadline `SCORING_TIMEOUT_S`). `alert` -> `pending_alert` with the `case_id`, money does
  not move. `allow` -> executed. Timeout, connection error, non-2xx or an unreadable body -> executed with
  `scoring: "unavailable"`, logged (fail open, DA 7). Other channels execute with `scoring: "not_checked"`,
  then `POST /v1/events` (failures only logged). Transfers from or to a frozen account get 409 `account_frozen`.
- **Holds** (`POST /holds`, only on a `pending_alert` transfer): window from the Hold window formula
  (`window.py`, test vectors in `tests/test_window.py`). The transfer becomes `held`.
- **`PATCH /holds/{id}`**: `keep` is a no-op. `override_after_contact_reached` needs the hold to list
  that override and `contact_reached=true`. `override_after_manager_review` needs the override listed,
  `manager_id` and a `second_confirmed_by` who is neither the manager nor whoever placed the hold.
  Plain `release` is accepted once the window has run out, or at any time for a hold whose `overrides`
  list is empty (bank-policy voluntary wait). Before the end, a hold with overrides gets 409 `hold_active`. Any release executes the transfer (`released`) unless a
  party was frozen meanwhile (409, hold stays). Violations are 409 with an `ApiError`.
- **`PATCH /transfers/{id}`**: `execute` (only `pending_alert`) or `cancel` (`pending_alert` or `held`;
  releases the hold without moving money).
- **`GET /accounts/{id}/payers?days=7`**: distinct payers of completed `transfer_in`s in the window, relative to
  the clock. For the mule: the six prior payers (Tanaka's pending or held transfer is not counted; once
  released it is the seventh).
- **`GET /accounts/{id}/transactions`**: oldest first by default; `limit` keeps the most recent N;
  `order=desc`; `since` / `until` are inclusive.
- **`POST /freezes`**: account `status: "frozen"`; a repeat for a frozen account returns the first freeze.
- Errors are `ApiError {error, detail}` (404, 409, 422 including request-body validation).
