"""POST /transfers: Scoring on counter / large transfers, fail open, post-transaction events."""

import pytest

from conftest import TANAKA_TRANSFER


def txn_count(client, account_id):
    return len(client.get(f"/accounts/{account_id}/transactions").json())


def test_tanaka_transfer_reaches_scoring_and_stays_pending_on_alert(client, scoring):
    scoring.mode = "alert"
    before_out = txn_count(client, "acct-tanaka-0001")
    before_in = txn_count(client, "acct-mule-0001")

    r = client.post("/transfers", json=TANAKA_TRANSFER)

    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "pending_alert"
    assert body["scoring"] == "alert"
    assert body["case_id"] == "case-2026-1013-0001"
    # Scoring saw the request, with the system role header and the transfer id we returned.
    assert scoring.paths() == ["/v1/score"]
    sent = scoring.requests[0][1]
    assert sent["transfer_id"] == body["transfer_id"]
    assert sent["customer_ref"] == "cust-tanaka-0001"
    assert sent["amount_jpy"] == 3_000_000
    assert sent["channel"] == "counter"
    assert sent["payee"]["account_id"] == "acct-mule-0001"
    assert sent["occurred_at"].startswith("2026-10-13T11:42:00")
    # The money did not move.
    assert txn_count(client, "acct-tanaka-0001") == before_out
    assert txn_count(client, "acct-mule-0001") == before_in
    got = client.get(f"/transfers/{body['transfer_id']}").json()
    assert got["status"] == "pending_alert" and got["case_id"] == body["case_id"]


def test_allow_executes_the_transfer(client, scoring):
    scoring.mode = "allow"
    before = txn_count(client, "acct-tanaka-0001")
    body = client.post("/transfers", json=TANAKA_TRANSFER).json()
    assert body["status"] == "executed" and body["scoring"] == "allow" and body["case_id"] is None
    assert txn_count(client, "acct-tanaka-0001") == before + 1
    out = client.get("/accounts/acct-tanaka-0001/transactions", params={"limit": 1}).json()[0]
    assert out["kind"] == "transfer_out" and out["amount_jpy"] == 3_000_000
    assert out["counterparty_account_id"] == "acct-mule-0001"


@pytest.mark.parametrize("mode", ["timeout", "connect_error", "error", "garbage", "slow"])
def test_scoring_outage_fails_open(client, scoring, settings, mode, bank_data):
    """DA 7: a Scoring timeout, outage or garbage never blocks a transfer."""
    if mode == "slow":  # a real deadline, not just a raised exception
        from dataclasses import replace

        import httpx
        from fastapi.testclient import TestClient

        from core_bank_mock.app import create_core_bank_app

        app = create_core_bank_app(
            replace(settings, scoring_timeout_s=0.1), data=bank_data, scoring_transport=httpx.MockTransport(scoring.handle),
        )
        with TestClient(app) as c:
            scoring.mode = mode
            body = c.post("/transfers", json=TANAKA_TRANSFER).json()
    else:
        scoring.mode = mode
        body = client.post("/transfers", json=TANAKA_TRANSFER).json()
    assert body["status"] == "executed"
    assert body["scoring"] == "unavailable"
    assert body["case_id"] is None


def test_outage_transfer_is_booked(client, scoring):
    scoring.mode = "connect_error"
    before = txn_count(client, "acct-mule-0001")
    client.post("/transfers", json=TANAKA_TRANSFER)
    assert txn_count(client, "acct-mule-0001") == before + 1


def test_small_atm_transfer_skips_pre_check_then_posts_event(client, scoring):
    scoring.mode = "alert"  # would alert if it were asked
    req = {**TANAKA_TRANSFER, "channel": "atm", "amount_jpy": 50_000}
    body = client.post("/transfers", json=req).json()
    assert body["status"] == "executed" and body["scoring"] == "not_checked"
    assert scoring.paths() == ["/v1/events"]
    assert scoring.requests[0][1]["transfer_id"] == body["transfer_id"]


def test_large_app_transfer_is_pre_checked(client, scoring):
    scoring.mode = "alert"
    body = client.post("/transfers", json={**TANAKA_TRANSFER, "channel": "app"}).json()
    assert body["status"] == "pending_alert" and body["scoring"] == "alert"
    assert scoring.paths() == ["/v1/score"]


def test_threshold_is_configurable_and_inclusive(scoring, bank_data):
    from dataclasses import replace

    import httpx
    from fastapi.testclient import TestClient

    from core_bank_mock.app import create_core_bank_app
    from mimamori_common.config import Settings

    app = create_core_bank_app(
        replace(Settings(), large_transfer_threshold_jpy=50_000), data=bank_data,
        scoring_transport=httpx.MockTransport(scoring.handle),
    )
    with TestClient(app) as c:
        c.post("/transfers", json={**TANAKA_TRANSFER, "channel": "atm", "amount_jpy": 50_000})
        c.post("/transfers", json={**TANAKA_TRANSFER, "channel": "atm", "amount_jpy": 49_999})
    assert scoring.paths() == ["/v1/score", "/v1/events"]


def test_event_failure_does_not_fail_the_transfer(client, scoring):
    scoring.mode = "error"
    body = client.post("/transfers", json={**TANAKA_TRANSFER, "channel": "atm", "amount_jpy": 50_000}).json()
    assert body["status"] == "executed" and body["scoring"] == "not_checked"


def test_cash_withdrawal_books_one_transaction(client, scoring):
    req = {"customer_ref": "cust-tanaka-0001", "account_id": "acct-tanaka-0001", "channel": "counter",
           "kind": "cash_withdrawal", "amount_jpy": 400_000}
    before = txn_count(client, "acct-tanaka-0001")
    body = client.post("/transfers", json=req).json()
    assert body["status"] == "executed" and body["scoring"] == "allow"
    last = client.get("/accounts/acct-tanaka-0001/transactions", params={"limit": 1}).json()[0]
    assert last["kind"] == "withdrawal" and last["amount_jpy"] == 400_000
    assert txn_count(client, "acct-tanaka-0001") == before + 1


def test_bad_requests_use_api_error(client):
    r = client.post("/transfers", json={**TANAKA_TRANSFER, "customer_ref": "cust-0002"})
    assert r.status_code == 422 and r.json()["error"] == "account_customer_mismatch"
    r = client.post("/transfers", json={**TANAKA_TRANSFER, "account_id": "acct-nope"})
    assert r.status_code == 404 and r.json()["error"] == "not_found"
    r = client.post("/transfers", json={**TANAKA_TRANSFER, "amount_jpy": 0})
    assert r.status_code == 422 and r.json()["error"] == "validation_error"
    r = client.post("/transfers", json={**TANAKA_TRANSFER, "payee": None})
    assert r.status_code == 422 and r.json()["error"] == "payee_required"
    assert client.get("/transfers/tr-9999").status_code == 404


def test_patch_transfer_execute_and_cancel(client, scoring):
    scoring.mode = "alert"
    t1 = client.post("/transfers", json=TANAKA_TRANSFER).json()["transfer_id"]
    r = client.patch(f"/transfers/{t1}", json={"action": "execute", "actor": "teller-01", "reason": "cleared"})
    assert r.status_code == 200 and r.json()["status"] == "executed"
    # Cannot execute or cancel twice.
    assert client.patch(f"/transfers/{t1}", json={"action": "execute", "actor": "t", "reason": "x"}).status_code == 409
    assert client.patch(f"/transfers/{t1}", json={"action": "cancel", "actor": "t", "reason": "x"}).status_code == 409

    t2 = client.post("/transfers", json=TANAKA_TRANSFER).json()["transfer_id"]
    r = client.patch(f"/transfers/{t2}", json={"action": "cancel", "actor": "teller-01", "reason": "customer withdrew"})
    assert r.json()["status"] == "cancelled"


def test_frozen_accounts_refuse_transfers(client, scoring):
    client.post("/freezes", json={"account_id": "acct-mule-0001", "case_id": "case-x", "approved_by": "analyst-01", "rationale": "mule"})
    r = client.post("/transfers", json=TANAKA_TRANSFER)
    assert r.status_code == 409 and r.json()["error"] == "account_frozen"
    assert scoring.requests == []
