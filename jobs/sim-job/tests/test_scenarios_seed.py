import json
from datetime import datetime, timedelta

from mimamori_common.models import TransferRequest
from mimamori_common.seed import load_bank_data

from sim_job.heldout import load_heldout, to_scenarios
from sim_job.scenarios import synthetic_scenarios
from sim_job.seedgen import build_seed


def _all():
    return synthetic_scenarios() + to_scenarios(load_heldout())


def test_scenario_set_shape_and_unique_ids():
    syn = synthetic_scenarios()
    assert len(syn) == 24
    assert sum(s.ground_truth == "scam" for s in syn) == 12
    ids = [s.id for s in _all()]
    assert len(ids) == len(set(ids))
    refs = [s.customer_ref for s in _all()]
    assert len(refs) == len(set(refs)), "one synthetic customer per scenario: no shared account state"


def test_transfer_bodies_match_the_api_contract_models():
    for s in _all():
        req = TransferRequest.model_validate(s.transfer_body("sim-teller"))
        assert req.channel == "counter" and req.amount_jpy == s.amount_jpy
        if s.kind == "transfer":
            assert req.payee is not None
            assert (req.payee.relation == "same_bank") == (req.payee.account_id is not None)
        else:
            assert req.payee is None


def test_extended_seed_loads_with_the_shared_models_and_is_consistent(tmp_path, monkeypatch):
    scenarios = _all()
    out = tmp_path / "sim-seed"
    summary = build_seed(scenarios, out)
    monkeypatch.setenv("MIMAMORI_SEED_DIR", str(out))
    bank = load_bank_data()  # validates every row with Customer / Account / BankTransaction
    accounts = {a.account_id: a for a in bank.accounts}
    customers = {c.customer_ref for c in bank.customers}
    for s in scenarios:
        assert s.account_id in accounts and s.customer_ref in customers
        assert accounts[s.account_id].customer_ref == s.customer_ref
        if s.payee_account_id():
            assert s.payee_account_id() in accounts
    assert len(summary["added_customers"]) == len([s for s in scenarios if s.new_customer])
    assert (out / "manifest.json").exists() and (out / "sim-scenarios.json").exists()
    assert "tanaka" in json.dumps(json.loads((out / "sim-scenarios.json").read_text()))


def test_new_mule_accounts_are_young_with_the_requested_fan_in(tmp_path, monkeypatch):
    out = tmp_path / "s"
    scenarios = synthetic_scenarios()
    build_seed(scenarios, out)
    monkeypatch.setenv("MIMAMORI_SEED_DIR", str(out))
    bank = load_bank_data()
    demo = datetime.fromisoformat(json.loads((out / "manifest.json").read_text())["demo_now"])
    s3 = next(s for s in scenarios if s.id == "syn-scam-03")  # fan_in 6, age 5 days
    acct = next(a for a in bank.accounts if a.account_id == s3.payee_account_id())
    assert (demo.date() - datetime.fromisoformat(acct.opened_on).date()) == timedelta(days=5)
    payers = {t.counterparty_account_id for t in bank.transactions
              if t.account_id == acct.account_id and t.kind == "transfer_in"}
    assert len(payers) == 6
    # every fan-in row has its paired transfer_out on the payer's account (the payers endpoint relies on both)
    outs = [t for t in bank.transactions if t.kind == "transfer_out" and t.counterparty_account_id == acct.account_id]
    assert len(outs) == 6


def test_known_payee_scenario_has_prior_payments_and_ordinary_history(tmp_path, monkeypatch):
    out = tmp_path / "s"
    scenarios = synthetic_scenarios()
    build_seed(scenarios, out)
    monkeypatch.setenv("MIMAMORI_SEED_DIR", str(out))
    bank = load_bank_data()
    s6 = next(s for s in scenarios if s.id == "syn-legit-06")
    prior = [t for t in bank.transactions if t.account_id == s6.account_id and t.counterparty_account_id == s6.payee_account_id()]
    assert len(prior) == 2
    history = [t for t in bank.transactions if t.account_id == s6.account_id]
    assert len(history) > 100  # 36 months of income, withdrawals, utilities
    assert max(t.amount_jpy for t in history if t.kind == "withdrawal") <= 100_000  # nothing near the scenario amounts


def test_seed_build_is_deterministic(tmp_path):
    a, b = tmp_path / "a", tmp_path / "b"
    build_seed(synthetic_scenarios(), a)
    build_seed(synthetic_scenarios(), b)
    for name in ("customers", "accounts", "transactions"):
        assert (a / "bank" / f"{name}.json").read_text() == (b / "bank" / f"{name}.json").read_text()


def test_base_seed_is_untouched_in_the_copy(tmp_path, monkeypatch):
    out = tmp_path / "s"
    build_seed(synthetic_scenarios(), out)
    monkeypatch.setenv("MIMAMORI_SEED_DIR", str(out))
    bank = load_bank_data()
    assert any(c.customer_ref == "cust-tanaka-0001" for c in bank.customers)
    assert any(a.account_id == "acct-mule-0001" for a in bank.accounts)
