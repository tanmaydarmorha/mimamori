"""Stubs for the other services, as ASGI apps built from the API contracts (docs/architecture/api-contracts.md).
No code from core-bank-mock, scoring or conversation-svc is imported. The fake bank is deliberately simple: the hold
window is `placed + minimum_hours` capped at `cap_hours` (the real window logic is core-bank-mock's job); PATCH /holds
enforces the contract's override rules."""

from __future__ import annotations

import statistics
from datetime import datetime, timedelta

import httpx
from fastapi import FastAPI
from fastapi.responses import JSONResponse

from mimamori_common.models import (
    Baseline, BankTransaction, CallRequest, CallResponse, Freeze, FreezeBody, Hold, HoldPatch, HoldRequest, KnownPayee,
    PayerRow, PayersResponse, SeasonalItem, Transfer, TransferPatch, TransferRequest,
)
from mimamori_common.seed import load_bank_data


def _err(status: int, error: str, detail: str = "") -> JSONResponse:
    return JSONResponse({"error": error, "detail": detail}, status_code=status)


class FakeBank:
    def __init__(self, now: datetime) -> None:
        data = load_bank_data()
        self.now = now
        self.customers = {c.customer_ref: c for c in data.customers}
        self.accounts = {a.account_id: a for a in data.accounts}
        self.txs: list[BankTransaction] = data.transactions
        self.transfers: dict[str, Transfer] = {}
        self.holds: dict[str, Hold] = {}
        self.freezes: list[Freeze] = []
        self.calls: list[tuple[str, str]] = []
        self.down = False
        self.app = self._build()
        self.transport = httpx.ASGITransport(app=self.app)

    def add_transfer(self, transfer_id: str, req: TransferRequest, status: str = "pending_alert") -> Transfer:
        t = Transfer(transfer_id=transfer_id, status=status, scoring="alert", request=req, created_at=self.now)
        self.transfers[transfer_id] = t
        return t

    def _build(self) -> FastAPI:
        app = FastAPI()

        @app.middleware("http")
        async def log_calls(request, call_next):
            self.calls.append((request.method, request.url.path))
            if self.down:
                return JSONResponse({"error": "down"}, status_code=503)
            return await call_next(request)

        @app.get("/transfers/{tid}")
        def get_transfer(tid: str):
            t = self.transfers.get(tid)
            return t.model_dump(mode="json") if t else _err(404, "not_found", tid)

        @app.patch("/transfers/{tid}")
        def patch_transfer(tid: str, body: TransferPatch):
            t = self.transfers.get(tid)
            if not t:
                return _err(404, "not_found", tid)
            t.status = "executed" if body.action == "execute" else "cancelled"
            return t.model_dump(mode="json")

        @app.get("/customers/{ref}")
        def get_customer(ref: str):
            c = self.customers.get(ref)
            return c.model_dump(mode="json") if c else _err(404, "not_found", ref)

        @app.get("/accounts/{aid}")
        def get_account(aid: str):
            a = self.accounts.get(aid)
            return a.model_dump(mode="json") if a else _err(404, "not_found", aid)

        @app.get("/accounts/{aid}/transactions")
        def transactions(aid: str, since: str | None = None, until: str | None = None, limit: int = 1000):
            out = [t for t in self.txs if t.account_id == aid]
            if since:
                out = [t for t in out if t.booked_at >= datetime.fromisoformat(since)]
            return [t.model_dump(mode="json") for t in out[-limit:]]

        @app.get("/accounts/{aid}/payers")
        def payers(aid: str, days: int = 7):
            since = self.now - timedelta(days=days)
            rows: dict[str, PayerRow] = {}
            for t in self.txs:
                if t.account_id == aid and t.kind == "transfer_in" and t.booked_at >= since and t.counterparty_account_id:
                    src = self.accounts[t.counterparty_account_id]
                    cust = self.customers[src.customer_ref]
                    prev = rows.get(cust.customer_ref)
                    rows[cust.customer_ref] = PayerRow(
                        customer_ref=cust.customer_ref, account_id=src.account_id, display_name_ja=cust.display_name_ja,
                        payments=(prev.payments if prev else 0) + 1, total_jpy=(prev.total_jpy if prev else 0) + t.amount_jpy,
                        last_paid_at=t.booked_at)
            return PayersResponse(account_id=aid, days=days, distinct_payers=len(rows), payers=list(rows.values())).model_dump(mode="json")

        @app.post("/holds")
        def place_hold(body: HoldRequest):
            n = len(self.holds) + 1
            minimum = self.now + timedelta(hours=body.window.minimum_hours)
            cap = self.now + timedelta(hours=body.window.cap_hours)
            hold = Hold(hold_id=f"hold-{n:04d}", account_id=body.account_id, transfer_id=body.transfer_id, case_id=body.case_id,
                        placed_by=body.placed_by, placed_at=self.now, minimum_ends_at=minimum, ends_at=min(minimum, cap),
                        cap_ends_at=cap, status="active", overrides=body.overrides)
            self.holds[hold.hold_id] = hold
            if body.transfer_id in self.transfers:
                self.transfers[body.transfer_id].status = "held"
            return hold.model_dump(mode="json")

        @app.patch("/holds/{hid}")
        def patch_hold(hid: str, body: HoldPatch):
            h = self.holds.get(hid)
            if not h:
                return _err(404, "not_found", hid)
            if body.action == "keep":
                return h.model_dump(mode="json")
            if body.action == "release" and h.overrides and self.now < h.ends_at:
                return _err(409, "hold_active", "only the overrides end a wishes-based hold early")
            if body.action == "override_after_contact_reached" and not (body.contact_reached and "after_contact_reached" in h.overrides):
                return _err(409, "override_not_allowed", "contact not reached or override not on this hold")
            if body.action == "override_after_manager_review":
                if not (body.manager_id and body.second_confirmed_by) or body.second_confirmed_by in (body.manager_id, h.placed_by) \
                        or "after_manager_review_and_second_confirmation" not in h.overrides:
                    return _err(409, "override_not_allowed", "manager review needs a distinct second confirmation")
            h.status, h.released_at, h.release_reason = "released", self.now, f"{body.action}: {body.reason}"
            if h.transfer_id in self.transfers:
                self.transfers[h.transfer_id].status = "released"
            return h.model_dump(mode="json")

        @app.post("/freezes")
        def freeze(body: FreezeBody):
            f = Freeze(freeze_id=f"frz-{len(self.freezes) + 1:04d}", account_id=body.account_id, case_id=body.case_id,
                       approved_by=body.approved_by, frozen_at=self.now, status="frozen")
            self.freezes.append(f)
            self.accounts[body.account_id].status = "frozen"
            return f.model_dump(mode="json")

        return app


class FakeConversation:
    def __init__(self, fail: bool = False) -> None:
        self.calls: list[CallRequest] = []
        self.raw: list[dict] = []
        self.fail = fail
        app = FastAPI()

        @app.post("/calls")
        def post_call(payload: dict):
            self.raw.append(payload)
            if self.fail:
                return _err(503, "down")
            req = CallRequest.model_validate(payload)
            self.calls.append(req)
            return CallResponse(call_id=req.brief.call_id, status="notice_sent", notice_text_ja="お母様の件でご連絡しました。").model_dump(mode="json")

        self.transport = httpx.ASGITransport(app=app)


class FakeScoring:
    """`POST /v1/baselines/{ref}/refresh`: computes a baseline from the seed, as Scoring would lazily."""

    def __init__(self, bank: FakeBank) -> None:
        self.bank = bank
        self.calls: list[str] = []
        app = FastAPI()

        @app.post("/v1/baselines/{ref}/refresh")
        def refresh(ref: str):
            self.calls.append(ref)
            return compute_baseline(bank, ref).model_dump(mode="json")

        self.transport = httpx.ASGITransport(app=app)


def compute_baseline(bank: FakeBank, ref: str) -> Baseline:
    acct = next(a for a in bank.accounts.values() if a.customer_ref == ref)
    tx = [t for t in bank.txs if t.account_id == acct.account_id]
    withdrawals = [t.amount_jpy for t in tx if t.kind == "withdrawal"]
    outs = [t for t in tx if t.kind == "transfer_out"]
    payees: dict[str, KnownPayee] = {}
    for t in outs:
        key = t.counterparty_account_id or t.counterparty_name_kana or "?"
        p = payees.get(key)
        payees[key] = KnownPayee(name_kana=t.counterparty_name_kana or "", account_id=t.counterparty_account_id,
                                 category=t.counterparty_category, payments=(p.payments if p else 0) + 1,
                                 last_paid_on=t.booked_at.date())
    seasonal = [SeasonalItem(key="april_school_fee", month=4, typical_amount_jpy=400000, years_seen=12)] if ref == "cust-tanaka-0001" else []
    return Baseline(
        customer_ref=ref, computed_at=bank.now, customer_tenure_years=bank.customers[ref].tenure_years,
        median_monthly_withdrawal_jpy=int(statistics.median(withdrawals)) if withdrawals else 0,
        p95_withdrawal_jpy=sorted(withdrawals)[int(len(withdrawals) * 0.95)] if withdrawals else 0,
        largest_payment_12m_jpy=max((t.amount_jpy for t in tx if t.booked_at >= bank.now - timedelta(days=365)), default=0),
        contractor_payments_count_12y=sum(1 for t in outs if t.counterparty_category == "contractor"),
        known_payees=list(payees.values()), seasonal_items=seasonal)
