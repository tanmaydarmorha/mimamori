"""core-bank-mock HTTP API (docs/architecture/api-contracts.md, "core-bank-mock")."""

from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Callable, Literal

import httpx
from fastapi import FastAPI, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from mimamori_common.config import Settings
from mimamori_common.models import (
    Account,
    ApiError,
    BankTransaction,
    Customer,
    Freeze,
    FreezeBody,
    Hold,
    HoldPatch,
    HoldRequest,
    PayersResponse,
    ScoreRequest,
    ScoreResponse,
    Transfer,
    TransferPatch,
    TransferRequest,
    TransferResponse,
)
from mimamori_common.seed import BankData, business_calendar, load_bank_data
from mimamori_common.web import create_app

from .bank import Bank, BankError
from .window import BusinessCalendar

log = logging.getLogger("core-bank-mock")

SERVICE = "core-bank-mock"
SYSTEM_HEADERS = {"X-Mimamori-Role": "system", "X-Mimamori-User": SERVICE}


def create_core_bank_app(
    settings: Settings | None = None,
    *,
    data: BankData | None = None,
    calendar: dict | None = None,
    scoring_transport: httpx.AsyncBaseTransport | None = None,
    now: Callable[[], datetime] | None = None,
) -> FastAPI:
    """Build the app. Tests inject `scoring_transport` (a stub for Scoring) and `now`."""
    settings = settings or Settings.from_env()
    scoring = httpx.AsyncClient(
        base_url=settings.scoring_url,
        transport=scoring_transport,
        timeout=httpx.Timeout(settings.scoring_timeout_s),
        headers=SYSTEM_HEADERS,
    )

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        yield
        await scoring.aclose()

    app = create_app(SERVICE, settings, lifespan=lifespan)
    bank = Bank(
        data or load_bank_data(),
        BusinessCalendar.from_seed(calendar if calendar is not None else business_calendar(), settings.business_day_close),
        now or settings.now,
    )
    app.state.bank = bank
    app.state.scoring = scoring

    @app.exception_handler(BankError)
    async def _bank_error(_: Request, exc: BankError) -> JSONResponse:
        return JSONResponse(ApiError(error=exc.error, detail=exc.detail).model_dump(), status_code=exc.status)

    @app.exception_handler(RequestValidationError)
    async def _invalid(_: Request, exc: RequestValidationError) -> JSONResponse:
        detail = "; ".join(f"{'.'.join(str(p) for p in e['loc'])}: {e['msg']}" for e in exc.errors())
        return JSONResponse(ApiError(error="validation_error", detail=detail).model_dump(), status_code=422)

    async def call_scoring(path: str, req: TransferRequest, transfer_id: str) -> ScoreResponse | None:
        """POST to Scoring; None on any failure (timeout, connection, non-2xx, bad body)."""
        body = ScoreRequest(
            transfer_id=transfer_id, customer_ref=req.customer_ref, account_id=req.account_id, channel=req.channel,
            kind=req.kind, amount_jpy=req.amount_jpy, payee=req.payee, memo=req.memo, occurred_at=bank._now(),
        )
        try:
            # httpx timeouts are per phase; wait_for makes SCORING_TIMEOUT_S the whole-call deadline.
            resp = await asyncio.wait_for(
                scoring.post(path, content=body.model_dump_json(), headers={"Content-Type": "application/json"}),
                timeout=settings.scoring_timeout_s,
            )
            resp.raise_for_status()
            return ScoreResponse.model_validate(resp.json())
        except Exception as exc:  # fail open: any problem with Scoring must not block the transfer (DA 7)
            log.warning("scoring %s unavailable for %s (%s: %s)", path, transfer_id, type(exc).__name__, exc)
            return None

    # ------------------------------------------------------------------ transfers

    @app.post("/transfers", response_model=TransferResponse, tags=["transfers"])
    async def post_transfer(req: TransferRequest) -> TransferResponse:
        bank.validate_transfer(req)
        # The transfer ID is needed by Scoring before the transfer exists, so reserve it first.
        checked = req.channel == "counter" or req.amount_jpy >= settings.large_transfer_threshold_jpy
        if not checked:
            transfer = bank.create_transfer(req, scoring="not_checked", status="executed")
            await call_scoring("/v1/events", req, transfer.transfer_id)  # post-transaction; failures only logged
            return _response(transfer)

        transfer = bank.create_transfer(req, scoring="unavailable", status="pending_alert")
        result = await call_scoring("/v1/score", req, transfer.transfer_id)
        if result is None:
            transfer.scoring = "unavailable"
            bank.execute_now(transfer)
        elif result.decision == "alert":
            transfer.scoring, transfer.case_id = "alert", result.case_id
            log.info("transfer %s pending: alert, case %s", transfer.transfer_id, result.case_id)
        else:
            transfer.scoring = "allow"
            bank.execute_now(transfer)
        return _response(transfer)

    @app.get("/transfers/{transfer_id}", response_model=Transfer, tags=["transfers"])
    def get_transfer(transfer_id: str) -> Transfer:
        return bank.transfer(transfer_id)

    @app.patch("/transfers/{transfer_id}", response_model=Transfer, tags=["transfers"])
    def patch_transfer(transfer_id: str, patch: TransferPatch) -> Transfer:
        return bank.patch_transfer(transfer_id, patch)

    # ------------------------------------------------------------------ read-only bank data

    @app.get("/customers", response_model=list[Customer], tags=["bank data"])
    def list_customers() -> list[Customer]:
        return list(bank.customers.values())

    @app.get("/customers/{ref}", response_model=Customer, tags=["bank data"])
    def get_customer(ref: str) -> Customer:
        return bank.customer(ref)

    @app.get("/accounts", response_model=list[Account], tags=["bank data"])
    def list_accounts(customer_ref: str | None = None) -> list[Account]:
        return bank.list_accounts(customer_ref)

    @app.get("/accounts/{account_id}", response_model=Account, tags=["bank data"])
    def get_account(account_id: str) -> Account:
        return bank.account(account_id)

    @app.get("/accounts/{account_id}/transactions", response_model=list[BankTransaction], tags=["bank data"])
    def get_transactions(
        account_id: str,
        since: datetime | None = None,
        until: datetime | None = None,
        limit: int | None = Query(default=None, ge=0, le=100_000, description="Keep only the most recent N."),
        order: Literal["asc", "desc"] = "asc",
    ) -> list[BankTransaction]:
        return bank.list_transactions(account_id, since, until, limit, order)

    @app.get("/accounts/{account_id}/payers", response_model=PayersResponse, tags=["bank data"])
    def get_payers(account_id: str, days: int = Query(default=7, ge=1, le=365)) -> PayersResponse:
        return bank.payers(account_id, days)

    # ------------------------------------------------------------------ holds and freezes

    @app.post("/holds", response_model=Hold, tags=["holds"])
    def post_hold(req: HoldRequest) -> Hold:
        return bank.place_hold(req)

    @app.get("/holds/{hold_id}", response_model=Hold, tags=["holds"])
    def get_hold(hold_id: str) -> Hold:
        return bank.hold(hold_id)

    @app.patch("/holds/{hold_id}", response_model=Hold, tags=["holds"])
    def patch_hold(hold_id: str, patch: HoldPatch) -> Hold:
        return bank.patch_hold(hold_id, patch)

    @app.post("/freezes", response_model=Freeze, tags=["holds"])
    def post_freeze(body: FreezeBody) -> Freeze:
        return bank.freeze(body)

    return app


def _response(t: Transfer) -> TransferResponse:
    return TransferResponse(transfer_id=t.transfer_id, status=t.status, scoring=t.scoring, case_id=t.case_id, hold_id=t.hold_id)
