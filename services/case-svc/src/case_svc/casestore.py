"""Persistence helpers over `CaseRepo` (case-db): cases, derived card, internal state, events, audit,
and the SSE fan-out. The card is a *view* rebuilt from the internal state (see card.py)."""

from __future__ import annotations

import asyncio
from collections import defaultdict
from datetime import datetime
from typing import Any

from mimamori_common.config import Settings
from mimamori_common.store import CaseRepo

from .errors import not_found

OPEN_STATUSES = {"open", "paused"}


class EventHub:
    """In-process fan-out of persisted events to SSE subscribers."""

    def __init__(self) -> None:
        self._subs: dict[str, list[asyncio.Queue]] = defaultdict(list)

    def subscribe(self, case_id: str) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue()
        self._subs[case_id].append(q)
        return q

    def unsubscribe(self, case_id: str, q: asyncio.Queue) -> None:
        if q in self._subs.get(case_id, []):
            self._subs[case_id].remove(q)

    def publish(self, event: dict) -> None:
        for q in list(self._subs.get(event["case_id"], [])):
            q.put_nowait(event)


class CaseStore:
    def __init__(self, repo: CaseRepo, settings: Settings, hub: EventHub | None = None) -> None:
        self.repo, self.settings, self.hub = repo, settings, hub or EventHub()
        self._locks: dict[str, asyncio.Lock] = {}
        self._turn_locks: dict[str, asyncio.Lock] = {}

    # time
    def now(self) -> datetime:
        return self.settings.now()

    # locks: `lock` guards short state mutations; `turn_lock` serialises copilot turns (a model call can take a minute,
    # and must not block a teller's decision).
    def lock(self, case_id: str) -> asyncio.Lock:
        return self._locks.setdefault(case_id, asyncio.Lock())

    def turn_lock(self, case_id: str) -> asyncio.Lock:
        return self._turn_locks.setdefault(case_id, asyncio.Lock())

    # cases
    def next_case_id(self) -> str:
        n = len(self.repo.list_cases()) + 1
        return f"case-{self.now():%Y-%m%d}-{n:04d}"

    def find_by_transfer(self, transfer_id: str) -> dict | None:
        found = self.repo.store.list("cases", where={"transfer_id": transfer_id}, limit=1)
        return found[0] if found else None

    def open_cases_for(self, customer_ref: str) -> list[dict]:
        return [c for c in self.repo.store.list("cases", where={"customer_ref": customer_ref}) if c["status"] in OPEN_STATUSES]

    def case(self, case_id: str) -> dict:
        doc = self.repo.get_case(case_id)
        if doc is None:
            raise not_found("case", case_id)
        return doc

    def save_case(self, case: dict) -> None:
        self.repo.put_case(case)

    def state(self, case_id: str) -> dict:
        doc = self.repo.store.get("case_state", case_id)
        if doc is None:
            raise not_found("case", case_id)
        return doc

    def save_state(self, case_id: str, state: dict) -> None:
        self.repo.store.set("case_state", case_id, state)

    def card(self, case_id: str) -> dict | None:
        return self.repo.get_card(case_id)

    def save_card(self, card: dict) -> None:
        self.repo.put_card(card)

    # events and audit
    def emit(self, case_id: str, type_: str, data: dict[str, Any] | None = None) -> dict:
        event = self.repo.append_event(case_id, {"type": type_, "at": self.now().isoformat(), "data": data or {}})
        self.hub.publish(event)
        return event

    def audit(self, case_id: str, action: str, actor: str, why: str | None, **extra: Any) -> dict:
        """Who did what and why. `actor` is the person named in the request; `via` is the header user."""
        return self.repo.append_audit({"case_id": case_id, "action": action, "actor": actor, "why": why,
                                       "at": self.now().isoformat(), **extra})

    # teller notes (case-db)
    def notes_for(self, customer_ref: str) -> list[dict]:
        return self.repo.store.list("teller_notes", where={"customer_ref": customer_ref}, order_by="at")
