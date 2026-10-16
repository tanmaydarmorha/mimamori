"""Build step 4: the family-call side. Contact-suspected checks, the brief built in code, the case code,
POST /calls (stubbed), the outcome, and wishes frozen during an open case (DA 12)."""

import json
import re

import pytest
from conftest import ANALYST, REPLAY, STAFF, replay
from jsonschema import Draft202012Validator
from referencing import Registry, Resource

from mimamori_common.models import ContactBrief
from mimamori_common.schemas import load_example, load_schema

PAUSE = {"action": "pause", "basis": "advance_wishes", "rationale": "Police impersonation and secrecy", "teller_id": "teller-sato"}


def brief_validator() -> Draft202012Validator:
    registry = Registry().with_resources((n, Resource.from_contents(load_schema(n))) for n in ("advance-wishes.json", "contact-brief.json"))
    return Draft202012Validator(load_schema("contact-brief.json"), registry=registry)


def paused_case(make_env, **kw):
    env, case_id, _ = replay(make_env, "A", upto=4, **kw)
    resp = env.client.post(f"/cases/{case_id}/decision", json=PAUSE, headers=STAFF)
    assert resp.status_code == 200, resp.text
    return env, case_id


def test_pause_triggers_the_call_with_a_brief_that_validates_and_leaks_nothing(make_env):
    env, case_id = paused_case(make_env)
    assert len(env.conv.calls) == 1
    raw = env.conv.raw[0]
    brief_validator().validate(raw["brief"])
    ContactBrief.model_validate(raw["brief"])
    b = raw["brief"]
    assert b["built_by"] == "code" and b["case_code"] == "4821" and b["call_id"] == f"call-{case_id[-4:]}-1"
    assert b["contact"] == {"contact_id": "tc-yuki", "relationship": "child", "locked_phone_e164": "+819012345678"}
    # exactly what her wishes allow: no amount_band (not in may_disclose), nothing for police (not notified yet)
    assert b["disclosable"] == {"transaction_paused": True, "reason_category": "call_from_someone_claiming_authority", "customer_at_branch": True}
    assert raw["policy"]["may_disclose"] == ["transaction_paused", "reason_category", "customer_at_branch", "police_notified"]
    assert b["customer_reference"] == "お母様" and b["language"] == "ja"
    # no balance, account number or other customer anywhere in what the conversation service receives
    text = json.dumps(raw, ensure_ascii=False)
    bank = env.bank
    secrets = [str(bank.accounts["acct-tanaka-0001"].balance_jpy), "acct-", "cust-", "3000000", "3,000,000", "ミライケンセツ", "タナカ", "田中 圭子"]
    secrets += [c.display_name_ja for c in bank.customers.values() if c.customer_ref != "cust-tanaka-0001"][:80]
    assert not [s for s in secrets if s in text], [s for s in secrets if s in text]
    assert not re.search(r"\d{6,}", text.replace("+819012345678", "").replace("+81312345678", ""))
    case = env.case(case_id)
    assert case["call_id"] == b["call_id"] and case["case_code"] == "4821"
    assert "contact_notice_sent" in [e["type"] for e in env.deps.store.repo.list_events(case_id)]


def test_brief_schema_forbids_balance_account_numbers_and_other_customers():
    brief = load_example("contact-brief-tanaka.json")
    v = brief_validator()
    v.validate(brief)
    for extra in ({"balance_jpy": 7420000}, {"account_id": "acct-tanaka-0001"}, {"other_payers": ["cust-0002"]}):
        assert list(v.iter_errors({**brief, **extra})), extra
    assert list(v.iter_errors({**brief, "disclosable": {**brief["disclosable"], "balance_jpy": 1}}))
    with pytest.raises(Exception):
        ContactBrief.model_validate({**brief, "balance_jpy": 7420000})


def test_amount_band_and_police_flag_are_disclosed_only_when_allowed_and_true(make_env):
    env, case_id = paused_case(make_env)
    wishes = env.deps.store.repo.get_active_wishes("cust-tanaka-0001")
    wishes["disclosure"]["may_disclose"] = ["transaction_paused", "amount_band", "police_notified"]
    env.deps.store.repo.put_wishes(wishes)
    assert env.client.post(f"/cases/{case_id}/police-notified", json={"teller_id": "teller-sato"}, headers=STAFF).status_code == 200
    resp = env.client.post(f"/cases/{case_id}/contact-call", headers=STAFF)
    assert resp.status_code == 200 and resp.json()["call_id"].endswith("-2")
    b = env.conv.raw[-1]["brief"]
    assert b["disclosable"] == {"transaction_paused": True, "amount_band": "1m_to_5m", "police_notified": True}  # no reason_category, not allowed
    brief_validator().validate(b)


def test_case_code_is_four_digits_and_overridable_via_env(make_env, monkeypatch):
    env, _ = paused_case(make_env, svc={"case_code": None})
    assert re.fullmatch(r"\d{4}", env.conv.raw[0]["brief"]["case_code"])
    monkeypatch.setenv("MIMAMORI_CASE_CODE", "7777")
    from case_svc.config import SvcConfig

    assert SvcConfig.from_env().case_code == "7777"
    monkeypatch.setenv("MIMAMORI_CASE_CODE", "77")
    with pytest.raises(ValueError):
        SvcConfig.from_env()


def set_wishes(env, **changes):
    w = env.deps.store.repo.get_active_wishes("cust-tanaka-0001")
    for k, v in changes.items():
        if k == "contact":
            w["trusted_contacts"][0].update(v)
        else:
            w[k] = v
    env.deps.store.repo.put_wishes(w)


@pytest.mark.parametrize("setup,reason", [
    (lambda env: set_wishes(env, contact={"phone_changed_at": "2026-10-05T10:00:00+09:00"}), "contact_number_changed_recently"),
    (lambda env: set_wishes(env, contact={"display_name": "ミライケンセツ代表"}), None),  # a different name: not linked
    (lambda env: set_wishes(env, outbound_notice_consent=False), "no_notice_consent"),
])
def test_contact_suspected_or_no_consent_means_no_call(make_env, setup, reason):
    env, case_id, _ = replay(make_env, "A", upto=4)
    setup(env)
    env.client.post(f"/cases/{case_id}/decision", json=PAUSE, headers=STAFF)
    assert bool(env.conv.calls) == (reason is None)
    assert env.case(case_id)["contact_suspected"] == reason


def test_contact_linked_to_the_payee_is_suspected(make_env):
    env, case_id, _ = replay(make_env, "A", upto=4)
    holder = env.bank.customers[env.bank.accounts["acct-mule-0001"].customer_ref]
    set_wishes(env, contact={"display_name": holder.display_name_ja})
    env.client.post(f"/cases/{case_id}/decision", json=PAUSE, headers=STAFF)
    assert env.conv.calls == [] and env.case(case_id)["contact_suspected"] == "contact_linked_to_payee"


def test_contact_flagged_in_teller_notes_is_suspected(make_env):
    env, case_id, _ = replay(make_env, "A", upto=4)
    note = {"teller_id": "teller-sato", "text": "Yuki's number matches a number seen on the scam call", "flags": ["contact_flagged"]}
    assert env.client.post(f"/cases/{case_id}/notes", json=note, headers=STAFF).status_code == 201
    env.client.post(f"/cases/{case_id}/decision", json=PAUSE, headers=STAFF)
    assert env.conv.calls == [] and env.case(case_id)["contact_suspected"] == "contact_flagged_in_notes"


def test_conversation_service_down_does_not_undo_the_pause_and_manual_retry_reports_503(make_env):
    env, case_id = paused_case(make_env, conv_fail=True)
    case = env.case(case_id)
    assert case["status"] == "paused" and case["call_id"] is None
    assert env.client.post(f"/cases/{case_id}/contact-call", headers=STAFF).status_code == 503
    env.conv.fail = False
    assert env.client.post(f"/cases/{case_id}/contact-call", headers=STAFF).json()["call_id"].endswith("-1")


def outcome_body(env, case_id, **over):
    case = env.case(case_id)
    view = {"case_id": case_id, "call_id": case["call_id"], "nature": "information",
            "verification": {"caller_number_match": True, "case_code_match": True}, "reached": True, "concerned": True,
            "coming_to_branch": True, "eta_minutes": 30, "wants_callback_later": False, "disclosed": ["transaction_paused"],
            "recorded_at": "2026-10-13T12:04:30+09:00", **over}
    return {"call_id": case["call_id"], "outcome": "contact_view", "contact_view": view}


def test_contact_outcome_is_information_and_reached_needs_both_checks(make_env):
    env, case_id = paused_case(make_env)
    resp = env.client.post(f"/cases/{case_id}/contact-outcome", json=outcome_body(env, case_id))
    assert resp.status_code == 200 and resp.json()["contact_view"]["reached"] is True and resp.json()["contact_view"]["nature"] == "information"
    body = outcome_body(env, case_id, verification={"caller_number_match": True, "case_code_match": False})  # claims reached anyway
    assert env.client.post(f"/cases/{case_id}/contact-outcome", json=body).json()["contact_view"]["reached"] is False
    assert "contact_outcome" in [e["type"] for e in env.deps.store.repo.list_events(case_id)]
    wrong = outcome_body(env, case_id)
    wrong["call_id"] = "call-9999-9"
    assert env.client.post(f"/cases/{case_id}/contact-outcome", json=wrong).status_code == 409
    assert env.client.post(f"/cases/{case_id}/contact-outcome", json={"call_id": "x", "outcome": "contact_view"}).status_code == 422


def test_verification_failed_is_flagged_and_repeats_are_accepted(make_env):
    env, case_id = paused_case(make_env)
    call_id = env.case(case_id)["call_id"]
    for _ in range(3):
        resp = env.client.post(f"/cases/{case_id}/contact-outcome", json={"call_id": call_id, "outcome": "verification_failed"})
        assert resp.status_code == 200 and resp.json()["verification_failed"] is True
    types = [e["type"] for e in env.deps.store.repo.list_events(case_id)]
    assert types.count("verification_failed") == 3
    assert env.case(case_id)["contact_view"] is None  # nothing was disclosed or learned


def test_wishes_changed_during_an_open_case_are_frozen_and_the_previous_contact_notified(make_env):
    env, case_id, _ = replay(make_env, "A", upto=2)
    new = load_example("advance-wishes-tanaka.json")
    new["trusted_contacts"][0].update(contact_id="tc-attacker", display_name="攻撃者", phone_e164="+819099999999")
    resp = env.client.put("/customers/cust-tanaka-0001/wishes", json=new, headers=STAFF)
    assert resp.status_code == 200
    assert resp.json()["status"] == "frozen_pending_review" and "open case" in resp.json()["frozen_reason"]
    repo = env.deps.store.repo
    assert repo.get_active_wishes("cust-tanaka-0001")["trusted_contacts"][0]["contact_id"] == "tc-yuki"  # still in force
    assert [w["status"] for w in repo.list_wishes("cust-tanaka-0001")][-1] == "frozen_pending_review"
    evt = [e for e in repo.list_events(case_id) if e["type"] == "wishes_frozen"][0]
    assert evt["data"]["previous_contact_id"] == "tc-yuki" and evt["data"]["previous_contact_notified"] is True
    env.client.post(f"/cases/{case_id}/decision", json=PAUSE, headers=STAFF)
    assert env.conv.raw[0]["brief"]["contact"]["locked_phone_e164"] == "+819012345678"  # the call goes to the original contact


def test_wishes_change_with_no_open_case_supersedes(make_env):
    env = make_env()
    new = load_example("advance-wishes-tanaka.json")
    resp = env.client.put("/customers/cust-tanaka-0001/wishes", json=new, headers=STAFF)
    assert resp.json() == {"customer_ref": "cust-tanaka-0001", "version": 3, "status": "active", "frozen_reason": None}
    assert env.deps.store.repo.get_active_wishes("cust-tanaka-0001")["version"] == 3
    assert env.client.put("/customers/cust-other/wishes", json=new).status_code == 422
