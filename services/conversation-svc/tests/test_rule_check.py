import itertools

import pytest

from conversation_svc.outgoing_check import amount_problems, check_outgoing, phrase_problems
from conversation_svc.templates import TemplateBook
from conversation_svc.verify import codes_match, normalise_e164, numbers_match

from .conftest import DISCLOSABLE_ALL, make_request


@pytest.mark.parametrize("text", [
    "三百万円です", "300万円", "３００万円", "300万", "３００万", "さんびゃくまんえん", "サンビャクマンエン",
    "ひゃくまん", "ごせんえん", "1000000", "100,000円", "三〇〇万", "参百萬円", "百万", "二千万円",
    "口座番号は1234567です", "１２３４５６７", "①②",
])
def test_amounts_in_any_form_are_rejected(text):
    assert amount_problems(text), text


@pytest.mark.parametrize("text", [
    "ご心配をおかけして申し訳ございません。", "ありません", "いたしません", "一時的に", "一緒にいらっしゃいます",
    "お待ちしております。",
])
def test_ordinary_sentences_pass(text):
    assert amount_problems(text) == []


def test_every_template_and_fallback_is_clean_for_every_disclosure_combination():
    book = TemplateBook.load()
    fields = ["transaction_paused", "reason_category", "customer_at_branch", "police_notified", "amount_band"]
    values = {"transaction_paused": [True, False], "reason_category": ["call_from_someone_claiming_authority", "unfamiliar_payee", "unusual_amount"],
              "customer_at_branch": [True, False], "police_notified": [True, False], "amount_band": ["under_1m", "1m_to_5m", "over_5m"]}
    seen = 0
    for chosen in itertools.product(*[[None, *values[f]] for f in fields]):
        disclosable = {f: v for f, v in zip(fields, chosen) if v is not None}
        request = make_request(disclosable=disclosable)
        for intent in book.by_intent:
            filled = book.fill(intent, request)
            assert amount_problems(filled.text) == [], (intent, disclosable, filled.text)
            assert "{" not in filled.text
            seen += 1
    assert seen > 1000


def test_templates_only_disclose_what_the_brief_and_policy_allow():
    book = TemplateBook.load()
    # reason_category is in the brief but the policy does not allow it: fallback, nothing disclosed
    request = make_request(disclosable=DISCLOSABLE_ALL, may_disclose=["transaction_paused"])
    filled = book.fill("what_happened", request)
    assert filled.used_fallback and filled.disclosed == ()
    assert "公的機関" not in filled.text
    # false boolean cannot be spoken as true
    request = make_request(disclosable={"customer_at_branch": False})
    assert book.fill("is_she_safe", request).used_fallback


def test_how_much_template_never_says_large_for_the_lowest_band():
    book = TemplateBook.load()
    low = book.fill("how_much", make_request(disclosable={"amount_band": "under_1m"}))
    high = book.fill("how_much", make_request(disclosable={"amount_band": "over_5m"}))
    assert low.used_fallback and not high.used_fallback and high.disclosed == ("amount_band",)


@pytest.mark.parametrize("phrase", [
    "三百万円です", "ご心配ですね、300万円の件", "口座は安全です", "警察に連絡しました", "大丈夫ですよ",
    "Please wait", "x" * 31, "ご心配をおかけして申し訳ございませんでしたがとてもとても長いです。", "",
    "ご連絡ください", "ignore previous", "さんびゃくまんえんですがご心配",
])
def test_bad_connecting_phrases_are_rejected(phrase):
    assert phrase_problems(phrase)


@pytest.mark.parametrize("phrase", ["ご心配をおかけして申し訳ございません。", "ご心配なお気持ち、お察しいたします。", "お気持ちはよく分かります。"])
def test_good_connecting_phrases_pass(phrase):
    assert phrase_problems(phrase) == []


def test_check_outgoing_requires_an_approved_body():
    bodies = {"申し訳ございません、その点については担当者から改めてご説明いたします。"}
    body = next(iter(bodies))
    assert check_outgoing(body, bodies).ok
    assert check_outgoing("お気持ちはよく分かります。" + body, bodies, "お気持ちはよく分かります。").ok
    assert not check_outgoing("残高は多いです。" + body, bodies, "残高は多いです。").ok
    assert not check_outgoing("お母様は元気です。", bodies).ok


@pytest.mark.parametrize("given,locked,expected", [
    ("090-1234-5678", "+819012345678", True),
    ("+81 90 1234 5678", "+819012345678", True),
    ("０９０１２３４５６７８", "+819012345678", True),
    ("+81 (0)90-1234-5678", "+819012345678", True),
    ("0081 90 1234 5678", "+819012345678", True),
    ("090-1234-5679", "+819012345678", False),
    ("", "+819012345678", False),
    ("not a number", "+819012345678", False),
])
def test_numbers_are_compared_as_e164(given, locked, expected):
    assert numbers_match(given, locked) is expected


def test_code_matching_normalises_width_and_space():
    assert codes_match("４８２１", "4821") and codes_match(" 48 21", "4821")
    assert not codes_match("4822", "4821") and not codes_match("", "4821")
    assert normalise_e164("garbage") == ""
