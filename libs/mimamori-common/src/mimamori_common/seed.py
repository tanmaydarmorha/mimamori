"""Load the synthetic seed (`seed/`) into the stores, and read the core-banking seed data.

    load_case_db(repo)   advance wishes (Tanaka)
    load_intel_db(repo)  approved playbooks, the general question bank, one pending playbook
    load_ref_db(repo)    watchlist snapshot
    load_bank_data()     customers, accounts, transactions for core-bank-mock (its own store, not case-db)

Located like schemas/: $MIMAMORI_SEED_DIR, /app/seed, then <repo>/seed. CLI: `python seed/load.py`.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from .config import Settings
from .models import Account, BankTransaction, Customer
from .schemas import load_example
from .store import CaseRepo, IntelRepo, RefRepo, open_case_repo, open_intel_repo, open_ref_repo

EVALUATION_CUTOFF_T = date(2026, 4, 1)  # playbooks used in evaluation must be published before this (CR 16, CR 28)


def seed_dir() -> Path:
    candidates = [Path(p) for p in [os.environ.get("MIMAMORI_SEED_DIR", ""), "/app/seed"] if p]
    candidates.append(Path(__file__).resolve().parents[4] / "seed")
    for path in candidates:
        if (path / "manifest.json").exists():
            return path
    raise FileNotFoundError(f"seed/ not found; looked in {[str(c) for c in candidates]}. Set MIMAMORI_SEED_DIR.")


def _read(*parts: str):
    return json.loads(seed_dir().joinpath(*parts).read_text())


def manifest() -> dict:
    return _read("manifest.json")


def business_calendar() -> dict:
    return _read("business-calendar.json")


@dataclass
class BankData:
    customers: list[Customer]
    accounts: list[Account]
    transactions: list[BankTransaction]


def load_bank_data() -> BankData:
    return BankData(
        customers=[Customer.model_validate(c) for c in _read("bank", "customers.json")],
        accounts=[Account.model_validate(a) for a in _read("bank", "accounts.json")],
        transactions=[BankTransaction.model_validate(t) for t in _read("bank", "transactions.json")],
    )


def playbooks() -> list[dict]:
    return load_example("playbooks.json") + _read("intel", "playbook-pending.json")


def load_case_db(repo: CaseRepo) -> None:
    repo.put_wishes(load_example("advance-wishes-tanaka.json"))


def load_intel_db(repo: IntelRepo) -> None:
    for pb in playbooks():
        repo.put_playbook(pb)
    repo.put_question_bank(load_example("question-bank-general.json"))


def load_ref_db(repo: RefRepo) -> None:
    repo.put_snapshot(_read("ref", "watchlist-snapshot.json"))


def load_all(settings: Settings | None = None) -> None:
    settings = settings or Settings.from_env()
    load_case_db(open_case_repo(settings))
    load_intel_db(open_intel_repo(settings))
    load_ref_db(open_ref_repo(settings))
