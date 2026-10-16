from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

import httpx
import pytest
from fakes import FakeCaseSvc, fake_bank_app
from mimamori_common.config import Settings
from mimamori_common.models import ScoreRequest
from mimamori_common.seed import load_bank_data, load_ref_db, manifest
from mimamori_common.store import open_case_repo, open_ref_repo, reset_memory_stores
from mimamori_scoring.app import create_scoring_app
from mimamori_scoring.config import ScoringConfig

DEMO_NOW = "2026-10-13T11:42:00+09:00"


@pytest.fixture(scope="session")
def bank_data():
    return load_bank_data()


@pytest.fixture(scope="session")
def seed_manifest():
    return manifest()


@pytest.fixture
def settings():
    return Settings(demo_now=DEMO_NOW, store_backend="memory", service_name="scoring")


@dataclass
class Harness:
    client: httpx.AsyncClient
    app: object
    bank: object
    case_svc: FakeCaseSvc
    settings: Settings
    case_repo: object
    ref_repo: object


@pytest.fixture
async def harness(settings, bank_data):
    reset_memory_stores()
    bank = fake_bank_app(settings.now(), bank_data)
    case_svc = FakeCaseSvc()
    case_repo, ref_repo = open_case_repo(settings), open_ref_repo(settings)
    load_ref_db(ref_repo)
    cfg = ScoringConfig(watchlist_ttl_s=0.0, warm_on_start=False)
    app = create_scoring_app(
        settings, cfg,
        bank_http=httpx.AsyncClient(transport=httpx.ASGITransport(app=bank), base_url="http://bank"),
        case_http=httpx.AsyncClient(transport=httpx.ASGITransport(app=case_svc.app), base_url="http://case"),
        case_repo=case_repo, ref_repo=ref_repo, warm_on_start=False,
    )
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://scoring") as client:
        yield Harness(client, app, bank, case_svc, settings, case_repo, ref_repo)
    reset_memory_stores()


def score_body(**kw) -> dict:
    base = dict(
        transfer_id="tr-test-0001", customer_ref="cust-tanaka-0001", account_id="acct-tanaka-0001",
        channel="counter", kind="transfer", amount_jpy=3_000_000, occurred_at=DEMO_NOW,
        payee={"name_kana": "カ）ミライケンセツ", "relation": "same_bank", "account_id": "acct-mule-0001"},
    )
    base.update(kw)
    return ScoreRequest.model_validate(base).model_dump(mode="json")


def parse(ts: str) -> datetime:
    return datetime.fromisoformat(ts)
