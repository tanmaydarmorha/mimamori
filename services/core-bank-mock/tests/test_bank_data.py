"""Read-only bank data, the payers query ("six others"), and freezes."""

from datetime import datetime

from conftest import TANAKA_TRANSFER, place_hold


def test_payers_of_the_mule_are_the_six_prior_payers(client, mani):
    r = client.get("/accounts/acct-mule-0001/payers", params={"days": 7})
    assert r.status_code == 200
    body = r.json()
    assert body["distinct_payers"] == 6 and len(body["payers"]) == 6
    expected = {p["customer_ref"]: p for p in mani["mule"]["prior_payers"]}
    assert {p["customer_ref"] for p in body["payers"]} == set(expected)
    for p in body["payers"]:
        e = expected[p["customer_ref"]]
        assert p["account_id"] == e["account_id"] and p["total_jpy"] == e["amount_jpy"] and p["payments"] == 1
        assert p["display_name_ja"]
    assert "cust-tanaka-0001" not in {p["customer_ref"] for p in body["payers"]}


def test_payers_default_days_is_seven_and_window_applies(client):
    assert client.get("/accounts/acct-mule-0001/payers").json()["distinct_payers"] == 6
    # Demo now is 10-13 11:42; the three payers of 10-09 are outside a one-day window, the 10-13 payer is inside.
    one_day = {p["customer_ref"] for p in client.get("/accounts/acct-mule-0001/payers", params={"days": 1}).json()["payers"]}
    assert "cust-0052" in one_day and not one_day & {"cust-0002", "cust-0011", "cust-0023"}
    assert client.get("/accounts/acct-mule-0001/payers", params={"days": 0}).status_code == 422
    assert client.get("/accounts/acct-nope/payers").status_code == 404


def test_pending_and_held_transfers_are_not_payers_but_a_released_one_is(client, scoring):
    scoring.mode = "alert"
    tid = client.post("/transfers", json=TANAKA_TRANSFER).json()["transfer_id"]
    assert client.get("/accounts/acct-mule-0001/payers").json()["distinct_payers"] == 6
    hold = place_hold(client, tid).json()
    assert client.get("/accounts/acct-mule-0001/payers").json()["distinct_payers"] == 6
    client.patch(f"/holds/{hold['hold_id']}", json={"action": "override_after_contact_reached", "reason": "r",
                                                    "actor": "t", "contact_reached": True})
    payers = client.get("/accounts/acct-mule-0001/payers").json()
    assert payers["distinct_payers"] == 7
    assert "cust-tanaka-0001" in {p["customer_ref"] for p in payers["payers"]}


def test_freeze_marks_the_account_frozen(client):
    assert client.get("/accounts/acct-mule-0001").json()["status"] == "active"
    r = client.post("/freezes", json={"account_id": "acct-mule-0001", "case_id": "case-2026-1013-0001",
                                      "approved_by": "analyst-01", "rationale": "seven payers in a week, account 4 days old"})
    assert r.status_code == 200, r.text
    f = r.json()
    assert f["status"] == "frozen" and f["account_id"] == "acct-mule-0001" and f["approved_by"] == "analyst-01"
    assert f["freeze_id"].startswith("frz-")
    assert client.get("/accounts/acct-mule-0001").json()["status"] == "frozen"
    assert [a["status"] for a in client.get("/accounts", params={"customer_ref": "cust-mule-0001"}).json()] == ["frozen"]
    # Idempotent retry returns the same freeze; others stay untouched.
    again = client.post("/freezes", json={"account_id": "acct-mule-0001", "case_id": "c", "approved_by": "a", "rationale": "r"})
    assert again.json()["freeze_id"] == f["freeze_id"]
    assert client.get("/accounts/acct-tanaka-0001").json()["status"] == "active"
    assert client.post("/freezes", json={"account_id": "acct-nope", "case_id": "c", "approved_by": "a", "rationale": "r"}).status_code == 404


def test_customers_and_accounts(client, mani):
    customers = client.get("/customers").json()
    assert len(customers) == mani["counts"]["customers"]
    t = client.get("/customers/cust-tanaka-0001").json()
    assert t["display_name_ja"] == "田中 圭子" and t["tenure_years"] == 12
    assert client.get("/customers/nope").status_code == 404
    accts = client.get("/accounts", params={"customer_ref": "cust-tanaka-0001"}).json()
    assert [a["account_id"] for a in accts] == ["acct-tanaka-0001"]
    assert client.get("/accounts/acct-tanaka-0001").json()["balance_jpy"] == 7_420_000


def test_transactions_filters_limit_and_order(client):
    allt = client.get("/accounts/acct-tanaka-0001/transactions").json()
    assert len(allt) > 100
    times = [t["booked_at"] for t in allt]
    assert times == sorted(times, key=datetime.fromisoformat)

    april = client.get("/accounts/acct-tanaka-0001/transactions",
                       params={"since": "2026-04-01T00:00:00+09:00", "until": "2026-04-30T23:59:59+09:00"}).json()
    assert any(t["amount_jpy"] == 400_000 for t in april)
    assert all("2026-04" in t["booked_at"] for t in april)

    last3 = client.get("/accounts/acct-tanaka-0001/transactions", params={"limit": 3}).json()
    assert last3 == allt[-3:]
    desc = client.get("/accounts/acct-tanaka-0001/transactions", params={"limit": 3, "order": "desc"}).json()
    assert desc == list(reversed(allt[-3:]))
    assert client.get("/accounts/nope/transactions").status_code == 404


def test_no_contractor_payments_in_tanaka_history(client):
    cats = {t["counterparty_category"] for t in client.get("/accounts/acct-tanaka-0001/transactions").json()}
    assert "contractor" not in cats


def test_healthz(client):
    assert client.get("/healthz").json() == {"status": "ok", "service": "core-bank-mock", "version": "0.1.0"}
