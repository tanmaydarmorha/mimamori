"""Done-when tests for the scoring service, against a fake core bank built on the synthetic seed."""

from __future__ import annotations

import statistics
import time
from datetime import timedelta

from conftest import score_body
from mimamori_common.models import BankTransaction
from mimamori_common.models.baseline import Baseline, WatchlistSnapshot


def signal_values(body: dict) -> dict[tuple[str, str], object]:
    return {(s["tool"], s["field"]): s["value"] for s in body["signals"]}


def to_request(t: BankTransaction, customer_ref: str, accounts: dict) -> dict | None:
    """A booked outgoing transaction as the event the bank would post after executing it."""
    if t.kind == "withdrawal":
        kind, payee = "cash_withdrawal", None
    elif t.kind in ("transfer_out", "direct_debit"):
        kind = "transfer"
        payee = {"name_kana": t.counterparty_name_kana, "relation": "same_bank" if t.counterparty_account_id else "other_bank",
                 "account_id": t.counterparty_account_id}
    else:
        return None
    channel = t.channel if t.channel in ("counter", "atm", "app") else "app"
    return dict(transfer_id=t.txn_id, customer_ref=customer_ref, account_id=t.account_id, channel=channel, kind=kind,
                amount_jpy=t.amount_jpy, payee=payee, memo=t.memo, occurred_at=t.booked_at.isoformat())


# ------------------------------------------------------------------ hero and school fee


async def test_april_school_fee_matches_seasonal_baseline_no_alert(harness, bank_data):
    fee = next(t for t in bank_data.transactions if t.txn_id == "txn-000372")  # 2026-04-10, ¥400,000
    body = to_request(fee, "cust-tanaka-0001", {})
    r = await harness.client.post("/v1/events", json=score_body(**body))
    assert r.status_code == 200
    out = r.json()
    assert out["decision"] == "allow"
    assert out["matched_baseline"] == "seasonal:april_school_fee"
    assert out["signals"] == []
    assert harness.case_svc.opened == []


async def test_april_withdrawal_pre_transaction_also_matches(harness):
    """Same item scored before execution, with the clock in April: still allowed, still no case."""
    from mimamori_common.config import Settings
    s = Settings(demo_now="2026-04-10T10:35:00+09:00", store_backend="memory", service_name="scoring")
    harness.app.state.scorer.settings = s
    r = await harness.client.post("/v1/score", json=score_body(
        transfer_id="tr-april", kind="cash_withdrawal", amount_jpy=400_000, payee=None, occurred_at="2026-04-10T10:35:00+09:00"))
    out = r.json()
    assert out["decision"] == "allow" and out["matched_baseline"] == "seasonal:april_school_fee"
    assert harness.case_svc.opened == []


async def test_hero_transfer_alerts_with_signals_and_opens_a_case(harness):
    r = await harness.client.post("/v1/score", json=score_body())
    assert r.status_code == 200
    out = r.json()
    assert out["decision"] == "alert"
    assert out["case_id"] and out["case_id"].startswith("case-")
    vals = signal_values(out)
    assert vals[("get_baseline", "amount_vs_median_ratio")] == 60
    assert vals[("get_baseline", "new_payee")] is True
    assert vals[("counterpart_graph", "account_age_days")] == 4
    assert vals[("counterpart_graph", "distinct_payers_7d")] == 7  # six completed payers + Tanaka
    assert [s["code"] for s in out["signals"]] == ["amount_vs_baseline", "new_payee", "payee_account_age", "payer_fan_in"]
    # the case service got exactly one call, with the signals and no balance / name
    assert len(harness.case_svc.opened) == 1
    opened = harness.case_svc.opened[0]
    assert opened.transfer_id == "tr-test-0001" and opened.customer_ref == "cust-tanaka-0001"
    assert opened.request.amount_jpy == 3_000_000 and opened.request.payee.name_kana == "カ）ミライケンセツ"
    assert {s.field for s in opened.signals} >= {"amount_vs_median_ratio", "new_payee", "account_age_days", "distinct_payers_7d"}
    # the score is persisted to case-db
    stored = harness.case_repo.get_score("tr-test-0001")
    assert stored["decision"] == "alert" and stored["case_id"] == out["case_id"] and stored["rule_version"] == "score-v1"


async def test_payer_already_among_the_six_is_not_double_counted(harness, seed_manifest):
    payer = seed_manifest["mule"]["prior_payers"][0]
    r = await harness.client.post("/v1/score", json=score_body(
        transfer_id="tr-again", customer_ref=payer["customer_ref"], account_id=payer["account_id"], amount_jpy=500_000))
    assert signal_values(r.json())[("counterpart_graph", "distinct_payers_7d")] == 6


async def test_events_never_open_a_case_even_on_alert(harness):
    r = await harness.client.post("/v1/events", json=score_body(channel="app", transfer_id="tr-ev"))
    assert r.json()["decision"] == "alert" and r.json()["case_id"] is None
    assert harness.case_svc.opened == []


async def test_alert_survives_case_service_outage(harness):
    harness.case_svc.fail = True
    out = (await harness.client.post("/v1/score", json=score_body())).json()
    assert out["decision"] == "alert" and out["case_id"] is None


async def test_bank_down_is_503_so_the_caller_fails_open(harness):
    import httpx

    def boom(request):
        raise httpx.ConnectError("down")

    harness.app.state.scorer.bank.http = httpx.AsyncClient(transport=httpx.MockTransport(boom), base_url="http://bank")
    r = await harness.client.post("/v1/score", json=score_body(customer_ref="cust-0003", account_id="acct-0003"))
    assert r.status_code == 503 and r.json()["error"] == "bank_unavailable"


# ------------------------------------------------------------------ baselines


async def test_tanaka_baseline_fields(harness):
    r = await harness.client.post("/v1/baselines/cust-tanaka-0001/refresh")
    b = Baseline.model_validate(r.json())
    assert b.median_monthly_withdrawal_jpy == 50_000
    assert b.contractor_payments_count_12y == 0  # absence is a field
    assert b.customer_tenure_years == 12
    assert [(s.key, s.month, s.typical_amount_jpy) for s in b.seasonal_items] == [("april_school_fee", 4, 400_000)]
    assert b.seasonal_items[0].years_seen == 12
    assert harness.case_repo.get_baseline("cust-tanaka-0001")["customer_ref"] == "cust-tanaka-0001"


async def test_baseline_is_cached_between_scores(harness):
    await harness.client.post("/v1/baselines/cust-tanaka-0001/refresh")
    harness.bank.state.calls.clear()
    await harness.client.post("/v1/score", json=score_body())
    # no baseline recompute (customer, accounts, full history); the one account read is the running-totals window
    assert not any(c.startswith(("customer ", "accounts of")) for c in harness.bank.state.calls)
    assert harness.bank.state.calls.count("transactions acct-tanaka-0001") == 1


async def test_refresh_all_covers_every_customer(harness, bank_data):
    r = await harness.client.post("/v1/baselines/refresh")
    assert len(r.json()) == len(bank_data.customers)


async def test_contractor_history_is_counted(harness):
    r = await harness.client.post("/v1/baselines/cust-0005/refresh")
    assert Baseline.model_validate(r.json()).contractor_payments_count_12y == 1


# ------------------------------------------------------------------ ordinary customers


async def test_no_ordinary_customer_alerts_when_their_last_14_days_are_replayed(harness, bank_data, seed_manifest):
    now = harness.settings.now()
    mule_payers = {p["customer_ref"] for p in seed_manifest["mule"]["prior_payers"]}
    accounts = {a.account_id: a for a in bank_data.accounts}
    ordinary = [c for c in bank_data.customers if c.customer_ref.startswith("cust-0")]
    assert len(ordinary) == seed_manifest["counts"]["ordinary_customers"]
    replayed, alerts = 0, []
    for c in ordinary:
        for acct in (a for a in bank_data.accounts if a.customer_ref == c.customer_ref):
            recent = [t for t in bank_data.transactions if t.account_id == acct.account_id and now - timedelta(days=14) <= t.booked_at <= now]
            for t in sorted(recent, key=lambda t: t.booked_at):
                body = to_request(t, c.customer_ref, accounts)
                if not body:
                    continue
                out = (await harness.client.post("/v1/events", json=score_body(**body))).json()
                replayed += 1
                if out["decision"] == "alert":
                    alerts.append((c.customer_ref, t.txn_id, t.counterparty_account_id, [s["code"] for s in out["signals"]]))
    print(f"\nreplayed {replayed} outgoing events for {len(ordinary)} customers; alerts: {alerts}")
    assert replayed > 50
    # The six customers who paid the mule in the last week are the scenario's victims: their transfer to
    # the mule is the one thing in their last 14 days that is not normal. Nothing else may alert.
    unexpected = [a for a in alerts if not (a[0] in mule_payers and a[2] == "acct-mule-0001")]
    assert unexpected == []
    assert {a[0] for a in alerts} <= mule_payers
    assert harness.case_svc.opened == []


# ------------------------------------------------------------------ legitimate look-alikes


async def test_legit_scenarios_are_scored(harness, seed_manifest):
    """Outcomes are documented in the README. Renovation to a payee the customer has paid before: allow.
    Car for a grandchild to a brand-new payee with an old account: alert (a large first payment is what
    the counter conversation is for); the copilot, not Scoring, clears it."""
    outcomes = {}
    for sc in seed_manifest["legit_scenarios"]:
        payee_acct = {"genuine_renovation": "カ）サクラコウムテン", "car_for_grandchild": "カ）ミドリモータース"}[sc["id"]]
        r = await harness.client.post("/v1/score", json=score_body(
            transfer_id=f"tr-{sc['id']}", customer_ref=sc["customer_ref"], account_id=sc["account_id"], amount_jpy=sc["amount_jpy"],
            payee={"name_kana": payee_acct, "relation": "same_bank", "account_id": sc["payee_account_id"]}))
        outcomes[sc["id"]] = r.json()
    reno, car = outcomes["genuine_renovation"], outcomes["car_for_grandchild"]
    assert reno["decision"] == "allow"
    assert car["decision"] == "alert"
    vals = signal_values(car)
    assert vals[("get_baseline", "new_payee")] is True
    assert ("counterpart_graph", "account_age_days") not in vals  # 14-year-old dealer account: not a signal
    assert ("counterpart_graph", "distinct_payers_7d") not in vals


# ------------------------------------------------------------------ watchlist


async def test_watchlist_hit_produces_a_signal_and_alerts(harness):
    snapshot = harness.ref_repo.get_latest_snapshot()
    snapshot["snapshot_id"] = "2026-10-13"
    snapshot["entries"].append({
        "list_name": "dicj_frozen_accounts", "name_ja": "（架空）ミドリモータース", "name_kana": "ミドリモータース",
        "account_hint": None, "notice_date": "2026-10-12", "source_ref": "synthetic-dicj-099",
    })
    WatchlistSnapshot.model_validate(snapshot)
    harness.ref_repo.put_snapshot(snapshot)
    # a small, otherwise unremarkable payment to a listed payee (half-width / spaced spellings still match)
    r = await harness.client.post("/v1/score", json=score_body(
        transfer_id="tr-wl", customer_ref="cust-0008", account_id="acct-0008", amount_jpy=20_000, channel="app",
        payee={"name_kana": "ミドリ モータース", "relation": "other_bank", "account_id": None}))
    out = r.json()
    assert out["decision"] == "alert"
    hit = [s for s in out["signals"] if s["tool"] == "check_lists"]
    assert hit and hit[0]["field"] == "watchlist_match" and hit[0]["value"] == "dicj_frozen_accounts"
    assert "synthetic-dicj-099" in hit[0]["statement_en"]


async def test_seed_snapshot_entry_matches_by_name(harness):
    r = await harness.client.post("/v1/score", json=score_body(
        transfer_id="tr-wl2", customer_ref="cust-0008", account_id="acct-0008", amount_jpy=10_000, channel="app",
        payee={"name_kana": "ブルームトレード", "relation": "other_bank"}))
    assert r.json()["decision"] == "alert"
    assert r.json()["signals"][-1]["code"] == "watchlist_match"


async def test_no_watchlist_snapshot_means_no_hits(harness):
    harness.ref_repo.store.delete("watchlist_latest", "latest")
    r = await harness.client.post("/v1/score", json=score_body(
        transfer_id="tr-wl3", customer_ref="cust-0008", account_id="acct-0008", amount_jpy=10_000, channel="app",
        payee={"name_kana": "ブルームトレード", "relation": "other_bank"}))
    assert r.json()["decision"] == "allow"


# ------------------------------------------------------------------ mule pattern needs an amount


async def test_300_yen_to_the_mule_account_is_allowed_but_signals_are_kept(harness):
    r = await harness.client.post("/v1/score", json=score_body(transfer_id="tr-small", amount_jpy=300))
    out = r.json()
    assert out["decision"] == "allow" and out["case_id"] is None
    assert harness.case_svc.opened == []
    vals = signal_values(out)
    assert vals[("counterpart_graph", "account_age_days")] == 4
    assert vals[("counterpart_graph", "distinct_payers_7d")] == 7
    codes = [s["code"] for s in out["signals"]]
    assert "payee_account_age" in codes and "payer_fan_in" in codes
    assert harness.case_repo.get_score("tr-small")["decision"] == "allow"


async def test_mule_pattern_alerts_at_the_floor_and_not_below(harness):
    at = (await harness.client.post("/v1/score", json=score_body(transfer_id="tr-100k", amount_jpy=100_000))).json()
    assert at["decision"] == "alert" and at["case_id"]
    below = (await harness.client.post("/v1/score", json=score_body(transfer_id="tr-99k", amount_jpy=99_999))).json()
    assert below["decision"] == "allow" and below["case_id"] is None


async def test_watchlist_hit_still_alerts_at_300_yen(harness):
    r = await harness.client.post("/v1/score", json=score_body(
        transfer_id="tr-wl-small", customer_ref="cust-0008", account_id="acct-0008", amount_jpy=300, channel="app",
        payee={"name_kana": "ブルームトレード", "relation": "other_bank"}))
    assert r.json()["decision"] == "alert"


def test_mule_floor_setting_is_read_from_the_env(monkeypatch):
    from mimamori_scoring.config import ScoringConfig

    assert ScoringConfig.from_env().mule_alert_min_amount_jpy == 100_000
    monkeypatch.setenv("SCORING_MULE_ALERT_MIN_AMOUNT_JPY", "250000")
    assert ScoringConfig.from_env().mule_alert_min_amount_jpy == 250_000


# ------------------------------------------------------------------ running totals (structuring)


def booked(txn_id: str, account_id: str, at, kind: str, amount: int, *, to_account: str | None = None, to_name: str | None = None) -> BankTransaction:
    return BankTransaction(txn_id=txn_id, account_id=account_id, booked_at=at, kind=kind, amount_jpy=amount, channel="counter",
                           counterparty_account_id=to_account, counterparty_name_kana=to_name)


async def test_thirty_payments_of_90k_to_the_mule_account_alert_from_the_second(harness):
    now = harness.settings.now()
    results = []
    for i in range(30):
        at = now - timedelta(minutes=30 - i)
        out = (await harness.client.post("/v1/score", json=score_body(
            transfer_id=f"tr-struct-{i}", amount_jpy=90_000, occurred_at=at.isoformat()))).json()
        results.append(out)
        harness.bank.state.book(booked(f"txn-struct-{i}", "acct-tanaka-0001", at, "transfer_out", 90_000, to_account="acct-mule-0001"))
    assert results[0]["decision"] == "allow" and results[0]["case_id"] is None
    assert all(r["decision"] == "alert" for r in results[1:])
    second = next(s for s in results[1]["signals"] if s["code"] == "payee_running_total")
    assert (second["tool"], second["field"], second["value"]) == ("recent_transactions", "payee_total_7d_jpy", 180_000)
    assert second["statement_en"] == "2 payments to this payee in 7 days, ¥180,000 in total, including this one"
    last = next(s for s in results[29]["signals"] if s["code"] == "payee_running_total")
    assert last["value"] == 2_700_000
    assert "payee_running_total" not in [s["code"] for s in results[0]["signals"]]
    assert len(harness.case_svc.opened) == 29


async def test_ten_15k_payments_to_ten_payees_in_one_day_is_a_normal_day(harness):
    now = harness.settings.now()
    for i in range(10):
        at = now - timedelta(minutes=60 - i)
        out = (await harness.client.post("/v1/score", json=score_body(
            transfer_id=f"tr-busy-{i}", amount_jpy=15_000, occurred_at=at.isoformat(),
            payee={"name_kana": f"ショップ{i}", "relation": "other_bank", "account_id": None}))).json()
        assert out["decision"] == "allow", out
        assert "outflow_running_total" not in [s["code"] for s in out["signals"]]
        harness.bank.state.book(booked(f"txn-busy-{i}", "acct-tanaka-0001", at, "transfer_out", 15_000, to_name=f"ショップ{i}"))
    assert harness.case_svc.opened == []


async def test_90k_after_500k_of_other_outflows_the_same_day_is_unusual(harness):
    now = harness.settings.now()
    harness.bank.state.book(booked("txn-earlier", "acct-tanaka-0001", now - timedelta(hours=3), "transfer_out", 500_000, to_name="ナニガシ"))
    out = (await harness.client.post("/v1/score", json=score_body(
        transfer_id="tr-day", amount_jpy=90_000, payee={"name_kana": "アタラシイ", "relation": "other_bank", "account_id": None}))).json()
    assert out["decision"] == "alert"
    codes = [s["code"] for s in out["signals"]]
    assert "outflow_running_total" in codes and "amount_vs_baseline" not in codes
    sig = next(s for s in out["signals"] if s["code"] == "outflow_running_total")
    assert (sig["tool"], sig["field"], sig["value"]) == ("recent_transactions", "outflow_24h_jpy", 590_000)
    assert sig["statement_en"] == "¥590,000 paid out in the last 24 hours, including this payment"


async def test_the_april_school_fee_does_not_add_up_with_an_ordinary_payment(harness):
    from mimamori_common.config import Settings
    s = Settings(demo_now="2026-04-10T15:00:00+09:00", store_backend="memory", service_name="scoring")
    harness.app.state.scorer.settings = s
    body = dict(transfer_id="tr-after-fee", amount_jpy=120_000, occurred_at="2026-04-10T15:00:00+09:00",
                payee={"name_kana": "アタラシイ", "relation": "other_bank", "account_id": None})
    out = (await harness.client.post("/v1/score", json=score_body(**body))).json()
    assert out["decision"] == "allow", out
    assert "outflow_running_total" not in [x["code"] for x in out["signals"]]


def test_running_total_settings_are_read_from_the_env(monkeypatch):
    from mimamori_scoring.config import ScoringConfig

    c = ScoringConfig.from_env()
    assert (c.payee_total_days, c.outflow_window_hours) == (7, 24)
    monkeypatch.setenv("SCORING_PAYEE_TOTAL_DAYS", "3")
    monkeypatch.setenv("SCORING_OUTFLOW_WINDOW_HOURS", "12")
    c = ScoringConfig.from_env()
    assert (c.payee_total_days, c.outflow_window_hours) == (3, 12)


# ------------------------------------------------------------------ latency


async def test_score_latency_under_200ms_with_the_fake_bank(harness):
    await harness.client.post("/v1/baselines/refresh")
    durations = []
    for i in range(30):
        t0 = time.perf_counter()
        r = await harness.client.post("/v1/score", json=score_body(transfer_id=f"tr-lat-{i}"))
        durations.append((time.perf_counter() - t0) * 1000)
        assert r.json()["decision"] == "alert"
    print(f"\nwarm /v1/score: median {statistics.median(durations):.1f} ms, max {max(durations):.1f} ms, in-handler {r.json()['latency_ms']} ms")
    assert statistics.median(durations) < 200 and max(durations) < 200


async def test_cold_score_including_baseline_computation_under_200ms(harness):
    t0 = time.perf_counter()
    r = await harness.client.post("/v1/score", json=score_body())
    cold = (time.perf_counter() - t0) * 1000
    print(f"\ncold /v1/score (baseline computed on first use): {cold:.1f} ms")
    assert r.json()["decision"] == "alert" and cold < 200
