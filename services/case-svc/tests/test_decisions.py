"""Build step 2: human decisions, holds, the police summary, and the audit trail."""

import pytest
from conftest import ANALYST, REPLAY, STAFF, replay

PAUSE = {"action": "pause", "basis": "advance_wishes", "rationale": "Police impersonation and secrecy at c4", "teller_id": "teller-sato"}


def decide(env, case_id, body, headers=STAFF):
    return env.client.post(f"/cases/{case_id}/decision", json=body, headers=headers)


def test_pause_with_wishes_places_hold_with_wishes_window_and_audits_who_and_why(make_env):
    env, case_id, _ = replay(make_env, "A")
    resp = decide(env, case_id, PAUSE)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["status"] == "paused" and body["warnings"] == []
    hold = env.bank.holds[body["hold"]["hold_id"]]
    assert hold.placed_by == "teller-sato" and hold.case_id == case_id and hold.account_id == "acct-tanaka-0001"
    assert hold.overrides == ["after_contact_reached", "after_manager_review_and_second_confirmation"]  # from her wishes
    assert (hold.ends_at - hold.placed_at).total_seconds() == 4 * 3600  # the fake bank's simplified window: minimum_hours
    audit = [a for a in env.client.get(f"/cases/{case_id}/audit").json() if a["action"] == "decision.pause"]
    assert len(audit) == 1
    a = audit[0]
    assert a["actor"] == "teller-sato" and a["why"] == PAUSE["rationale"] and a["via"] == "teller-sato"
    assert a["basis"] == "advance_wishes" and a["hold_id"] == hold.hold_id
    assert a["pause_recommended_at_decision"] is True and a["risk_level_at_decision"] == "high"
    assert env.case(case_id)["decisions"][0]["decided_by"] == "teller-sato"


def test_single_source_pause_is_allowed_with_a_logged_warning(make_env, caplog):
    env = make_env(svc={"investigation_enabled": False})
    case_id = env.open_case(signals=[])  # no facts, no quotes: not even one source
    with caplog.at_level("WARNING"):
        resp = decide(env, case_id, {**PAUSE, "basis": "bank_policy", "rationale": "the teller is uneasy"})
    assert resp.status_code == 200  # never blocked (DA 11)
    assert resp.json()["warnings"] == ["single_source_pause"]
    assert any("single_source_pause" in r.message for r in caplog.records)
    audit = [a for a in env.client.get(f"/cases/{case_id}/audit").json() if a["action"] == "decision.pause"][0]
    assert audit["warnings"] == ["single_source_pause"]


def test_pause_with_two_sources_has_no_warning(make_env):
    env, case_id, _ = replay(make_env, "A", upto=4)
    assert decide(env, case_id, PAUSE).json()["warnings"] == []


def test_wishes_basis_needs_applicable_wishes_and_bank_policy_does_not(make_env):
    env = make_env()
    case_id = env.open_case(customer_ref="cust-0005", account_id="acct-0005", payee_account="acct-co-0001", amount=1_800_000)
    resp = decide(env, case_id, PAUSE)  # cust-0005 has no wishes on file
    assert resp.status_code == 409 and resp.json()["error"] == "wishes_not_applicable"
    resp = decide(env, case_id, {**PAUSE, "basis": "bank_policy"})
    assert resp.status_code == 200
    hold = env.bank.holds[resp.json()["hold"]["hold_id"]]
    assert hold.overrides == []  # a voluntary wait
    # no wishes, so no family call
    assert env.conv.calls == [] and env.case(case_id)["contact_suspected"] == "no_wishes_on_file"


def test_bank_policy_hold_can_be_released_with_a_plain_release(make_env):
    env = make_env()
    case_id = env.open_case(customer_ref="cust-0005", account_id="acct-0005", payee_account="acct-co-0001", amount=1_800_000)
    decide(env, case_id, {**PAUSE, "basis": "bank_policy"})
    resp = decide(env, case_id, {"action": "release", "release_reason": "cleared_by_teller", "rationale": "customer produced the contract",
                                 "teller_id": "teller-sato"})
    assert resp.status_code == 200 and resp.json()["status"] == "released"
    assert env.bank.transfers["tr-0001"].status == "released"


def test_wishes_hold_cannot_be_plain_released_early_only_overrides_end_it(make_env):
    env, case_id, _ = replay(make_env, "A")
    decide(env, case_id, PAUSE)
    release = {"action": "release", "release_reason": "cleared_by_teller", "rationale": "customer insists", "teller_id": "teller-sato"}
    resp = decide(env, case_id, release)
    assert resp.status_code == 409 and resp.json()["error"] == "hold_active"
    assert not any(c == ("PATCH", f"/holds/hold-0001") for c in env.bank.calls)  # refused before asking the bank

    # override after contact reached: needs the verified callback outcome first
    contact = {"action": "release", "release_reason": "customer_override_after_contact_reached", "rationale": "daughter spoke to her",
               "teller_id": "teller-sato"}
    assert decide(env, case_id, contact).json()["error"] == "contact_not_reached"

    # manager review: the second confirmer must differ from the manager and from whoever placed the hold
    mgr = {"action": "release", "release_reason": "manager_review_second_confirmation", "rationale": "manager reviewed",
           "teller_id": "teller-sato", "manager_id": "mgr-ono", "second_confirmed_by": "teller-sato"}
    assert decide(env, case_id, mgr).json()["error"] == "second_confirmation_invalid"
    mgr["second_confirmed_by"] = "mgr-kato"
    resp = decide(env, case_id, mgr)
    assert resp.status_code == 200 and resp.json()["status"] == "released"
    audit = [a for a in env.client.get(f"/cases/{case_id}/audit").json() if a["action"] == "decision.release"][0]
    assert audit["manager_id"] == "mgr-ono" and audit["second_confirmed_by"] == "mgr-kato" and audit["why"] == "manager reviewed"


def test_release_after_contact_reached_uses_the_verified_outcome(make_env):
    env, case_id, _ = replay(make_env, "A")
    decide(env, case_id, PAUSE)
    case = env.case(case_id)
    view = {"case_id": case_id, "call_id": case["call_id"], "nature": "information",
            "verification": {"caller_number_match": True, "case_code_match": True}, "reached": True, "concerned": True,
            "coming_to_branch": True, "eta_minutes": 30, "wants_callback_later": False, "disclosed": ["transaction_paused"],
            "recorded_at": "2026-10-13T12:04:30+09:00"}
    assert env.client.post(f"/cases/{case_id}/contact-outcome", json={"call_id": case["call_id"], "outcome": "contact_view", "contact_view": view}).status_code == 200
    resp = decide(env, case_id, {"action": "release", "release_reason": "customer_override_after_contact_reached",
                                 "rationale": "Yuki confirmed", "teller_id": "teller-sato"})
    assert resp.status_code == 200 and resp.json()["status"] == "released"


def test_release_without_hold_executes_the_transfer(make_env):
    env = make_env()
    case_id = env.open_case(customer_ref="cust-0005", account_id="acct-0005", payee_account="acct-co-0001", amount=1_800_000)
    resp = decide(env, case_id, {"action": "release", "release_reason": "cleared_by_teller", "rationale": "documents checked",
                                 "teller_id": "teller-sato"})
    assert resp.status_code == 200 and env.bank.transfers["tr-0001"].status == "executed"


def test_invalid_decision_bodies_are_rejected(make_env):
    env = make_env()
    case_id = env.open_case()
    assert decide(env, case_id, {"action": "pause", "rationale": "x", "teller_id": "t"}).status_code == 422
    assert decide(env, case_id, {"action": "release", "rationale": "x", "teller_id": "t"}).status_code == 422
    assert decide(env, "case-nope", PAUSE).status_code == 404


def test_dismissal_is_the_only_way_an_indicator_leaves_and_it_is_audited(make_env):
    env, case_id, cards = replay(make_env, "A", upto=4)
    assert cards[-1]["risk"]["pause_recommended"]
    secrecy = next(c for c in cards[-1]["claims"] if c["kind"] == "quote" and c["indicator"] == "secrecy_instruction")
    resp = env.client.post(f"/cases/{case_id}/claims/{secrecy['id']}/dismiss", json={"teller_id": "teller-sato", "reason": "she was joking"},
                           headers=STAFF)
    assert resp.status_code == 200
    card = resp.json()["card"]
    assert not any(c["id"] == secrecy["id"] for c in card["claims"])
    assert not any("secrecy" in f["condition"] for f in card["risk"]["fired"])  # H2 (impersonation + pressure + risky payee) still holds
    a = [x for x in env.client.get(f"/cases/{case_id}/audit").json() if x["action"] == "indicator.dismissed"][0]
    assert a["actor"] == "teller-sato" and a["why"] == "she was joking"
    # the model listing the same quote again on the next turn does not bring it back
    card = env.turn(case_id, REPLAY["A"]["customer_turns"][4])["card"]
    assert not any(c["kind"] == "quote" and c["source"]["text"] == secrecy["source"]["text"] for c in card["claims"])


def test_police_summary_includes_only_requested_sections_and_logs_the_officer(make_env):
    env, case_id, _ = replay(make_env, "A")
    body = {"officer_name": "巡査部長 山本 太郎", "officer_title": "警部補", "requested_items": ["amount", "customer_statements"], "teller_id": "teller-sato"}
    resp = env.client.post(f"/cases/{case_id}/police-summary", json=body, headers=STAFF)
    assert resp.status_code == 200, resp.text
    out = resp.json()
    assert set(out["items"]) == {"amount", "customer_statements"}
    assert out["items"]["amount"]["amount_jpy"] == 3_000_000
    assert all(i["text"] for i in out["items"]["customer_statements"])
    assert "【取引内容】" in out["text_ja"] and "【お客様の発言】" in out["text_ja"]
    assert "【振込先】" not in out["text_ja"] and "【経過】" not in out["text_ja"] and "カ）ミライケンセツ" not in out["text_ja"]
    assert "田中" not in out["text_ja"]
    audit = [a for a in env.client.get(f"/cases/{case_id}/audit").json() if a["action"] == "police_summary.issued"][0]
    assert audit["officer_name"] == "巡査部長 山本 太郎" and audit["officer_title"] == "警部補"
    assert audit["actor"] == "teller-sato" and audit["requested_items"] == ["amount", "customer_statements"]
    # a different request gets different sections, still only what was asked
    only_payee = env.client.post(f"/cases/{case_id}/police-summary", json={**body, "requested_items": ["payee"]}, headers=STAFF).json()
    assert set(only_payee["items"]) == {"payee"}


def test_police_summary_needs_officer_name_and_items(make_env):
    env = make_env()
    case_id = env.open_case()
    bad = {"officer_name": "", "officer_title": "警部補", "requested_items": ["amount"], "teller_id": "t"}
    assert env.client.post(f"/cases/{case_id}/police-summary", json=bad).status_code == 422
    assert env.client.post(f"/cases/{case_id}/police-summary", json={**bad, "officer_name": "x", "requested_items": []}).status_code == 422


def test_case_carries_the_filled_approved_hold_line_only_while_a_pause_is_recommended(make_env):
    env, case_id, _ = replay(make_env, "A", upto=3)
    assert env.case(case_id)["hold_line"] is None
    env.copilot.json  # noqa: B018 (queue already holds the remaining recordings)
    env.turn(case_id, REPLAY["A"]["customer_turns"][3])
    line = env.case(case_id)["hold_line"]
    assert line["id"] == "h.fake_police.real_police" and "警察" in line["ja"] and line["en"]
