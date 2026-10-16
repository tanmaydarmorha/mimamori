"""In-process stand-ins for the services Scoring calls, built on the synthetic seed.

`fake_bank_app` serves the read endpoints of core-bank-mock from `mimamori_common.seed.load_bank_data()`;
`FakeCaseSvc` stubs `POST /cases` (idempotent on `transfer_id`, like the real one).
"""

from __future__ import annotations

from datetime import datetime, timedelta

from fastapi import FastAPI, HTTPException
from mimamori_common.models import OpenCaseRequest, OpenCaseResponse, PayerRow, PayersResponse
from mimamori_common.seed import BankData, load_bank_data


def fake_bank_app(now: datetime, data: BankData | None = None) -> FastAPI:
    data = data or load_bank_data()
    app = FastAPI()
    customers = {c.customer_ref: c for c in data.customers}
    accounts = {a.account_id: a for a in data.accounts}
    by_account: dict[str, list] = {}
    for t in sorted(data.transactions, key=lambda t: t.booked_at):
        by_account.setdefault(t.account_id, []).append(t)
    app.state.calls = []

    def book(txn) -> None:
        """Book a row after the fact, as the bank does when a transfer executes (rows go in time order)."""
        by_account.setdefault(txn.account_id, []).append(txn)

    app.state.book = book

    @app.get("/customers")
    async def list_customers():
        app.state.calls.append("customers")
        return [c.model_dump(mode="json") for c in data.customers]

    @app.get("/customers/{ref}")
    async def get_customer(ref: str):
        app.state.calls.append(f"customer {ref}")
        if ref not in customers:
            raise HTTPException(404)
        return customers[ref].model_dump(mode="json")

    @app.get("/accounts")
    async def list_accounts(customer_ref: str | None = None):
        app.state.calls.append(f"accounts of {customer_ref}")
        return [a.model_dump(mode="json") for a in data.accounts if customer_ref in (None, a.customer_ref)]

    @app.get("/accounts/{account_id}")
    async def get_account(account_id: str):
        app.state.calls.append(f"account {account_id}")
        if account_id not in accounts:
            raise HTTPException(404)
        return accounts[account_id].model_dump(mode="json")

    @app.get("/accounts/{account_id}/transactions")
    async def transactions(account_id: str, since: datetime | None = None, until: datetime | None = None, limit: int = 500):
        app.state.calls.append(f"transactions {account_id}")
        rows = [t for t in by_account.get(account_id, []) if (not since or t.booked_at >= since) and (not until or t.booked_at <= until)]
        return [t.model_dump(mode="json") for t in rows[-limit:]]

    @app.get("/accounts/{account_id}/payers")
    async def payers(account_id: str, days: int = 7):
        app.state.calls.append(f"payers {account_id}")
        since = now - timedelta(days=days)
        grouped: dict[str, list] = {}
        for t in by_account.get(account_id, []):
            if t.kind == "transfer_in" and t.counterparty_account_id and since <= t.booked_at <= now:
                grouped.setdefault(t.counterparty_account_id, []).append(t)
        rows = []
        for payer_account, txs in grouped.items():
            acct = accounts[payer_account]
            rows.append(PayerRow(
                customer_ref=acct.customer_ref, account_id=payer_account,
                display_name_ja=customers[acct.customer_ref].display_name_ja, payments=len(txs),
                total_jpy=sum(t.amount_jpy for t in txs), last_paid_at=max(t.booked_at for t in txs),
            ))
        return PayersResponse(account_id=account_id, days=days, distinct_payers=len(rows), payers=rows).model_dump(mode="json")

    return app


class FakeCaseSvc:
    def __init__(self, fail: bool = False) -> None:
        self.app = FastAPI()
        self.opened: list[OpenCaseRequest] = []
        self.by_transfer: dict[str, OpenCaseResponse] = {}
        self.fail = fail

        @self.app.post("/cases")
        async def open_case(body: OpenCaseRequest):
            if self.fail:
                raise HTTPException(503, "down")
            self.opened.append(body)
            if body.transfer_id not in self.by_transfer:
                self.by_transfer[body.transfer_id] = OpenCaseResponse(case_id=f"case-2026-1013-{len(self.by_transfer) + 1:04d}", status="open")
            return self.by_transfer[body.transfer_id].model_dump(mode="json")
