# Seed data (synthetic)

All people, companies, accounts and numbers are invented. Regenerate with `python seed/generate.py`
(deterministic). Load into the stores with `python seed/load.py` (see `mimamori_common.seed`).

| Path | What | Read by |
|---|---|---|
| `bank/customers.json`, `accounts.json`, `transactions.json` | Core-banking data: Tanaka Keiko (12 years, ~¥50,000 monthly withdrawals, ¥400,000 each April, no contractor payments), the mule account `カ）ミライケンセツ` (opened 2026-10-09, six prior payers), 3 company payees, 56 ordinary customers (36 months of history; 6 are the mule's other payers) | `core-bank-mock` (its own store, **not** `case-db`) |
| `manifest.json` | Index of the scenarios: hero transfer, mule payers, school-fee event, two legitimate look-alikes (genuine renovation, car for a grandchild), demo clock | tests, `sim-job`, demo |
| `business-calendar.json` | Closed days for hold windows | `core-bank-mock` |
| `intel/playbook-pending.json` | One **pending** playbook for the analyst console (the approved ones are `schemas/examples/playbooks.json`, all `published_at` before T = 2026-04-01) | `intel-db` |
| `ref/watchlist-snapshot.json` | Sample dated watchlist snapshot (fictional entries) | `ref-db`, Scoring |
| Tanaka's advance wishes | `schemas/examples/advance-wishes-tanaka.json` | `case-db` |

`distinct_payers_7d` for the hero transfer is 7: the six completed payers plus Tanaka's pending
request. Balances are fixed per account and not reconciled with the history. An ordinary
customer's last 14 days replayed through `POST /v1/events` must never alert, except that the six mule
payers' transfers to `acct-mule-0001` are expected to.
