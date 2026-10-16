from __future__ import annotations

import json
from datetime import datetime, timedelta

import httpx
import pytest
from fastapi.testclient import TestClient

from core_bank_mock.app import create_core_bank_app
from mimamori_common.config import JST, Settings
from mimamori_common.seed import load_bank_data, manifest

DEMO_NOW = datetime.fromisoformat("2026-10-13T11:42:00+09:00")  # a Tuesday

TANAKA_TRANSFER = {
    "customer_ref": "cust-tanaka-0001",
    "account_id": "acct-tanaka-0001",
    "channel": "counter",
    "kind": "transfer",
    "amount_jpy": 3_000_000,
    "payee": {"name_kana": "カ）ミライケンセツ", "relation": "same_bank", "account_id": "acct-mule-0001"},
    "teller_id": "teller-01",
}

WINDOW = {"minimum_hours": 4, "extend_to_next_business_day_close": True, "cap_hours": 24}
BOTH_OVERRIDES = ["after_contact_reached", "after_manager_review_and_second_confirmation"]


class Clock:
    def __init__(self, t: datetime = DEMO_NOW):
        self.t = t

    def __call__(self) -> datetime:
        return self.t.astimezone(JST)

    def set(self, iso: str) -> None:
        self.t = datetime.fromisoformat(iso)

    def advance(self, **kw) -> None:
        self.t += timedelta(**kw)


class FakeScoring:
    """Stands in for the Scoring service behind an httpx.MockTransport."""

    def __init__(self):
        self.requests: list[tuple[str, dict]] = []
        self.mode = "allow"  # allow | alert | error | timeout | connect_error | garbage | slow
        self.case_id = "case-2026-1013-0001"

    async def handle(self, request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        self.requests.append((request.url.path, body))
        if self.mode == "timeout":
            raise httpx.ReadTimeout("scoring too slow", request=request)
        if self.mode == "connect_error":
            raise httpx.ConnectError("scoring down", request=request)
        if self.mode == "error":
            return httpx.Response(503, json={"error": "down"})
        if self.mode == "garbage":
            return httpx.Response(200, text="<html>not json</html>")
        if self.mode == "slow":
            import asyncio

            await asyncio.sleep(2)
        decision = "alert" if self.mode == "alert" else "allow"
        payload = {"decision": decision, "signals": [], "scored_at": "2026-10-13T11:42:00+09:00"}
        if decision == "alert":
            payload["case_id"] = self.case_id
        return httpx.Response(200, json=payload)

    def paths(self) -> list[str]:
        return [p for p, _ in self.requests]


@pytest.fixture(scope="session")
def bank_data():
    return load_bank_data()


@pytest.fixture
def clock():
    return Clock()


@pytest.fixture
def scoring():
    return FakeScoring()


@pytest.fixture
def settings():
    return Settings(scoring_timeout_s=0.5, demo_now=None)


@pytest.fixture
def client(settings, scoring, clock, bank_data):
    app = create_core_bank_app(
        settings, data=bank_data.__class__(
            customers=list(bank_data.customers),
            accounts=[a.model_copy() for a in bank_data.accounts],
            transactions=list(bank_data.transactions),
        ),
        scoring_transport=httpx.MockTransport(scoring.handle), now=clock,
    )
    with TestClient(app) as c:
        c.bank = app.state.bank
        yield c


@pytest.fixture(scope="session")
def mani():
    return manifest()


def place_hold(client, transfer_id, overrides=None, window=None, placed_by="teller-01"):
    return client.post("/holds", json={
        "account_id": "acct-tanaka-0001", "transfer_id": transfer_id, "case_id": "case-2026-1013-0001",
        "placed_by": placed_by, "window": window or WINDOW, "overrides": BOTH_OVERRIDES if overrides is None else overrides,
    })
