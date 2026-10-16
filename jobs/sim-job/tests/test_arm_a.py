import asyncio

from sim_job.arm_a import ArmA, red_flags, triggered
from sim_job.params import SimParams
from sim_job.personas import QuestionIndex, ScriptedRolePlayer
from sim_job.scenarios import by_id, synthetic_scenarios

SC = by_id(synthetic_scenarios())
IDX = QuestionIndex.load()


def run(sid, **kw):
    params = SimParams(**kw)
    return asyncio.run(ArmA(IDX, params).run(SC[sid], ScriptedRolePlayer()))


def test_red_flag_lexicon_hears_published_flags_not_everything():
    assert "secrecy_instruction" in red_flags("誰にも言うなって言われてるの。", "check_contact")
    assert "official_instruction" in red_flags("警察の人から電話があってね", "check_contact")
    assert "script_phrase" in red_flags("お金を安全な口座に移さないといけない", "check_instructions")
    assert "no_documents" in red_flags("書類は、後で送ってもらうことになっていて。", "verify_purpose")
    # documents are only a flag when the teller asked about documents
    assert "no_documents" not in red_flags("書類は、後で送ってもらうことになっていて。", "check_contact")
    # the spike's trap: 内緒 about a past surprise is not "told not to tell"
    assert red_flags("車のことは孫には内緒にしてたけど、もう本人も知ってるしね。", "check_contact") == []
    assert red_flags("請求書はここにあります。", "verify_purpose") == []


def test_amount_threshold_is_a_stated_parameter():
    assert triggered(SC["syn-scam-01"], SimParams(amount_threshold_jpy=1_000_000))
    assert not triggered(SC["syn-scam-08"], SimParams(amount_threshold_jpy=1_000_000))  # 900,000
    assert triggered(SC["syn-scam-08"], SimParams(amount_threshold_jpy=500_000))
    out = run("syn-scam-08")
    assert not out.engaged and not out.paused and out.transcript == []


def test_hero_is_stopped_by_the_routine_when_the_victim_mentions_police():
    out = run("syn-scam-01")
    assert out.paused and out.paused_at_turn == 2  # the who-asked reply carries the script phrases
    assert out.flag_first_turn == out.paused_at_turn
    assert [q["id"] for q in out.questions][:2] == ["q.general.purpose", "q.general.who_asked"]
    assert any(r.startswith(("script_phrase", "official_instruction")) for r in out.reasons)


def test_coached_victim_with_papers_passes_the_counter_check_the_npa_gap():
    out = run("syn-scam-04")  # cover story + invoice produced, other bank
    assert out.engaged and not out.flag_ever and not out.paused
    assert len(out.questions) == 4  # the whole routine was asked and nothing was heard


def test_legitimate_with_papers_passes_and_without_papers_is_falsely_paused():
    assert not run("syn-legit-03").paused  # house deposit, contract in hand
    assert run("syn-legit-04").paused  # gift, "no documents": today's check stops it too


def test_teller_not_acting_on_a_flag_is_recorded_not_hidden():
    out = run("syn-scam-01", follow_p=0.0)
    assert out.flag_ever and not out.paused
    assert any("did not act" in n for n in out.notes)
    assert len(out.questions) == 4  # asked on to the end of the routine


def test_threshold_zero_checks_everything():
    out = run("syn-legit-09", amount_threshold_jpy=0)  # ¥80,000 routine withdrawal
    assert out.engaged
