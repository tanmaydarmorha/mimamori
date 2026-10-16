"""Build step 5 (analyst side) and the API surface: freeze flow, playbook approval, roles, SSE, WebSocket audio."""

import json

from conftest import ANALYST, REPLAY, STAFF, replay

from mimamori_common.llm import FakeClient
from mimamori_common.seed import manifest


def test_freeze_flow_requires_the_analyst_and_returns_the_six_other_payers(make_env):
    env = make_env()
    case_id = env.open_case()
    req = {"requested_by": "teller-sato", "reason": "account opened 4 days ago, 7 payers this week"}
    fr = env.client.post(f"/cases/{case_id}/freeze-request", json=req, headers=STAFF)
    assert fr.status_code == 200 and fr.json()["status"] == "pending" and fr.json()["account_id"] == "acct-mule-0001"
    assert env.client.post(f"/cases/{case_id}/freeze-request", json=req, headers=STAFF).status_code == 409  # one pending at a time
    assert env.client.get("/freeze-requests", headers=STAFF).status_code == 403
    pending = env.client.get("/freeze-requests?status=pending", headers=ANALYST).json()
    assert [p["freeze_id"] for p in pending] == [fr.json()["freeze_id"]]

    decision = {"decision": "approve", "analyst_id": "analyst-ito", "rationale": "Relief Act Art. 3(1): suspicion on the bank's own account"}
    assert env.client.post(f"/cases/{case_id}/freeze-decision", json=decision, headers=STAFF).status_code == 403
    assert env.bank.freezes == []  # a teller can't approve
    assert env.client.get(f"/cases/{case_id}/outreach").json() == []  # empty until a freeze is approved
    resp = env.client.post(f"/cases/{case_id}/freeze-decision", json=decision, headers=ANALYST)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["freeze"]["account_id"] == "acct-mule-0001" and body["freeze"]["approved_by"] == "analyst-ito"
    assert env.bank.accounts["acct-mule-0001"].status == "frozen"
    expected = {p["customer_ref"] for p in manifest()["mule"]["prior_payers"]}
    assert len(body["outreach"]) == 6 and {o["customer_ref"] for o in body["outreach"]} == expected
    assert "cust-tanaka-0001" not in expected | {o["customer_ref"] for o in body["outreach"]}
    assert env.client.get(f"/cases/{case_id}/outreach").json() == body["outreach"]
    evt = [e for e in env.deps.store.repo.list_events(case_id) if e["type"] == "outreach_ready"][0]
    assert len(evt["data"]["outreach"]) == 6
    audit = [a for a in env.client.get(f"/cases/{case_id}/audit").json() if a["action"] == "freeze.approved"][0]
    assert audit["actor"] == "analyst-ito" and "Relief Act" in audit["why"]
    assert env.client.post(f"/cases/{case_id}/freeze-decision", json=decision, headers=ANALYST).status_code == 409  # already decided


def test_rejected_freeze_does_not_touch_the_bank(make_env):
    env = make_env()
    case_id = env.open_case()
    env.client.post(f"/cases/{case_id}/freeze-request", json={"requested_by": "teller-sato", "reason": "r"}, headers=STAFF)
    resp = env.client.post(f"/cases/{case_id}/freeze-decision", json={"decision": "reject", "analyst_id": "analyst-ito", "rationale": "not enough"},
                           headers=ANALYST)
    assert resp.status_code == 200 and resp.json()["freeze_request"]["status"] == "rejected" and resp.json()["outreach"] == []
    assert env.bank.freezes == [] and env.bank.accounts["acct-mule-0001"].status == "active"


def test_playbook_approval_is_analyst_only_and_only_approved_reach_the_copilot(make_env):
    env = make_env(copilot=FakeClient(json=[REPLAY["A"]["outputs"][0]] * 3, repeat_last=True))
    pending = env.client.get("/playbooks?status=pending").json()
    assert len(pending) == 1
    pid = pending[0]["id"]
    case_id = env.open_case()
    env.turn(case_id, REPLAY["A"]["customer_turns"][0])
    assert pid not in env.copilot.calls[-1].user

    patch = {"status": "approved", "analyst_id": "analyst-ito", "note": "checked against the NPA bulletin"}
    assert env.client.patch(f"/playbooks/{pid}", json=patch, headers=STAFF).status_code == 403
    assert env.deps.intel.get_playbook(pid)["status"] == "pending"
    ok = env.client.patch(f"/playbooks/{pid}", json=patch, headers=ANALYST)
    assert ok.status_code == 200 and ok.json()["status"] == "approved" and ok.json()["approved_by"] == "analyst-ito"
    env.turn(case_id, REPLAY["A"]["customer_turns"][1])
    assert pid in env.copilot.calls[-1].user  # now it reaches the model

    assert env.client.patch(f"/playbooks/{pid}", json={"status": "retired", "analyst_id": "analyst-ito"}, headers=ANALYST).status_code == 200
    env.turn(case_id, REPLAY["A"]["customer_turns"][2])
    assert pid not in env.copilot.calls[-1].user
    assert env.client.patch(f"/playbooks/{pid}", json=patch, headers=ANALYST).status_code == 409  # retired stays retired
    a = env.deps.store.repo.list_audit("playbooks")
    assert [x["action"] for x in a] == ["playbook.approved", "playbook.retired"] and a[0]["actor"] == "analyst-ito"
    assert env.client.patch("/playbooks/pb.none.none", json=patch, headers=ANALYST).status_code == 404


def test_rejected_playbook_never_reaches_the_copilot(make_env):
    env = make_env(copilot=FakeClient(json=[REPLAY["A"]["outputs"][0]]))
    pid = env.client.get("/playbooks?status=pending").json()[0]["id"]
    assert env.client.patch(f"/playbooks/{pid}", json={"status": "rejected", "analyst_id": "analyst-ito"}, headers=ANALYST).status_code == 200
    case_id = env.open_case()
    env.turn(case_id, REPLAY["A"]["customer_turns"][0])
    assert pid not in env.copilot.calls[0].user


def test_sse_replays_events_in_order_with_ids_and_after(make_env):
    env, case_id, _ = replay(make_env, "A", upto=2)
    text = env.client.get(f"/cases/{case_id}/events?follow=false").text
    frames = [f for f in text.split("\n\n") if f.strip()]
    ids = [int(f.split("\n")[0].removeprefix("id: ")) for f in frames]
    assert ids == sorted(ids) and ids[0] == 1
    assert frames[0].split("\n")[1] == "event: case_opened"
    data = json.loads(frames[0].split("\n")[2].removeprefix("data: "))
    assert data["case_id"] == case_id and data["seq"] == 1
    types = [f.split("\n")[1].removeprefix("event: ") for f in frames]
    assert types.count("transcript_turn") == 2 and "card_updated" in types
    later = env.client.get(f"/cases/{case_id}/events?follow=false&after={ids[-2]}").text
    assert later.count("id: ") == 1
    assert env.client.get(f"/cases/{case_id}/events?follow=false", headers={"Last-Event-ID": str(ids[-1])}).text == ""
    assert env.client.get("/cases/case-nope/events").status_code == 404


def test_event_hub_fans_out_to_live_subscribers(make_env):
    env = make_env()
    case_id = env.open_case()
    q = env.deps.store.hub.subscribe(case_id)
    event = env.deps.store.emit(case_id, "wishes_frozen", {"x": 1})
    assert q.get_nowait() == event
    env.deps.store.hub.unsubscribe(case_id, q)


def test_websocket_audio_typed_mode_turns_text_frames_into_turns(make_env):
    env = make_env(copilot=FakeClient(json=[REPLAY["A"]["outputs"][0]]))
    case_id = env.open_case()
    with env.client.websocket_connect(f"/cases/{case_id}/audio") as ws:
        ws.send_bytes("teller:ご用途をお伺いしてもよろしいですか".encode())
        assert ws.receive_json() == {"type": "transcript", "turn_id": "t1", "speaker": "teller", "text": "ご用途をお伺いしてもよろしいですか", "is_final": True}
        ws.send_bytes(REPLAY["A"]["customer_turns"][0].encode())
        out = ws.receive_json()
        assert out["turn_id"] == "c1" and out["speaker"] == "customer" and out["is_final"] is True
    card = env.case(case_id)["card"]
    assert card["card_version"] >= 3 and any(c["kind"] == "quote" for c in card["claims"])  # cards arrive over SSE / GET, not the socket


def test_unknown_case_and_bad_bodies(make_env):
    env = make_env()
    assert env.client.get("/cases/case-nope").json()["error"] == "not_found"
    assert env.client.post("/cases", json={"transfer_id": "x"}).json()["error"] == "validation_error"
    assert env.client.get("/healthz").json()["service"] == "case-svc"
    assert env.client.get("/cases", params={"status": "paused"}).json() == []
    env.open_case()
    assert [c["status"] for c in env.client.get("/cases").json()] == ["open"]


def test_data_boundary_conversation_svc_cannot_open_case_db():
    import pytest
    from mimamori_common.config import Settings
    from mimamori_common.store import open_case_repo

    with pytest.raises(PermissionError):
        open_case_repo(Settings(service_name="conversation-svc"))
