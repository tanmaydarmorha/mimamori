"""Holds: placement, the override rules, release executing the transfer."""

import pytest

from conftest import TANAKA_TRANSFER, WINDOW, place_hold


@pytest.fixture
def pending(client, scoring):
    scoring.mode = "alert"
    return client.post("/transfers", json=TANAKA_TRANSFER).json()["transfer_id"]


@pytest.fixture
def held(client, pending):
    return place_hold(client, pending).json()


def patch(client, hold_id, **kw):
    return client.patch(f"/holds/{hold_id}", json={"reason": "r", "actor": "teller-01", **kw})


def test_hold_places_and_marks_transfer_held(client, pending):
    r = place_hold(client, pending)
    assert r.status_code == 200, r.text
    hold = r.json()
    assert hold["status"] == "active" and hold["transfer_id"] == pending
    assert hold["overrides"] == ["after_contact_reached", "after_manager_review_and_second_confirmation"]
    t = client.get(f"/transfers/{pending}").json()
    assert t["status"] == "held" and t["hold_id"] == hold["hold_id"] and t["hold"]["hold_id"] == hold["hold_id"]
    assert client.get(f"/holds/{hold['hold_id']}").json() == hold


def test_cannot_hold_twice_or_hold_a_missing_or_executed_transfer(client, pending):
    assert place_hold(client, pending).status_code == 200
    assert place_hold(client, pending).status_code == 409
    assert place_hold(client, "tr-9999").status_code == 404
    client.post("/transfers", json={**TANAKA_TRANSFER, "channel": "atm", "amount_jpy": 10_000})
    assert place_hold(client, "tr-0002").status_code == 409


def test_hold_account_must_match_transfer(client, pending):
    r = client.post("/holds", json={"account_id": "acct-0002", "transfer_id": pending, "case_id": "c", "placed_by": "t",
                                    "window": WINDOW, "overrides": []})
    assert r.status_code == 422


def test_keep_changes_nothing(client, held):
    r = patch(client, held["hold_id"], action="keep")
    assert r.status_code == 200 and r.json()["status"] == "active"


def test_contact_override_needs_contact_reached(client, held, pending, clock):
    r = patch(client, held["hold_id"], action="override_after_contact_reached", contact_reached=False)
    assert r.status_code == 409 and r.json()["error"] == "override_conditions_not_met"
    assert client.get(f"/transfers/{pending}").json()["status"] == "held"

    r = patch(client, held["hold_id"], action="override_after_contact_reached", contact_reached=True)
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "released" and r.json()["released_at"]
    assert client.get(f"/transfers/{pending}").json()["status"] == "released"


@pytest.mark.parametrize("kw", [
    {},
    {"manager_id": "mgr-01"},
    {"second_confirmed_by": "teller-02"},
    {"manager_id": "mgr-01", "second_confirmed_by": "mgr-01"},  # not a different person
    {"manager_id": "mgr-01", "second_confirmed_by": "teller-01"},  # the person who placed the hold
])
def test_manager_override_conditions(client, held, kw):
    r = patch(client, held["hold_id"], action="override_after_manager_review", **kw)
    assert r.status_code == 409
    assert client.get(f"/holds/{held['hold_id']}").json()["status"] == "active"


def test_manager_override_with_second_person_releases_and_executes(client, held, pending):
    before = len(client.get("/accounts/acct-mule-0001/transactions").json())
    r = patch(client, held["hold_id"], action="override_after_manager_review", manager_id="mgr-01", second_confirmed_by="teller-02")
    assert r.status_code == 200 and r.json()["status"] == "released"
    assert "override_after_manager_review" in r.json()["release_reason"]
    assert client.get(f"/transfers/{pending}").json()["status"] == "released"
    assert len(client.get("/accounts/acct-mule-0001/transactions").json()) == before + 1  # money moved


def test_override_must_be_allowed_by_the_hold(client, pending):
    hold = place_hold(client, pending, overrides=["after_contact_reached"]).json()
    r = patch(client, hold["hold_id"], action="override_after_manager_review", manager_id="m", second_confirmed_by="s")
    assert r.status_code == 409 and r.json()["error"] == "override_not_allowed"

    hold2_t = client.post("/transfers", json=TANAKA_TRANSFER).json()["transfer_id"]
    hold2 = place_hold(client, hold2_t, overrides=[]).json()
    r = patch(client, hold2["hold_id"], action="override_after_contact_reached", contact_reached=True)
    assert r.status_code == 409 and r.json()["error"] == "override_not_allowed"


def test_plain_release_only_after_the_window(client, held, pending, clock):
    r = patch(client, held["hold_id"], action="release")
    assert r.status_code == 409 and r.json()["error"] == "hold_active"
    clock.advance(hours=25)
    assert client.get(f"/holds/{held['hold_id']}").json()["status"] == "expired"
    r = patch(client, held["hold_id"], action="release")
    assert r.status_code == 200 and r.json()["status"] == "released"
    assert client.get(f"/transfers/{pending}").json()["status"] == "released"


def test_hold_without_overrides_can_be_plainly_released_early(client, pending):
    hold = place_hold(client, pending, overrides=[]).json()
    r = patch(client, hold["hold_id"], action="release")
    assert r.status_code == 200 and r.json()["status"] == "released"
    assert client.get(f"/transfers/{pending}").json()["status"] == "released"


def test_released_hold_cannot_be_patched_again(client, held):
    patch(client, held["hold_id"], action="override_after_contact_reached", contact_reached=True)
    assert patch(client, held["hold_id"], action="keep").status_code == 409
    assert patch(client, held["hold_id"], action="override_after_contact_reached", contact_reached=True).status_code == 409


def test_cancel_releases_the_hold_without_moving_money(client, held, pending):
    r = client.patch(f"/transfers/{pending}", json={"action": "cancel", "actor": "teller-01", "reason": "customer withdrew"})
    assert r.json()["status"] == "cancelled"
    assert client.get(f"/holds/{held['hold_id']}").json()["status"] == "released"
    assert client.patch(f"/transfers/{pending}", json={"action": "execute", "actor": "t", "reason": "x"}).status_code == 409


def test_release_blocked_if_payee_frozen_meanwhile(client, held, pending):
    client.post("/freezes", json={"account_id": "acct-mule-0001", "case_id": "c", "approved_by": "analyst-01", "rationale": "mule"})
    r = patch(client, held["hold_id"], action="override_after_contact_reached", contact_reached=True)
    assert r.status_code == 409 and r.json()["error"] == "account_frozen"
    assert client.get(f"/holds/{held['hold_id']}").json()["status"] == "active"
    assert client.get(f"/transfers/{pending}").json()["status"] == "held"


def test_unknown_hold_is_404(client):
    assert client.get("/holds/hold-9999").status_code == 404
    assert patch(client, "hold-9999", action="keep").status_code == 404
