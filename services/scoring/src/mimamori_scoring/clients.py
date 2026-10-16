"""HTTP clients for the two services Scoring calls: core-bank-mock (read-only) and case-svc."""

from __future__ import annotations

import logging
from datetime import datetime

import httpx
from mimamori_common.models import (
    Account,
    BankTransaction,
    Customer,
    OpenCaseRequest,
    OpenCaseResponse,
    PayersResponse,
)

log = logging.getLogger("scoring.clients")

ALL_TXNS_LIMIT = 100_000


class BankUnavailable(RuntimeError):
    """Core banking could not answer; Scoring cannot score (the caller fails open)."""


class UnknownReference(LookupError):
    """The bank has no such customer or account (404)."""


class BankClient:
    def __init__(self, http: httpx.AsyncClient) -> None:
        self.http = http

    async def _get(self, path: str, **params):
        try:
            resp = await self.http.get(path, params={k: v for k, v in params.items() if v is not None})
            resp.raise_for_status()
            return resp.json()
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 404:
                raise UnknownReference(path) from exc
            raise BankUnavailable(f"GET {path}: {exc!r}") from exc
        except (httpx.HTTPError, ValueError) as exc:
            raise BankUnavailable(f"GET {path}: {exc!r}") from exc

    async def customers(self) -> list[Customer]:
        return [Customer.model_validate(c) for c in await self._get("/customers")]

    async def customer(self, customer_ref: str) -> Customer:
        return Customer.model_validate(await self._get(f"/customers/{customer_ref}"))

    async def accounts_of(self, customer_ref: str) -> list[Account]:
        return [Account.model_validate(a) for a in await self._get("/accounts", customer_ref=customer_ref)]

    async def account(self, account_id: str) -> Account:
        return Account.model_validate(await self._get(f"/accounts/{account_id}"))

    async def transactions(
        self, account_id: str, since: datetime | None = None, until: datetime | None = None,
    ) -> list[BankTransaction]:
        rows = await self._get(
            f"/accounts/{account_id}/transactions",
            since=since.isoformat() if since else None, until=until.isoformat() if until else None,
            limit=ALL_TXNS_LIMIT,
        )
        return [BankTransaction.model_validate(r) for r in rows]

    async def payers(self, account_id: str, days: int) -> PayersResponse:
        return PayersResponse.model_validate(await self._get(f"/accounts/{account_id}/payers", days=days))


class CaseClient:
    def __init__(self, http: httpx.AsyncClient) -> None:
        self.http = http

    async def open_case(self, body: OpenCaseRequest) -> OpenCaseResponse | None:
        """One call per alert; idempotency on transfer_id is the case service's job. Returns None if the
        case service is unreachable (the alert is still returned, without a case id)."""
        try:
            resp = await self.http.post("/cases", json=body.model_dump(mode="json"))
            resp.raise_for_status()
            return OpenCaseResponse.model_validate(resp.json())
        except (httpx.HTTPError, ValueError) as exc:
            log.error("could not open case for transfer %s: %r", body.transfer_id, exc)
            return None
