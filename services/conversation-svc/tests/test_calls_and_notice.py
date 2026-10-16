import copy

import httpx
import pytest
from mimamori_common.models import ContactOutcomeRequest
from mimamori_common.schemas import load_example

from conversation_svc.case_client import CaseSvcClient
from conversation_svc.fixed_text import OPENING_JA

from .conftest import LOCKED, make_request


def test_post_calls_sends_a_notice_that_reveals_only_the_allowed_things(harness):
    r = harness.post_call()
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "notice_sent" and body["call_id"] == "call-0007-1"
    text = body["notice_text_ja"]
    # allowed: branch, "about your mother", published number, case code
    assert "サンプル銀行 駅前支店" in text and "お母様" in text and "03-1234-5678" in text and "4821" in text
    # nothing else: no transaction, amount, police, pause, account or name
    for forbidden in ["円", "万", "振込", "送金", "口座", "残高", "警察", "詐欺", "保留", "停止", "田中", "窓口", "手続き"]:
        assert forbidden not in text, forbidden
    # asks the family to verify the bank on the published number; does not claim to prove identity
    assert "公開番号" in text and "本人確認" not in text and "身元" not in text


def test_notice_is_listed_for_the_locked_number_only(harness):
    harness.post_call()
    got = harness.client.get("/notices", params={"to": "090-1234-5678"}).json()
    assert len(got) == 1
    assert got[0]["to_phone_e164"] == LOCKED and got[0]["case_code"] == "4821"
    assert got[0]["published_phone_e164"] == "+81312345678"
    assert harness.client.get("/notices", params={"to": "+819099999999"}).json() == []


def test_post_calls_is_idempotent_but_rejects_a_different_brief_under_the_same_id(harness):
    assert harness.post_call().status_code == 200
    assert harness.post_call().status_code == 200
    assert len(harness.client.get("/notices", params={"to": LOCKED}).json()) == 1
    other = make_request(disclosable={"transaction_paused": True})
    assert harness.post_call(other).status_code == 409


@pytest.mark.parametrize("extra", [{"balance_jpy": 3_000_000}, {"account_number": "1234567"}, {"payee": "カ）ミドリ"}])
def test_a_brief_with_a_forbidden_field_is_rejected(harness, extra):
    body = {"brief": copy.deepcopy(load_example("contact-brief-tanaka.json")), "policy": {"may_disclose": ["transaction_paused"]}}
    body["brief"]["disclosable"].update(extra)
    assert harness.client.post("/calls", json=body).status_code == 422
    body["brief"].update(extra)
    assert harness.client.post("/calls", json=body).status_code == 422


def test_healthz(harness):
    assert harness.client.get("/healthz").json()["service"] == "conversation-svc"


def test_opening_line_says_automated_and_recorded():
    assert "自動音声" in OPENING_JA and "録音" in OPENING_JA


def test_case_client_posts_to_the_contract_path_as_system():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen.update(path=request.url.path, role=request.headers["x-mimamori-role"], body=request.read().decode())
        return httpx.Response(200, json={})

    client = CaseSvcClient("http://case-svc:8083", transport=httpx.MockTransport(handler))
    import asyncio

    outcome = ContactOutcomeRequest(call_id="call-0007-1", outcome="verification_failed")
    assert asyncio.run(client.post_outcome("case-2026-1013-0007", outcome)) is True
    assert seen["path"] == "/cases/case-2026-1013-0007/contact-outcome" and seen["role"] == "system"
    assert "verification_failed" in seen["body"]


def test_case_client_retries_5xx_then_gives_up_but_not_on_4xx():
    calls = []

    def handler(request):
        calls.append(1)
        return httpx.Response(503)

    import asyncio

    client = CaseSvcClient("http://x", retries=2, transport=httpx.MockTransport(handler))
    assert asyncio.run(client.post_outcome("case-1", ContactOutcomeRequest(call_id="c", outcome="verification_failed"))) is False
    assert len(calls) == 2
    calls.clear()
    client = CaseSvcClient("http://x", retries=3, transport=httpx.MockTransport(lambda r: (calls.append(1), httpx.Response(404))[1]))
    assert asyncio.run(client.post_outcome("case-1", ContactOutcomeRequest(call_id="c", outcome="verification_failed"))) is False
    assert len(calls) == 1
