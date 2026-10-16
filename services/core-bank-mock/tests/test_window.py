"""Hold window: the test vectors in docs/architecture/api-contracts.md ("Hold window")."""

from datetime import datetime, timedelta

import pytest

from conftest import TANAKA_TRANSFER, WINDOW, place_hold
from core_bank_mock.window import BusinessCalendar, compute_window
from mimamori_common.models import HoldWindow
from mimamori_common.seed import business_calendar

CAL = BusinessCalendar.from_seed(business_calendar(), "15:00")
EXTEND = HoldWindow(**WINDOW)
NO_EXTEND = HoldWindow(minimum_hours=4, extend_to_next_business_day_close=False, cap_hours=24)

# (placed, window, expected ends_at). Tue 2026-10-13, Fri 2026-10-16 (the Monday 10-12 before is a holiday).
VECTORS = [
    ("Tue 09:30", "2026-10-13T09:30:00+09:00", EXTEND, "2026-10-13T15:00:00+09:00"),
    ("Tue 11:50", "2026-10-13T11:50:00+09:00", EXTEND, "2026-10-14T11:50:00+09:00"),  # cap
    ("Tue 14:30", "2026-10-13T14:30:00+09:00", EXTEND, "2026-10-14T14:30:00+09:00"),  # cap
    ("Fri 14:30", "2026-10-16T14:30:00+09:00", EXTEND, "2026-10-17T14:30:00+09:00"),  # cap; next close is Monday
    ("Tue 14:30 no extend", "2026-10-13T14:30:00+09:00", NO_EXTEND, "2026-10-13T18:30:00+09:00"),
]


@pytest.mark.parametrize("label,placed,window,expected", VECTORS, ids=[v[0] for v in VECTORS])
def test_vectors_pure(label, placed, window, expected):
    w = compute_window(datetime.fromisoformat(placed), window, CAL)
    assert w.ends_at == datetime.fromisoformat(expected)


@pytest.mark.parametrize("label,placed,window,expected", VECTORS, ids=[v[0] for v in VECTORS])
def test_vectors_through_api(client, scoring, clock, label, placed, window, expected):
    scoring.mode = "alert"
    transfer_id = client.post("/transfers", json=TANAKA_TRANSFER).json()["transfer_id"]
    clock.set(placed)
    r = place_hold(client, transfer_id, window=window.model_dump())
    assert r.status_code == 200, r.text
    hold = r.json()
    assert datetime.fromisoformat(hold["ends_at"]) == datetime.fromisoformat(expected)
    assert datetime.fromisoformat(hold["cap_ends_at"]) == datetime.fromisoformat(placed) + timedelta(hours=24)
    assert hold["status"] == "active"


def test_minimum_wins_over_early_close_when_cap_allows():
    # minimum 4h from Tue 09:30 is 13:30; the close at 15:00 is later and inside the 24h cap.
    w = compute_window(datetime.fromisoformat("2026-10-13T09:30:00+09:00"), EXTEND, CAL)
    assert w.minimum_ends_at == datetime.fromisoformat("2026-10-13T13:30:00+09:00")
    assert w.ends_at == datetime.fromisoformat("2026-10-13T15:00:00+09:00")


def test_close_exactly_at_minimum_end_counts():
    # minimum ends exactly at 15:00 -> that close is "at or after".
    w = compute_window(datetime.fromisoformat("2026-10-13T11:00:00+09:00"), EXTEND, CAL)
    assert w.ends_at == datetime.fromisoformat("2026-10-13T15:00:00+09:00")


def test_calendar_skips_holidays_and_weekends():
    # Sun 10-11 then Mon 10-12 (holiday) -> next close is Tue 10-13 15:00.
    nxt = CAL.next_close_at_or_after(datetime.fromisoformat("2026-10-11T09:00:00+09:00"))
    assert nxt == datetime.fromisoformat("2026-10-13T15:00:00+09:00")


def test_close_time_is_config():
    cal = BusinessCalendar.from_seed(business_calendar(), "17:30")
    w = compute_window(datetime.fromisoformat("2026-10-13T09:30:00+09:00"), EXTEND, cal)
    assert w.ends_at == datetime.fromisoformat("2026-10-13T17:30:00+09:00")


def test_cap_can_be_shorter_than_minimum_extension_only():
    # cap == minimum: the hold is exactly the minimum.
    w = compute_window(
        datetime.fromisoformat("2026-10-13T11:50:00+09:00"),
        HoldWindow(minimum_hours=4, extend_to_next_business_day_close=True, cap_hours=4), CAL,
    )
    assert w.ends_at == datetime.fromisoformat("2026-10-13T15:50:00+09:00")
