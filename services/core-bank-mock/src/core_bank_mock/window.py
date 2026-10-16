"""Hold window computation (docs/architecture/api-contracts.md, "Hold window").

    minimum_ends_at = placed + minimum_hours
    ends_at = minimum_ends_at
    if extend: ends_at = max(minimum_ends_at, first business-day close at or after minimum_ends_at)
    cap_ends_at = placed + cap_hours
    ends_at = min(ends_at, cap_ends_at)

Business closes at `close` (local, JST) on days that are not Saturday/Sunday and not in the
business calendar's `closed_dates`.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta

from mimamori_common.config import JST
from mimamori_common.models import HoldWindow


@dataclass(frozen=True)
class BusinessCalendar:
    closed_dates: frozenset[date]
    close: time = time(15, 0)

    @classmethod
    def from_seed(cls, calendar: dict, close: str = "15:00") -> "BusinessCalendar":
        hh, mm = close.split(":")[:2]
        closed = frozenset(date.fromisoformat(d) for d in calendar.get("closed_dates", []))
        return cls(closed_dates=closed, close=time(int(hh), int(mm)))

    def is_business_day(self, d: date) -> bool:
        return d.weekday() < 5 and d not in self.closed_dates

    def next_close_at_or_after(self, moment: datetime) -> datetime:
        """First business-day close (in JST) that is >= `moment`."""
        moment = moment.astimezone(JST)
        day = moment.date()
        for _ in range(400):  # far more than any closure run
            if self.is_business_day(day):
                candidate = datetime.combine(day, self.close, tzinfo=JST)
                if candidate >= moment:
                    return candidate
            day += timedelta(days=1)
        raise RuntimeError("no business day found within 400 days")  # pragma: no cover


@dataclass(frozen=True)
class ComputedWindow:
    minimum_ends_at: datetime
    ends_at: datetime
    cap_ends_at: datetime


def compute_window(placed: datetime, window: HoldWindow, calendar: BusinessCalendar) -> ComputedWindow:
    placed = placed.astimezone(JST)
    minimum_ends_at = placed + timedelta(hours=window.minimum_hours)
    ends_at = minimum_ends_at
    if window.extend_to_next_business_day_close:
        ends_at = max(minimum_ends_at, calendar.next_close_at_or_after(minimum_ends_at))
    cap_ends_at = placed + timedelta(hours=window.cap_hours)
    return ComputedWindow(minimum_ends_at=minimum_ends_at, ends_at=min(ends_at, cap_ends_at), cap_ends_at=cap_ends_at)
