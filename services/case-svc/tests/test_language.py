"""WI-005: the case's conversation language (ja | en): set before the first turn, locked after, audited,
and carried into the contact brief with the matching customer reference."""

from conftest import REPLAY, SCENARIOS, STAFF, replay

from mimamori_common.llm import FakeClient

PAUSE = {"action": "pause", "basis": "advance_wishes", "rationale": "Police impersonation and secrecy", "teller_id": "teller-sato"}


def patch(env, case_id, language, actor="teller-sato"):
    return env.client.patch(f"/cases/{case_id}/language", json={"language": language, "actor": actor}, headers=STAFF)


def fresh_case(make_env):
    env = make_env(copilot=FakeClient(json=list(REPLAY["A"]["outputs"])))
    return env, env.open_case(**SCENARIOS["A"])


def test_language_defaults_to_ja_and_shows_in_the_list(make_env):
    env, case_id = fresh_case(make_env)
    assert env.client.get(f"/cases/{case_id}", headers=STAFF).json()["language"] == "ja"
    assert env.client.get("/cases", headers=STAFF).json()[0]["language"] == "ja"


def test_language_can_be_set_before_the_first_turn_and_is_audited(make_env):
    env, case_id = fresh_case(make_env)
    resp = patch(env, case_id, "en")
    assert resp.status_code == 200 and resp.json()["language"] == "en"
    assert patch(env, case_id, "ja").json()["language"] == "ja"  # changeable until the first turn
    audit = env.client.get(f"/cases/{case_id}/audit").json()
    set_ = [a for a in audit if a["action"] == "case.language_set"]
    assert len(set_) == 2 and set_[0]["actor"] == "teller-sato"


def test_language_is_locked_after_the_first_turn(make_env):
    env, case_id = fresh_case(make_env)
    env.turn(case_id, REPLAY["A"]["customer_turns"][0])
    resp = patch(env, case_id, "en")
    assert resp.status_code == 409 and resp.json()["error"] == "language_locked"
    assert env.client.get(f"/cases/{case_id}", headers=STAFF).json()["language"] == "ja"


def test_unknown_language_is_rejected(make_env):
    env, case_id = fresh_case(make_env)
    assert patch(env, case_id, "fr").status_code == 422


def test_english_case_gives_an_english_brief_and_reference(make_env):
    env, case_id = fresh_case(make_env)
    patch(env, case_id, "en")
    for text in REPLAY["A"]["customer_turns"][:4]:
        env.turn(case_id, text)
    assert env.client.post(f"/cases/{case_id}/decision", json=PAUSE, headers=STAFF).status_code == 200
    brief = env.conv.raw[0]["brief"]
    assert brief["language"] == "en" and brief["customer_reference"] == "your mother"
    assert brief["branch"]["name_en"] == "Sample Bank, Ekimae Branch"


def test_japanese_case_brief_is_unchanged_in_language(make_env):
    env, case_id, _ = replay(make_env, "A", upto=4)
    env.client.post(f"/cases/{case_id}/decision", json=PAUSE, headers=STAFF)
    brief = env.conv.raw[0]["brief"]
    assert brief["language"] == "ja" and brief["customer_reference"] == "お母様"


# ------------------------------------------------------------------ WI-006: the counter copilot in English


def _system_prompt_of(make_env, language):
    env, _, _ = replay(make_env, "A", upto=1, language=language)
    return env.copilot.calls[0].system


def test_english_case_prompt_has_the_english_examples_only(make_env):
    en = _system_prompt_of(make_env, "en")
    assert "The conversation is in English" in en and "The police called and said not to tell anyone." in en
    assert "It's a birthday present, so I'm keeping it a secret from my wife." in en
    assert "検察の人から連絡があって" not in en and "{language}" not in en


def test_japanese_case_prompt_has_the_japanese_examples_only(make_env):
    ja = _system_prompt_of(make_env, "ja")
    assert "The conversation is in Japanese" in ja and "検察の人から連絡があって" in ja
    assert "The police called and said not to tell anyone." not in ja


def test_both_languages_share_one_set_of_definitions():
    from case_svc.copilot import system_prompt

    head = lambda s, name: s.split("Examples of what customers say")[0].replace(f"in {name}", "in X")  # noqa: E731
    assert head(system_prompt("en"), "English") == head(system_prompt("ja"), "Japanese")
    assert "impersonated_relative" in system_prompt("en") and "someone **claiming** to be family" in system_prompt("en")


def test_next_question_and_hold_line_have_the_bank_english(make_env):
    from case_svc.bank import load_bank

    env, case_id, cards = replay(make_env, "A", upto=4, language="en")
    view = load_bank(env.deps.intel)
    nq = cards[3]["next_question"]
    assert nq["en_filled"] == view.questions[nq["question_id"]]["en"].replace("{payee_name}", "カ）ミライケンセツ").replace("{branch_name}", "Sample Bank, Ekimae Branch")
    assert nq["ja_filled"] and nq["ja_filled"] != nq["en_filled"]
    case = env.client.get(f"/cases/{case_id}", headers=STAFF).json()
    line = view.hold_lines[case["card"]["risk"]["hold_line_id"]]
    assert case["hold_line"]["en"] == line["en"] and case["hold_line"]["ja"] == line["ja"]
    assert "{" not in nq["en_filled"]


def test_the_seeded_first_question_has_english_too(make_env):
    env, case_id = fresh_case(make_env)
    nq = env.client.get(f"/cases/{case_id}", headers=STAFF).json()["card"]["next_question"]
    assert nq["question_id"] == "q.general.purpose" and nq["en_filled"].startswith("If you don't mind")
