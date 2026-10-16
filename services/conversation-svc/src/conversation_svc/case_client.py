"""Reports the call outcome to case-svc: `POST /cases/{id}/contact-outcome`. The only thing this
service ever sends back, and the only outbound call it makes."""

from __future__ import annotations

import asyncio
import logging
from typing import Protocol

import httpx
from mimamori_common.models import ContactOutcomeRequest

log = logging.getLogger("conversation_svc.case_client")


class OutcomeSink(Protocol):
    async def post_outcome(self, case_id: str, outcome: ContactOutcomeRequest) -> bool: ...


class CaseSvcClient:
    def __init__(self, base_url: str, timeout_s: float = 5.0, retries: int = 3,
                 transport: httpx.AsyncBaseTransport | None = None) -> None:
        self.base_url, self.timeout_s, self.retries, self._transport = base_url.rstrip("/"), timeout_s, retries, transport

    async def post_outcome(self, case_id: str, outcome: ContactOutcomeRequest) -> bool:
        url = f"{self.base_url}/cases/{case_id}/contact-outcome"
        headers = {"X-Mimamori-Role": "system", "X-Mimamori-User": "conversation-svc"}
        for attempt in range(1, self.retries + 1):
            try:
                async with httpx.AsyncClient(timeout=self.timeout_s, transport=self._transport) as http:
                    resp = await http.post(url, json=outcome.model_dump(mode="json", exclude_none=True), headers=headers)
                if resp.status_code < 300:
                    return True
                log.warning("contact-outcome %s -> HTTP %s (attempt %s)", case_id, resp.status_code, attempt)
                if resp.status_code < 500:
                    return False  # 4xx will not get better by retrying
            except httpx.HTTPError as err:
                log.warning("contact-outcome %s failed: %s (attempt %s)", case_id, type(err).__name__, attempt)
            await asyncio.sleep(0.2 * attempt)
        return False
