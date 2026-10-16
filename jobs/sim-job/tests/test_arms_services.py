import asyncio

import httpx
import pytest

from sim_job.arm_bc import ServiceArms
from sim_job.clients import CaseSvcClient, CoreBankClient, ServiceError
from sim_job.fakes import FakeWorld, make_clients
from sim_job.params import SimParams
from sim_job.personas import QuestionIndex, ScriptedRolePlayer
from sim_job.runner import run_scenarios, summarize
from sim_job.scenarios import by_id, synthetic_scenarios

SC = by_id(synthetic_scenarios())
IDX = QuestionIndex.load()


def setup(params=None, **world_kw):
    world = FakeWorld(**world_kw)
    core, case = make_clients(world)
    return world, ServiceArms(core, case, IDX, params or SimParams())


def run(arms, sid):
    return asyncio.run(arms.run(SC[sid], ScriptedRolePlayer()))


def test_hero_alert_gives_b_a_pause_at_alert_and_c_a_pause_after_questions_with_wishes_basis():
    world, arms = setup()
    b, c = run(arms, "syn-scam-01")
    assert b.scoring == "alert" and b.paused and b.paused_at_turn == 0
    assert c.paused and c.paused_at_turn >= 1 and c.risk_level == "high" and c.case_id
    dec = world.cases[c.case_id]["decisions"]
    assert [d["action"] for d in dec] == ["pause"]
    assert dec[0]["basis"] == "advance_wishes"  # Tanaka has wishes
    assert dec[0]["decided_by"] == "sim-teller" and dec[0]["rationale"]
    assert c.hold_line_ja and "お待ちいただけますでしょうか" in c.hold_line_ja
    assert c.signals  # the signals Scoring sent are recorded for the report


def test_bank_policy_basis_without_wishes():
    world, arms = setup()
    _, c = run(arms, "syn-scam-05")
    assert world.cases[c.case_id]["decisions"][0]["basis"] == "bank_policy"


def test_legitimate_alerted_transfer_is_cleared_by_the_teller_not_paused():
    world, arms = setup()
    b, c = run(arms, "syn-legit-03")
    assert b.paused  # statistics alone stops it (the fake's blunt rule)
    assert not c.paused and c.flag_ever is False
    d = world.cases[c.case_id]["decisions"]
    assert d[0]["action"] == "release" and d[0]["release_reason"] == "cleared_by_teller"


def test_scoring_unavailable_means_neither_arm_engages_and_case_svc_is_never_called():
    world, arms = setup(unavailable=True)
    b, c = run(arms, "syn-scam-01")
    assert b.scoring == c.scoring == "unavailable"
    assert not b.engaged and not c.engaged and not b.paused and not c.paused
    assert not [r for r in world.requests if r[0] == "case"]


def test_no_alert_means_no_case_so_mimamori_is_as_silent_as_statistics():
    world, arms = setup()
    b, c = run(arms, "syn-legit-09")  # ¥80,000
    assert b.scoring == "allow" and not c.engaged and c.case_id is None and not world.cases


def test_teller_ignoring_a_flag_releases_and_says_so():
    world, arms = setup(SimParams(follow_p=0.0))
    b, c = run(arms, "syn-scam-01")
    assert b.flag_ever and not b.paused
    assert c.flag_ever and not c.paused
    assert world.cases[c.case_id]["decisions"][0]["action"] == "release"
    assert "not acted on by the teller" in world.cases[c.case_id]["decisions"][0]["rationale"]
    assert len(c.questions) == SimParams().max_turns or c.questions  # kept asking after the flag


def test_the_teller_only_reads_approved_questions_and_the_opening_is_shared():
    world, arms = setup()
    _, c = run(arms, "syn-scam-03")
    approved = {q["ja"] for q in world._bank.values()}
    teller_turns = [t["text"] for t in world.cases[c.case_id]["turns"] if t["speaker"] == "teller"]
    assert teller_turns and set(teller_turns) <= approved
    assert c.questions[0]["id"] == "q.general.purpose"
    assert len(c.questions) <= SimParams().max_turns


def test_same_teller_draw_in_every_arm():
    params = SimParams(follow_p=0.5)
    world, arms = setup(params)
    results = asyncio.run(run_scenarios(list(SC.values()), params, IDX, arms, ScriptedRolePlayer(), None))
    seen = 0
    for r in results:
        a, b, c = (r.arms[k] for k in ("a_counter_check", "b_statistics", "c_mimamori"))
        acts = params.teller_acts(r.scenario.id)
        for o in (a, b, c):
            if o is not None and o.flag_ever:
                seen += 1
                assert o.paused == acts, (r.scenario.id, o.arm)
    assert seen > 20


def test_case_service_failure_is_recorded_on_arm_c_and_arm_b_still_decides():
    world = FakeWorld()
    core, _ = make_clients(world)
    down = CaseSvcClient("http://case.down", transport=httpx.MockTransport(lambda req: httpx.Response(503, text="down")))
    arms = ServiceArms(core, down, IDX, SimParams())
    b, c = run(arms, "syn-scam-05")
    assert b.paused and not b.error
    assert c.error and "503" in c.error and not c.paused
    assert summarize([type("R", (), {"scenario": SC["syn-scam-05"], "arms": {"c_mimamori": c}, "judgements": []})()],
                     "c_mimamori").errors == 1


def test_core_bank_failure_is_an_error_not_a_pass():
    core = CoreBankClient("http://core.down", transport=httpx.MockTransport(lambda req: httpx.Response(500, text="boom")))
    _, case = make_clients(FakeWorld())
    b, c = run(ServiceArms(core, case, IDX, SimParams()), "syn-scam-01")
    assert b.error and c.error and not b.engaged and not c.engaged


def test_clients_validate_responses_against_the_shared_models():
    world = FakeWorld()
    core, case = make_clients(world)
    bad = httpx.MockTransport(lambda req: httpx.Response(200, json={"transfer_id": "x"}))
    with pytest.raises(Exception):
        asyncio.run(CoreBankClient("http://x", transport=bad).post_transfer(SC["syn-scam-01"].transfer_body("t")))
    with pytest.raises(ServiceError):
        asyncio.run(case.get_case("case-nope"))
