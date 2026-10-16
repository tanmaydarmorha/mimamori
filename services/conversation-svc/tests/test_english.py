"""WI-005: the English pack. Every spoken word of an `en` call comes from the English templates, the
English rule check is as strict as the Japanese one, and a `ja` call also carries English glosses."""

import re

import pytest
from mimamori_common.models import CallTemplate
from mimamori_common.schemas import load_example

from conversation_svc.fixed_text import NOTICE_TEMPLATE_EN, NOTICE_TEMPLATE_JA, OPENING_EN, REASON_CATEGORY_EN, REASON_CATEGORY_JA, text_for
from conversation_svc.outgoing_check import (
    amount_problems_en, check_outgoing, phrase_problems, phrase_problems_en,
)
from conversation_svc.templates import TemplateBook

from .conftest import DISCLOSABLE_ALL, make_request, turn

BOOK = TemplateBook.load()
SLOT = re.compile(r"\{([a-z_]+)\}")


def says(messages):
    return [m for m in messages if m["type"] == "say"]


def test_every_template_has_matching_slots_in_all_four_strings():
    for raw in load_example("call-templates.json"):
        t = CallTemplate.model_validate(raw)
        norm = lambda s, suffix: {x.removesuffix(suffix) for x in SLOT.findall(s)}  # noqa: E731
        assert norm(t.ja, "_ja") == norm(t.en, "_en"), t.intent
        assert norm(t.fallback_ja, "_ja") == norm(t.fallback_en, "_en"), t.intent


def test_fixed_text_packs_agree():
    assert set(SLOT.findall(NOTICE_TEMPLATE_JA)) == set(SLOT.findall(NOTICE_TEMPLATE_EN))
    assert set(REASON_CATEGORY_JA) == set(REASON_CATEGORY_EN)
    assert text_for("en").opening == OPENING_EN


@pytest.mark.parametrize("bad", ["three million yen", "¥3,000,000", "account number 1234", "about 5 dollars", "two lakh rupees",
                                 "a hundred", "$20", "the account  number is"])
def test_english_check_rejects_amounts_and_accounts(bad):
    assert amount_problems_en(bad), bad


@pytest.mark.parametrize("bad", ["The police are involved.", "Please hold on.", "It will be safe.", "I will transfer it", "your account",
                                 "How much is it", "I'm sorry 3 times", "Sorry – really", "x" * 61, ""])
def test_english_phrase_rejects_facts_and_odd_characters(bad):
    assert phrase_problems_en(bad), bad


def test_english_phrase_accepts_a_plain_lead_in():
    assert phrase_problems_en("I'm sorry for the worry.") == []
    assert phrase_problems_en("Thank you for calling, and I understand.") == []


def test_someone_and_money_are_not_number_words():
    assert amount_problems_en("We were told of a call from someone claiming to be an official.") == []


def test_every_filled_english_template_passes_the_english_check():
    for may in (list(DISCLOSABLE_ALL), []):
        request = make_request(may_disclose=may, language="en")
        for intent in BOOK.by_intent:
            filled = BOOK.fill(intent, request)
            assert filled.gloss_en is None
            assert check_outgoing(filled.text, BOOK.all_bodies(request), language="en").ok, filled.text
            assert not re.search(r"[぀-ヿ一-鿿]", filled.text)


def test_english_check_requires_an_approved_body_with_a_space_before_the_phrase():
    request = make_request(language="en")
    bodies = BOOK.all_bodies(request)
    body = BOOK.fill("is_she_safe", request).text
    assert check_outgoing("I'm sorry for the worry. " + body, bodies, "I'm sorry for the worry.", language="en").ok
    assert not check_outgoing("I'm sorry for the worry." + body, bodies, "I'm sorry for the worry.", language="en").ok
    assert not check_outgoing("Your mother owes three million yen.", bodies, language="en").ok


def test_japanese_check_is_unchanged():
    assert phrase_problems("ご心配なお気持ち、お察しいたします。") == []
    assert phrase_problems("警察です")


# ----------------------------------------------------------------------------------- calls


def en_call(harness, messages):
    harness.post_call(make_request(language="en"))
    return harness.call(messages)


def test_english_notice_is_english_and_reveals_only_the_allowed_things(harness):
    body = harness.post_call(make_request(language="en")).json()
    text = body["notice_text_ja"]  # CallResponse keeps its field name
    notice = harness.client.get("/notices", params={"to": "+819012345678"}).json()[0]
    assert notice["text"] == text and notice["language"] == "en" and notice["gloss_en"] is None
    assert "Sample Bank, Ekimae Branch" in text and "your mother" in text and "03-1234-5678" in text and "4821" in text
    for forbidden in ["yen", "transfer", "account", "balance", "police", "fraud", "paused", "hold", "Tanaka"]:
        assert forbidden not in text.lower(), forbidden
    assert not re.search(r"[぀-ヿ一-鿿]", text)


def test_english_call_speaks_english_only_and_refuses_the_amount(harness):
    out = en_call(harness, [turn("What happened?"), turn("Is my mother safe?"), turn("How much is it?"), turn("I'm coming right away")])
    spoken = says(out)
    assert spoken[0]["text"] == OPENING_EN and spoken[0]["language"] == "en" and "gloss_en" not in spoken[0]
    assert all(m["language"] == "en" and "gloss_en" not in m for m in spoken)
    assert "precaution" in spoken[1]["text"]
    assert "with our staff" in spoken[2]["text"]
    assert "unable to share the amount over the phone" in spoken[3]["text"]  # the polite refusal: amount is not in the wishes
    assert spoken[-1]["template_intent"] == "coming_to_branch"
    for m in spoken:
        assert not re.search(r"[぀-ヿ一-鿿]", m["text"]) and not re.search(r"\d", m["text"]), m["text"]
        assert "I'm sorry for the worry." in m["text"] or m["template_intent"] == "opening"
    assert out[-1] == {"type": "ended", "reason": "completed"}
    assert harness.client.app.state.tts["ja"].spoken == []  # no Japanese reached the Japanese voice


def test_english_call_drops_a_bad_english_phrase_and_keeps_the_template(harness):
    harness.model.json_handler = lambda s, u, sc: {"intent": "how_much", "connecting_phrase": "The police froze three million yen", "signals": {}}
    out = en_call(harness, [turn("How much?")])
    text = says(out)[1]["text"]
    assert text == BOOK.fill("how_much", make_request(language="en")).text


def test_classifier_is_asked_for_the_phrase_in_the_call_language(harness):
    en_call(harness, [turn("What happened?")])
    assert "English lead-in" in harness.model.calls[0].system and "connecting_phrase" in harness.model.calls[0].system
    harness.model.calls.clear()
    harness.post_call(make_request(call_id="call-0008-1"))
    harness.call([turn("何があったんですか？")])


def test_japanese_call_carries_english_glosses_and_only_japanese_reaches_tts(harness):
    harness.post_call()
    notice = harness.client.get("/notices", params={"to": "+819012345678"}).json()[0]
    assert notice["language"] == "ja" and notice["gloss_en"].startswith("This is Sample Bank, Ekimae Branch.")
    assert "your mother" in notice["gloss_en"] and "4821" in notice["gloss_en"]
    out = harness.call([turn("母は無事ですか？"), turn("どうすればいいですか")])
    spoken = says(out)
    assert spoken[0]["gloss_en"] == OPENING_EN and spoken[0]["language"] == "ja"
    assert spoken[1]["gloss_en"].endswith("(+ a short lead-in, not translated)") and "with our staff" in spoken[1]["gloss_en"]
    tts = harness.client.app.state.tts
    assert tts["en"].spoken == []
    assert tts["ja"].spoken and not any(re.search(r"[A-Za-z]", t) for t in tts["ja"].spoken)
