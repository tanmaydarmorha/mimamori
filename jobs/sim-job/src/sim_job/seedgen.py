"""Build the sim's synthetic bank: an extended copy of `seed/` that core-bank-mock is started against.

    sim-job seed --out /tmp/sim-seed
    MIMAMORI_SEED_DIR=/tmp/sim-seed  (core-bank-mock, scoring, case-svc, conversation-svc)

Core-bank-mock's API is read-only for bank data (api-contracts.md), so the sim cannot push customers
into a running instance; it hands the services a seed directory instead. The base seed (Tanaka, the
fan-in mule, 56 ordinary customers, company accounts) is copied unchanged; the scenarios' extra
customers, payee accounts and fan-in rows are appended. Deterministic: same inputs, same files.
Synthetic only: invented names, IDs and amounts.
"""

from __future__ import annotations

import json
import random
import shutil
from datetime import date, datetime, timedelta
from pathlib import Path

from mimamori_common.config import JST
from mimamori_common.seed import manifest, seed_dir

from .scenarios import CustomerSpec, Scenario

BRANCH = "サンプル銀行 駅前支店"
ORDINARY_POOL = [f"cust-{n:04d}" for n in range(1, 57)]
MULE_PAYERS_IN_BASE = {"cust-0002", "cust-0011", "cust-0023", "cust-0034", "cust-0041", "cust-0052"}


def _at(day: date, rng: random.Random, hour: int | None = None) -> datetime:
    return datetime(day.year, day.month, day.day, hour if hour is not None else rng.randint(9, 15), rng.randint(0, 59), tzinfo=JST)


def _month_back(d: date, n: int) -> date:
    y, m = d.year, d.month - n
    while m <= 0:
        y, m = y - 1, m + 12
    return date(y, m, min(d.day, 28))


class _Bank:
    def __init__(self, base: Path):
        self.customers = json.loads((base / "bank" / "customers.json").read_text())
        self.accounts = json.loads((base / "bank" / "accounts.json").read_text())
        self.txns = json.loads((base / "bank" / "transactions.json").read_text())
        self.n = 0

    def customer(self, ref, ja, kana, tenure, account_id, opened_on: date, balance=12_000_000):
        self.customers.append({"customer_ref": ref, "display_name_ja": ja, "display_name_kana": kana,
                               "tenure_years": tenure, "branch_name_ja": BRANCH})
        self.accounts.append({"account_id": account_id, "customer_ref": ref, "holder_name_kana": kana,
                              "branch_name_ja": BRANCH, "opened_on": opened_on.isoformat(), "balance_jpy": balance,
                              "status": "active"})

    def txn(self, account_id, when: datetime, kind, amount, channel, cp_account=None, cp_name=None, cp_cat=None, memo=None):
        self.n += 1
        self.txns.append({"txn_id": f"txn-sim-{self.n:06d}", "account_id": account_id, "booked_at": when.isoformat(),
                          "kind": kind, "amount_jpy": amount, "channel": channel, "counterparty_account_id": cp_account,
                          "counterparty_name_kana": cp_name, "counterparty_category": cp_cat, "memo": memo})


def _ledger(bank: _Bank, spec: CustomerSpec, account_id: str, demo: date, seed: int) -> None:
    """36 months of ordinary activity: income, ATM withdrawals around the median, a utilities debit."""
    rng = random.Random(f"{seed}:{spec.ref}")
    for k in range(36, 0, -1):
        month = _month_back(demo.replace(day=1), k)
        income_day = date(month.year, month.month, 25)
        bank.txn(account_id, _at(income_day, rng, 9), "deposit", spec.income_jpy, "system",
                 cp_name="コウセイネンキン", cp_cat="pension")
        for _ in range(rng.choice([1, 1, 2])):
            amount = int(round(spec.median_withdrawal_jpy * rng.uniform(0.8, 1.2), -4)) or 10_000
            bank.txn(account_id, _at(date(month.year, month.month, rng.randint(3, 22)), rng), "withdrawal", amount, "atm")
        bank.txn(account_id, _at(date(month.year, month.month, 27), rng, 9), "direct_debit", rng.randint(14, 22) * 1000,
                 "system", cp_name="デンキ ガス スイドウ", cp_cat="utilities")


def _payee_account(bank: _Bank, sc: Scenario, demo: date, seed: int, used_payers: set[str]) -> None:
    p = sc.payee
    if not p or p.kind not in ("new_mule", "company"):
        return
    rng = random.Random(f"{seed}:{sc.id}:payee")
    account_id = sc.payee_account_id()
    ref = f"cust-sim-{p.kind}-{sc.id}"
    age = p.age_days if p.age_days is not None else 2900
    opened = demo - timedelta(days=age)
    bank.customer(ref, p.name_kana, p.name_kana, max(age // 365, 0), account_id, opened, balance=9_000_000)
    if p.kind == "new_mule":
        pool = [c for c in ORDINARY_POOL if c not in MULE_PAYERS_IN_BASE and c not in used_payers]
        kana = {c["customer_ref"]: c["display_name_kana"] for c in bank.customers}
        for ref_payer in rng.sample(pool, p.fan_in):
            used_payers.add(ref_payer)
            payer_acct = "acct-" + ref_payer.removeprefix("cust-")
            when = _at(max(opened, demo - timedelta(days=rng.randint(1, 5))), rng)
            amount = rng.choice([400_000, 600_000, 800_000, 1_200_000])
            bank.txn(payer_acct, when, "transfer_out", amount, "counter", account_id, p.name_kana, "company", "工事代金")
            bank.txn(account_id, when, "transfer_in", amount, "counter", payer_acct, kana[ref_payer], "individual")


def _prior_payments(bank: _Bank, sc: Scenario, demo: date, rng: random.Random) -> None:
    p = sc.payee
    n = p.prior_payments if p else 0
    if not n:
        return
    for i in range(n):
        when = _at(demo - timedelta(days=45 * (i + 1)), rng)
        bank.txn(sc.account_id, when, "transfer_out", 800_000, "counter", sc.payee_account_id(), p.name_kana, "contractor",
                 "工事代金")


def build_seed(scenarios: list[Scenario], out: Path, seed: int = 20261013) -> dict:
    """Write the extended seed directory. Returns a summary (counts, mule accounts)."""
    base = seed_dir()
    out = Path(out)
    if out.exists():
        shutil.rmtree(out)
    shutil.copytree(base, out)
    demo = datetime.fromisoformat(manifest()["demo_now"]).date()
    bank = _Bank(base)
    used_payers: set[str] = set()
    existing_refs = {c["customer_ref"] for c in bank.customers}
    created = []
    for sc in scenarios:
        rng = random.Random(f"{seed}:{sc.id}")
        if sc.new_customer is not None:
            spec = sc.new_customer
            if spec.ref in existing_refs:
                raise ValueError(f"{sc.id}: customer {spec.ref} already exists")
            existing_refs.add(spec.ref)
            bank.customer(spec.ref, spec.name_ja, spec.name_kana, spec.tenure_years, sc.account_id,
                          demo - timedelta(days=365 * spec.tenure_years))
            _ledger(bank, spec, sc.account_id, demo, seed)
            created.append(spec.ref)
        _payee_account(bank, sc, demo, seed, used_payers)
        _prior_payments(bank, sc, demo, rng)
    (out / "bank" / "customers.json").write_text(json.dumps(bank.customers, ensure_ascii=False, indent=1))
    (out / "bank" / "accounts.json").write_text(json.dumps(bank.accounts, ensure_ascii=False, indent=1))
    (out / "bank" / "transactions.json").write_text(json.dumps(bank.txns, ensure_ascii=False, indent=1))
    summary = {
        "note": "Synthetic. Extended copy of seed/ for the sim-job evaluation. Start the services with MIMAMORI_SEED_DIR pointing here.",
        "base_seed": str(base),
        "demo_now": manifest()["demo_now"],
        "added_customers": created,
        "scenarios": [{"id": s.id, "ground_truth": s.ground_truth, "customer_ref": s.customer_ref,
                       "account_id": s.account_id, "kind": s.kind, "amount_jpy": s.amount_jpy,
                       "payee_account_id": s.payee_account_id(), "has_wishes": s.has_wishes} for s in scenarios],
    }
    (out / "sim-scenarios.json").write_text(json.dumps(summary, ensure_ascii=False, indent=1))
    return summary
