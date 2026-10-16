"""The seed must tell the Tanaka story and respect the evaluation date split."""

import statistics
from datetime import date, datetime, timedelta

import jsonschema
from referencing import Registry, Resource

from mimamori_common.config import Settings
from mimamori_common.models import AdvanceWishes
from mimamori_common.schemas import load_schema, schemas_dir
from mimamori_common.seed import EVALUATION_CUTOFF_T, load_all, load_bank_data, manifest, playbooks
from mimamori_common.store import open_case_repo, open_intel_repo, open_ref_repo

DEMO = datetime.fromisoformat("2026-10-13T11:42:00+09:00")


def test_tanaka_history_matches_the_story():
    data = load_bank_data()
    tx = [t for t in data.transactions if t.account_id == "acct-tanaka-0001"]
    assert min(t.booked_at for t in tx).year == 2014 and max(t.booked_at for t in tx) < DEMO
    normal = [t.amount_jpy for t in tx if t.kind == "withdrawal" and t.amount_jpy != 400_000]
    assert statistics.median(normal) == 50_000
    april = [t for t in tx if t.amount_jpy == 400_000]
    assert len(april) == 12 and {t.booked_at.month for t in april} == {4}
    assert not [t for t in tx if t.counterparty_category == "contractor"]  # no contractor payments, ever
    assert max(t.amount_jpy for t in tx if t.booked_at > DEMO - timedelta(days=365)) == 400_000


def test_mule_account_is_new_with_six_prior_payers_from_distinct_customers():
    data = load_bank_data()
    mule = next(a for a in data.accounts if a.account_id == "acct-mule-0001")
    assert (DEMO.date() - date.fromisoformat(mule.opened_on)).days == 4
    assert mule.holder_name_kana == "カ）ミライケンセツ"
    incoming = [t for t in data.transactions if t.account_id == mule.account_id and t.kind == "transfer_in"]
    payers = {t.counterparty_account_id for t in incoming}
    assert len(payers) == 6 and "acct-tanaka-0001" not in payers
    assert all(DEMO - timedelta(days=7) <= t.booked_at <= DEMO for t in incoming)
    assert manifest()["mule"]["distinct_payers_7d_including_pending_tanaka"] == 7
    owners = {a.account_id: a.customer_ref for a in data.accounts}
    assert len({owners[p] for p in payers}) == 6


def test_ordinary_customers_and_referential_integrity():
    data = load_bank_data()
    assert len([c for c in data.customers if c.customer_ref.startswith("cust-0")]) >= 50
    accounts = {a.account_id for a in data.accounts}
    customers = {c.customer_ref for c in data.customers}
    assert all(a.customer_ref in customers for a in data.accounts)
    assert all(t.account_id in accounts for t in data.transactions)
    assert all(t.counterparty_account_id in accounts for t in data.transactions if t.counterparty_account_id)


def test_seeded_wishes_validate_and_load():
    load_all(Settings())
    wishes = open_case_repo().get_active_wishes("cust-tanaka-0001")
    AdvanceWishes.model_validate(wishes)
    assert wishes["cooling_off"]["minimum_hours"] == 4 and wishes["outbound_notice_consent"] is True


def test_playbooks_respect_the_date_split_and_only_approved_are_served():
    for pb in playbooks():
        assert all(date.fromisoformat(s["published_at"]) < EVALUATION_CUTOFF_T for s in pb["sources"]), pb["id"]
    load_all(Settings())
    repo = open_intel_repo()
    assert {p["id"] for p in repo.list_playbooks("approved")} == {
        "pb.fake_police.safe_account", "pb.relative_in_trouble.callback_collector", "pb.gold_bullion.phone_instructed"}
    assert [p["id"] for p in repo.list_playbooks("pending")] == ["pb.other_scam.fee_sms"]
    assert repo.get_question_bank("general")["status"] == "approved"


def test_pending_playbook_matches_the_schema():
    registry = Registry().with_resources((s["$id"], Resource.from_contents(s)) for s in
                                         (load_schema(p.name) for p in schemas_dir().glob("*.json")))
    validator = jsonschema.Draft202012Validator(load_schema("playbook.json"), registry=registry, format_checker=jsonschema.FormatChecker())
    pending = [p for p in playbooks() if p["status"] == "pending"]
    assert pending and all(not list(validator.iter_errors(p)) for p in pending)


def test_watchlist_snapshot_loads():
    load_all(Settings())
    assert open_ref_repo().get_latest_snapshot()["snapshot_id"] == "2026-10-12"


def test_watchlist_snapshot_matches_the_model():
    from mimamori_common.models import WatchlistSnapshot
    from mimamori_common.seed import _read

    WatchlistSnapshot.model_validate(_read("ref", "watchlist-snapshot.json"))
