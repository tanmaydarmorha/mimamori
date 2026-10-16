# scoring

Pre-transaction check and post-transaction monitoring. **No LLM.** Min 1 instance. Target < 200 ms per
`/v1/score`. Reads core banking (`CORE_BANK_URL`: transactions, accounts, payers) and `ref-db` (watchlist);
writes baselines and scores to `case-db`; on `alert` calls case-svc `POST /cases` itself.

| Endpoint | |
|---|---|
| `POST /v1/score` | `ScoreRequest` -> `ScoreResponse`. Pre-transaction. On `alert` opens a case (one call per alert; case-svc is idempotent on `transfer_id`) and returns `case_id`. If case-svc is down the alert is still returned with `case_id: null`. |
| `POST /v1/events` | `ScoreRequest` -> `EventResponse`. Post-transaction. Never opens a case. `matched_baseline` explains a large item that was fine. |
| `POST /v1/baselines/refresh`, `POST /v1/baselines/{customer_ref}/refresh` | Recompute baselines as of now and store them in `case-db`. Also run in the background at startup (`SCORING_WARM_ON_START=false` to skip) and lazily on first use. |
| `GET /healthz` | |

Core banking unreachable -> `503 bank_unavailable` (the caller fails open, DA 7). Unknown customer -> 404.

## Run

```bash
python3 -m venv .venv && .venv/bin/pip install -e "libs/mimamori-common[web,dev]" -e "services/scoring[dev]"
.venv/bin/python -m pytest services/scoring/tests            # no GCP, no other service needed
CORE_BANK_URL=http://localhost:8081 CASE_SVC_URL=http://localhost:8083 PORT=8082 \
  .venv/bin/uvicorn mimamori_scoring.app:app --port 8082
docker build -f services/scoring/Dockerfile . && docker run -p 8082:8080 <image>
```

Settings come from `mimamori_common.config.Settings` (`MIMAMORI_STORE`, `CORE_BANK_URL`, `CASE_SVC_URL`,
`MIMAMORI_DEMO_NOW`, `LARGE_TRANSFER_THRESHOLD_JPY`, ...). Thresholds are in `mimamori_scoring/config.py`
(`SCORING_*` env overrides), e.g. `SCORING_MULE_ALERT_MIN_AMOUNT_JPY` (default 100000): the mule pattern
(young payee account and fan-in) alone alerts only at or above this amount; below it the decision is
`allow` with the signals still stored. A watchlist hit alerts at any amount.

Running totals (structuring, WI-012): the rules also judge the total, including the payment being scored.
`SCORING_PAYEE_TOTAL_DAYS` (default 7): the customer's `transfer_out` rows to the same payee, summed; the mule
term uses `max(amount, payee total)`. `SCORING_OUTFLOW_WINDOW_HOURS` (default 24): all the customer's outflows,
summed; `unusual` runs on `max(amount, outflow)`. Earlier seasonal rows are left out. A `payee_running_total` or
`outflow_running_total` signal is added only when the total, not the single payment, crossed the threshold.
Scoring reads the customer's own account once per request for this (case-svc's `recent_transactions` tool
computes the same three fields, with the same env var names, so the fact check keeps the signals).

## Baseline (`mimamori_common.models.Baseline`)

Computed as of a cutoff from transactions booked strictly before it, so a transaction is never part of its
own baseline. Cached in `case-db` (24 h); a request older than the cached baseline is computed as of its own
`occurred_at` and not cached, which is how history is replayed. `median_monthly_withdrawal_jpy` is the median
of monthly outflow totals (cash withdrawals + transfers out) over 36 months; `p95_withdrawal_jpy` the 95th
percentile single outflow; `contractor_payments_count_12y` counts payments to `contractor` payees (0 for
Tanaka; absence is a field). **Seasonal items**: a large outflow (>= 3x the monthly median) recurring in the
same month with similar amounts (+-15 %) in >= 2 years. Tanaka: `april_school_fee`, 12 years, ¥400,000.
The *name* `school_fee` is a heuristic (any such April item), because the bank data has no purpose for it.

## Rule `score-v1`

Signals carry `tool` / `field` / `value` as in api-contracts.md: `get_baseline.amount_vs_median_ratio`,
`get_baseline.new_payee`, `counterpart_graph.account_age_days`, `counterpart_graph.distinct_payers_7d`
(includes the requesting customer), `check_lists.watchlist_match`.

```
unusual = amount >= ¥100,000 and amount >= 10x median monthly outflow and amount > p95 item  (and not seasonal)
alert   = watchlist hit
       or unusual and (new payee or payee account < 30 days or >= 3 payers in 7 days or cash withdrawal)
       or payee account < 30 days and >= 3 payers in 7 days
```

Watchlist matching: payee name (NFKC, brackets and spaces dropped, hiragana folded to katakana) equal to a
snapshot entry's kana or Japanese name, or the payee account id as a whole token in `account_hint`. The
latest `ref-db` snapshot is cached for 60 s.

## Results on the seed (see `tests/test_scoring.py`)

| Case | Outcome |
|---|---|
| Tanaka ¥400,000, 2026-04-10 (`/v1/events`) | `allow`, `matched_baseline = seasonal:april_school_fee`, no case |
| Tanaka ¥3,000,000 counter transfer to the mule | `alert`: 60x baseline, new payee, payee account 4 days old, 7 payers; case opened |
| 50 ordinary customers (not mule payers), last 14 days | no alerts |
| **6 ordinary customers who paid the mule in the last week** | **alert** on that transfer (it is the one abnormal item in their last 14 days; events never open a case). Nothing else in their 14 days alerts. See note below. |
| Legit look-alike `genuine_renovation` (cust-0005, ¥2,400,000 to `カ）サクラコウムテン`) | **allow**. Large (15x), but the customer has paid that payee before, the account is 10 years old with no fan-in. |
| Legit look-alike `car_for_grandchild` (cust-0008, ¥1,800,000 to `カ）ミドリモータース`) | **alert** (false positive at the scoring stage): 16x baseline and a first payment to a new payee. The dealer account is 14 years old with one payer, so those two signals are absent. Scoring has no way to know the purpose; this is what the counter conversation and copilot are for (spike conversation B), and the alert only opens a case, never stops the customer. |
| Watchlist hit (fake `ref-db` snapshot, payee name) | `check_lists.watchlist_match` signal and `alert`, even for a small amount |

Note on the 14-day replay: the task statement says every ordinary customer should produce no alerts, but six
of the seed's "ordinary" customers are the mule's other payers, and their transfer to the mule is exactly what
scoring should flag. The test asserts alerts happen only for those six transfers to `acct-mule-0001`.

## Latency

In-process fake bank, warm baselines: median ~1 ms per `/v1/score` (max < 2 ms); cold (baseline computed on the
first request): ~7 ms. A real network adds one bank round trip for the payee account and payers (issued in
parallel), plus the case-svc call on alert. Baselines are cached, the watchlist is cached, nothing else is fetched.

## Assumptions about other services

- core-bank-mock serves `GET /customers`, `/customers/{ref}`, `/accounts?customer_ref=`, `/accounts/{id}`,
  `/accounts/{id}/transactions?since=&until=&limit=` (ISO datetimes, inclusive, large `limit` honoured) and
  `/accounts/{id}/payers?days=7` as in api-contracts.md. For history replays the fan-in is derived from the payee
  account's `transfer_in` rows instead of `/payers` (which is anchored at the bank's now).
- case-svc `POST /cases` is idempotent on `transfer_id`.
