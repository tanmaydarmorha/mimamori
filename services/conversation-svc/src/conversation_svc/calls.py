"""In-memory call state. The service keeps only what POST /calls sent plus the call's own progress;
it never holds anything else about the case, and no utterance text."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal

from mimamori_common.models import CallRequest, Notice

from .verify import codes_match, numbers_match

CallState = Literal["notice_sent", "in_progress", "ended", "locked"]


@dataclass
class CallRecord:
    request: CallRequest
    notice: Notice
    state: CallState = "notice_sent"
    failed_attempts: int = 0
    turns: int = 0
    signals: dict = field(default_factory=dict)
    disclosed: list[str] = field(default_factory=list)
    intents: list[str] = field(default_factory=list)  # for audit, never the caller's words
    outcome_sent: bool = False
    started_at: datetime | None = None

    @property
    def call_id(self) -> str:
        return self.request.brief.call_id


class CallStore:
    def __init__(self) -> None:
        self._calls: dict[str, CallRecord] = {}

    def get(self, call_id: str) -> CallRecord | None:
        return self._calls.get(call_id)

    def add(self, record: CallRecord) -> None:
        self._calls[record.call_id] = record

    def notices_for(self, e164: str) -> list[Notice]:
        return [c.notice for c in self._calls.values() if numbers_match(e164, c.request.brief.contact.locked_phone_e164)]

    def find_for_callback(self, caller_number: str, case_code: str) -> CallRecord | None:
        """The call a callback is about. The caller can't name a call, so match on either secret:
        prefer a call matching both, then the most recent open call matching one. Used only to know
        where to report a failed check; matching one is never enough to verify."""
        open_calls = [c for c in self._calls.values() if c.state in ("notice_sent", "locked")]
        both = [c for c in open_calls if numbers_match(caller_number, c.request.brief.contact.locked_phone_e164)
                and codes_match(case_code, c.request.brief.case_code)]
        either = [c for c in open_calls if numbers_match(caller_number, c.request.brief.contact.locked_phone_e164)
                  or codes_match(case_code, c.request.brief.case_code)]
        pool = both or either or (open_calls if len(open_calls) == 1 else [])  # a lone open call is the only one it can be about
        return max(pool, key=lambda c: c.notice.sent_at) if pool else None
