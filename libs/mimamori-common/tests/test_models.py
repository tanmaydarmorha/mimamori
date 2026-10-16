import pytest
from pydantic import ValidationError

from mimamori_common import models as m
from mimamori_common.schemas import load_example

EXAMPLES = {
    "advance-wishes-tanaka.json": m.AdvanceWishes,
    "evidence-card-tanaka.json": m.EvidenceCard,
    "contact-brief-tanaka.json": m.ContactBrief,
    "call-turn-tanaka.json": m.CallTurn,
    "contact-view-tanaka.json": m.ContactView,
    "question-bank-general.json": m.QuestionBank,
}


@pytest.mark.parametrize("name", EXAMPLES)
def test_schema_examples_validate_with_models(name):
    EXAMPLES[name].model_validate(load_example(name))


def test_playbooks_and_templates_validate():
    for pb in load_example("playbooks.json"):
        m.Playbook.model_validate(pb)
    for t in load_example("call-templates.json"):
        m.CallTemplate.model_validate(t)


def test_contact_brief_has_no_field_for_balance_or_other_customers():
    brief = load_example("contact-brief-tanaka.json")
    for forbidden in ("balance_jpy", "account_id", "payee", "other_customers"):
        with pytest.raises(ValidationError):
            m.ContactBrief.model_validate({**brief, forbidden: "x"})
    with pytest.raises(ValidationError):
        m.ContactBrief.model_validate({**brief, "disclosable": {**brief["disclosable"], "balance_jpy": 1}})


def test_contact_view_is_always_information():
    view = load_example("contact-view-tanaka.json")
    with pytest.raises(ValidationError):
        m.ContactView.model_validate({**view, "nature": "instruction"})


def test_copilot_turn_rejects_likelihood_numbers_and_free_text_questions():
    turn = {"indicators": [], "cover_story": {"stated_reason": None, "consistent_with_history": "unknown", "matches_playbook": None},
            "leading_hypothesis": "legitimate", "next_question_id": "q.general.purpose", "rationale_en": "x"}
    m.CopilotTurn.model_validate(turn)
    with pytest.raises(ValidationError):
        m.CopilotTurn.model_validate({**turn, "likelihood": 0.9})
    with pytest.raises(ValidationError):
        m.CopilotTurn.model_validate({**turn, "next_question_id": "ask her about the trip"})


def test_decision_request_rules():
    base = {"rationale": "cooling-off per her wishes", "teller_id": "teller-1"}
    m.DecisionRequest(action="pause", basis="advance_wishes", **base)
    with pytest.raises(ValidationError):
        m.DecisionRequest(action="pause", **base)  # a pause needs a stated basis
    with pytest.raises(ValidationError):
        m.DecisionRequest(action="release", **base)
    with pytest.raises(ValidationError):
        m.DecisionRequest(action="release", release_reason="manager_review_second_confirmation", **base)
    m.DecisionRequest(action="release", release_reason="manager_review_second_confirmation", manager_id="mgr-1", second_confirmed_by="teller-2", **base)


def test_contact_outcome_request_needs_view_exactly_when_contact_view():
    view = m.ContactView.model_validate(load_example("contact-view-tanaka.json"))
    m.ContactOutcomeRequest(call_id="call-1", outcome="contact_view", contact_view=view)
    m.ContactOutcomeRequest(call_id="call-1", outcome="verification_failed")
    with pytest.raises(ValidationError):
        m.ContactOutcomeRequest(call_id="call-1", outcome="contact_view")
    with pytest.raises(ValidationError):
        m.ContactOutcomeRequest(call_id="call-1", outcome="verification_failed", contact_view=view)


def test_phone_messages_are_discriminated():
    from pydantic import TypeAdapter

    msg = TypeAdapter(m.PhoneClientMessage).validate_python(
        {"type": "callback", "caller_number": "+819012345678", "menu_choice": m.PHONE_MENU_RETURN_CALL, "case_code": "4821"})
    assert isinstance(msg, m.PhoneCallback)


def test_police_summary_needs_officer_name_and_title():
    with pytest.raises(ValidationError):
        m.PoliceSummaryRequest(officer_name="", officer_title="Inspector", requested_items=["amount"], teller_id="t")
    with pytest.raises(ValidationError):
        m.PoliceSummaryRequest(officer_name="X", officer_title="Y", requested_items=[], teller_id="t")


def test_transfer_and_hold_models_compose():
    req = m.TransferRequest(customer_ref="c", account_id="a", channel="counter", kind="transfer", amount_jpy=3_000_000,
                            payee=m.PayeeRef(name_kana="カ）ミライケンセツ", relation="same_bank", account_id="acct-mule-0001"))
    t = m.Transfer(transfer_id="tr-1", status="pending_alert", scoring="alert", case_id="case-2026-1013-0007", request=req,
                   created_at="2026-10-13T11:40:00+09:00")
    assert t.hold is None and t.request.amount_jpy == 3_000_000


def test_web_app_has_healthz():
    from fastapi.testclient import TestClient

    from mimamori_common.web import create_app

    assert TestClient(create_app("scoring")).get("/healthz").json()["service"] == "scoring"
