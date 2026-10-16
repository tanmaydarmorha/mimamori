"""HTTP clients for the services case-svc calls (contracts: docs/architecture/api-contracts.md).
Each takes an optional `transport` so tests can stub the other service with httpx.MockTransport or
an ASGI app. Other services' code is never imported."""

from __future__ import annotations

from typing import Any

import httpx

from mimamori_common.models import (
    Account, BankTransaction, CallRequest, CallResponse, Customer, Freeze, FreezeBody, Hold, HoldPatch,
    HoldRequest, PayersResponse, Transfer, TransferPatch,
)

from .errors import ApiProblem

SYSTEM_HEADERS = {"X-Mimamori-Role": "system", "X-Mimamori-User": "case-svc"}


class _Base:
    service = "upstream"

    def __init__(self, base_url: str, transport: httpx.AsyncBaseTransport | None = None, timeout_s: float = 10.0) -> None:
        self.base_url, self._transport, self.timeout_s = base_url.rstrip("/"), transport, timeout_s

    async def _request(self, method: str, path: str, *, json: Any = None, params: dict | None = None) -> Any:
        try:
            async with httpx.AsyncClient(base_url=self.base_url, transport=self._transport, timeout=self.timeout_s,
                                         headers=SYSTEM_HEADERS) as http:
                resp = await http.request(method, path, json=json, params=params)
        except httpx.HTTPError as err:
            raise ApiProblem(503, "dependency_unavailable", f"{self.service}: {err!r}") from err
        if resp.status_code >= 500:
            raise ApiProblem(503, "dependency_unavailable", f"{self.service} {resp.status_code}")
        if resp.status_code >= 400:
            try:
                body = resp.json()
            except ValueError:
                body = {}
            detail = body.get("detail") if isinstance(body, dict) else None
            error = body.get("error", "upstream_error") if isinstance(body, dict) else "upstream_error"
            raise ApiProblem(resp.status_code if resp.status_code in (404, 409, 422) else 502, error,
                             f"{self.service}: {detail}")
        return resp.json()


class CoreBankClient(_Base):
    service = "core-bank-mock"

    async def get_transfer(self, transfer_id: str) -> Transfer:
        return Transfer.model_validate(await self._request("GET", f"/transfers/{transfer_id}"))

    async def patch_transfer(self, transfer_id: str, patch: TransferPatch) -> Transfer:
        return Transfer.model_validate(await self._request("PATCH", f"/transfers/{transfer_id}", json=patch.model_dump(mode="json")))

    async def get_customer(self, ref: str) -> Customer:
        return Customer.model_validate(await self._request("GET", f"/customers/{ref}"))

    async def get_account(self, account_id: str) -> Account:
        return Account.model_validate(await self._request("GET", f"/accounts/{account_id}"))

    async def transactions(self, account_id: str, since: str | None = None, until: str | None = None,
                           limit: int | None = None) -> list[BankTransaction]:
        params = {k: v for k, v in {"since": since, "until": until, "limit": limit}.items() if v is not None}
        data = await self._request("GET", f"/accounts/{account_id}/transactions", params=params)
        return [BankTransaction.model_validate(t) for t in data]

    async def payers(self, account_id: str, days: int = 7) -> PayersResponse:
        return PayersResponse.model_validate(await self._request("GET", f"/accounts/{account_id}/payers", params={"days": days}))

    async def place_hold(self, body: HoldRequest) -> Hold:
        return Hold.model_validate(await self._request("POST", "/holds", json=body.model_dump(mode="json")))

    async def patch_hold(self, hold_id: str, body: HoldPatch) -> Hold:
        return Hold.model_validate(await self._request("PATCH", f"/holds/{hold_id}", json=body.model_dump(mode="json")))

    async def freeze(self, body: FreezeBody) -> Freeze:
        return Freeze.model_validate(await self._request("POST", "/freezes", json=body.model_dump(mode="json")))


class ScoringClient(_Base):
    service = "scoring"

    async def refresh_baseline(self, customer_ref: str) -> dict:
        return await self._request("POST", f"/v1/baselines/{customer_ref}/refresh")


class ConversationClient(_Base):
    service = "conversation-svc"

    async def post_call(self, body: CallRequest) -> CallResponse:
        return CallResponse.model_validate(await self._request("POST", "/calls", json=body.model_dump(mode="json", exclude_none=True)))
