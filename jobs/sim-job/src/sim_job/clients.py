"""Thin HTTP clients for core-bank-mock and case-svc, written against docs/architecture/api-contracts.md.

Request bodies are built from `mimamori_common.models` where a model exists, so a contract change breaks
here loudly. Responses are validated with the same models. `transport` lets tests (and the in-package
fake services) run everything over ASGI without a network.

The sim is a `system`-role caller for reads; the teller's own actions (key in the transfer, ask, decide)
carry `X-Mimamori-Role: teller` and the sim teller's ID so the audit trail shows who decided.
"""

from __future__ import annotations

import httpx
from mimamori_common.models import (
    Case,
    DecisionRequest,
    DecisionResponse,
    Playbook,
    TransferResponse,
    TurnRequest,
    TurnResponse,
)

from .params import TELLER_ID


class ServiceError(RuntimeError):
    def __init__(self, service: str, method: str, path: str, status: int, body: str):
        super().__init__(f"{service} {method} {path} -> {status}: {body[:300]}")
        self.status = status


def _headers(role: str, user: str) -> dict:
    return {"X-Mimamori-Role": role, "X-Mimamori-User": user}


class _Base:
    service = "service"

    def __init__(self, base_url: str, *, transport: httpx.AsyncBaseTransport | None = None, timeout_s: float = 120.0):
        self._http = httpx.AsyncClient(base_url=base_url, transport=transport, timeout=timeout_s)

    async def aclose(self) -> None:
        await self._http.aclose()

    async def _call(self, method: str, path: str, *, role="teller", user=TELLER_ID, **kw) -> httpx.Response:
        resp = await self._http.request(method, path, headers=_headers(role, user), **kw)
        if resp.status_code >= 400:
            raise ServiceError(self.service, method, path, resp.status_code, resp.text)
        return resp

    async def healthy(self) -> bool:
        try:
            return (await self._http.get("/healthz")).status_code == 200
        except httpx.HTTPError:
            return False


class CoreBankClient(_Base):
    service = "core-bank-mock"

    async def post_transfer(self, body: dict) -> TransferResponse:
        return TransferResponse.model_validate((await self._call("POST", "/transfers", json=body)).json())

    async def get_transfer(self, transfer_id: str) -> dict:
        return (await self._call("GET", f"/transfers/{transfer_id}", role="system", user="sim-job")).json()


class CaseSvcClient(_Base):
    service = "case-svc"

    async def get_case(self, case_id: str) -> Case:
        return Case.model_validate((await self._call("GET", f"/cases/{case_id}", role="system", user="sim-job")).json())

    async def post_turn(self, case_id: str, speaker: str, text: str) -> TurnResponse:
        body = TurnRequest(speaker=speaker, text=text).model_dump()
        return TurnResponse.model_validate((await self._call("POST", f"/cases/{case_id}/turns", json=body)).json())

    async def post_decision(self, case_id: str, req: DecisionRequest) -> DecisionResponse:
        return DecisionResponse.model_validate(
            (await self._call("POST", f"/cases/{case_id}/decision", json=req.model_dump(mode="json", exclude_none=True))).json())

    async def approved_playbooks(self) -> list[Playbook]:
        rows = (await self._call("GET", "/playbooks", params={"status": "approved"}, role="system", user="sim-job")).json()
        return [Playbook.model_validate(r) for r in rows]
