# watchlist-loader

Scheduled Cloud Run Job. Deterministic, **no LLM, no `case-db` access** (it never calls
`open_case_repo`, which refuses this service). Fetches the DICJ frozen-account notices and the FSA
unregistered-firm warnings, validates them, and writes a dated snapshot to `ref-db` with
`RefRepo.put_snapshot(WatchlistSnapshot)`. Scoring reads `RefRepo.get_latest_snapshot()`.

## Run

```bash
pip install -e "libs/mimamori-common[dev]" -e "jobs/watchlist-loader[dev]"
python -m watchlist_loader                      # fixture source, in-memory store; exit 0
python -m pytest jobs/watchlist-loader/tests

docker build -f jobs/watchlist-loader/Dockerfile -t mimamori-watchlist-loader .
docker compose up -d firestore                  # emulator on :8086
docker run --rm -e MIMAMORI_STORE=firestore -e FIRESTORE_EMULATOR_HOST=host.docker.internal:8086 \
  -e MIMAMORI_PROJECT_ID=mimamori-local mimamori-watchlist-loader
```

| Env var | Default | |
|---|---|---|
| `WATCHLIST_SOURCE` | `fixture` | `fixture` (bundled fictional entries, or `WATCHLIST_SOURCE_PATH` if set) or `file` (needs `WATCHLIST_SOURCE_PATH`). Anything else, including `live`, is rejected: no live fetcher is built in. |
| `WATCHLIST_SOURCE_PATH` | | JSON file in the source format below |
| `MIMAMORI_*` | | Store, region, demo clock: see `libs/mimamori-common/README.md` |

Exit codes: `0` written or unchanged; `1` source rejected (last good snapshot untouched); `2` any
other failure (store unreachable, bad config).

## Behaviour

- **Normalise:** each entry is validated with `WatchlistEntry` (extra or missing fields fail), strings
  get NFC and whitespace collapsed (characters are otherwise kept as published; Scoring should NFKC
  when matching), entries are sorted by `(list_name, source_ref)`.
- **`content_hash`** = sha256 of the normalised entries as canonical JSON. List order, source order
  and stray whitespace in the source do not change it.
- **Unchanged** hash: nothing written, `latest` unchanged, exit 0.
- **Changed:** new snapshot `snapshot_id` = `YYYY-MM-DD` (JST, `MIMAMORI_DEMO_NOW` honoured), or
  `YYYY-MM-DDTHHMM` for a second changed run on the same day; `latest` moves to it. Older snapshots are kept.
- **Rejected, nothing written:** bad JSON, wrong shape, missing fields, an entry that fails
  `WatchlistEntry`, an entry whose `list_name` differs from its source, duplicate `source_ref`, no
  name/kana/account hint, zero entries in total, a list that had entries before and now has none, or a
  total below 50% of the previous snapshot when that had 10 or more entries (`loader.MIN_RETAIN_RATIO`).
  A genuine large delisting would need the threshold changed or a manual load; that is deliberate.

Source format (`src/watchlist_loader/fixtures/source.json`, fictional entries):

```json
{"sources": [{"list_name": "dicj_frozen_accounts", "url": "...", "fetched_at": "2026-10-12T03:00:00+09:00",
              "entries": [{"list_name": "dicj_frozen_accounts", "name_ja": "...", "name_kana": "...",
                           "account_hint": null, "notice_date": "2026-09-30", "source_ref": "..."}]}]}
```

## Live sources (not built, for the user to decide)

No live fetcher is written, and nothing here has been run against the real sites. To add one behind
the `Fetcher` interface (`sources.py`: return `RawBatch`es; validation is shared), first check:

| List | Likely page (verify before use) |
|---|---|
| DICJ frozen-account / 公告 notices | https://furikomesagi.dic.go.jp/ (Deposit Insurance Corporation of Japan, under the Remittance Fraud Relief Act) |
| FSA unregistered-firm warnings | https://www.fsa.go.jp/ordinary/chuui/mutouroku.html |

Check each site's terms of use and `robots.txt` (reuse and automated access), whether a data download
exists instead of scraping, and rate-limit to a few requests per run (this runs daily at most).
Gate it behind an explicit `WATCHLIST_SOURCE=live` and keep it out of tests. Parsing rules depend on
the real page formats, which were not inspected. The sample entries here are all fictional.
