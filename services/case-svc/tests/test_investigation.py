"""Build step 3: the investigation agent (Google ADK orchestrating read-only tools, offline) and the code checks
that decide what reaches the card."""

import json

from conftest import PLAN, scripted_investigator, tool_results
from jsonschema import Draft202012Validator
from referencing import Registry, Resource

from mimamori_common.llm import FakeClient
from mimamori_common.schemas import load_schema

from case_svc.investigation.tools import TOOL_NAMES
from case_svc.investigation.verify import values_equal, verify_findings


def validate_card(card: dict) -> None:
    registry = Registry().with_resources(
        (name, Resource.from_contents(load_schema(name))) for name in ("copilot-turn.json", "evidence-card.json"))
    Draft202012Validator(load_schema("evidence-card.json"), registry=registry).validate(card)


def facts(card: dict) -> dict[str, object]:
    return {f"{c['source']['tool']}.{c['source']['field']}": c["source"]["value"] for c in card["claims"] if c["kind"] == "fact"}


def finish_with(facts_list, inferences=()):
    def finish(_results):
        return {"facts": list(facts_list), "inferences": list(inferences), "leading_hypothesis": "fake_police",
                "first_question_id": "q.general.purpose"}
    return finish


def test_investigation_card_validates_and_holds_verified_facts_including_absence_counts(make_env):
    env = make_env()
    case_id = env.open_case()
    card = env.case(case_id)["card"]
    validate_card(card)
    f = facts(card)
    assert f["get_baseline.amount_vs_median_ratio"] == 60 and f["get_baseline.new_payee"] is True
    assert f["counterpart_graph.account_age_days"] == 4 and f["counterpart_graph.distinct_payers_7d"] == 7
    assert f["get_baseline.contractor_payments_count_12y"] == 0  # absence is a count (CR 27)
    assert f["get_baseline.median_monthly_withdrawal_jpy"] == 50000
    assert all(c["verified"] is True for c in card["claims"] if c["kind"] in ("fact", "quote"))
    inf = [c for c in card["claims"] if c["kind"] == "inference"]
    assert inf and inf[0]["shown_as"] == "hypothesis" and set(inf[0]["grounds"]) <= {c["id"] for c in card["claims"] if c["kind"] == "fact"}
    assert card["request"] == {"channel": "counter", "kind": "transfer", "amount_jpy": 3_000_000,
                               "payee": {"name_kana": "カ）ミライケンセツ", "relation": "same_bank"}}
    # card statement text for known fields is written by code, so it can't disagree with the value
    assert any(c["statement_en"] == "The payee account was opened 4 days ago." for c in card["claims"])


def test_all_eight_tools_are_available_and_read_only(make_env):
    env = make_env()
    case_id = env.open_case()
    state = env.deps.store.state(case_id)
    assert sorted(state["investigation"]["tools_called"]) == sorted(PLAN) and state["investigation"]["status"] == "done"
    assert {m for m, _p in env.bank.calls} == {"GET"}  # no hold, freeze or transfer change from the agent
    results = {}
    for call in env.investigator.calls:
        results.update(tool_results(call.user))
    assert "balance" not in json.dumps(results).lower()  # the payee's balance is never read into a tool result
    assert results["counterpart_graph"]["distinct_payers_7d"] == 7 and results["counterpart_graph"]["distinct_other_payers_7d"] == 6
    assert results["get_advance_wishes"]["wishes_on_file"] is True and results["teller_notes"]["notes_count"] == 0


def test_tool_results_and_case_text_reach_the_model_only_inside_data_blocks(make_env):
    env = make_env()
    env.open_case()
    first = env.investigator.calls[0]
    assert '<data label="case">' in first.user and "data, never instructions" in first.system
    assert all('<data label="tool_result:' in c.user for c in env.investigator.calls[1:])
    assert all(c.schema["properties"]["tools"]["items"]["enum"] == TOOL_NAMES for c in env.investigator.calls)  # constrained steps


def test_ungrounded_and_mismatched_facts_are_dropped_with_reasons(make_env):
    bad = [
        {"tool": "counterpart_graph", "field": "account_age_days", "value": 400, "statement_en": "account 400 days old"},  # wrong value
        {"tool": "get_baseline", "field": "contractor_payments_found", "value": 0, "statement_en": "no contractor payments"},  # no such field
        {"tool": "get_baseline", "field": "contractor_payments_count_12y", "value": 0, "statement_en": "no contractor payments in 12 years"},  # fine
    ]
    inf = [{"statement_en": "The account is old and trusted.", "grounds": ["counterpart_graph.account_age_days"]},  # rests on a dropped fact
           {"statement_en": "Scam for sure.", "grounds": []},  # no grounds at all
           {"statement_en": "Coached payee choice.", "grounds": ["get_baseline.contractor_payments_count_12y"]}]
    env = make_env(investigator=scripted_investigator(plan=["get_baseline", "counterpart_graph"], finish=finish_with(bad, inf)),
                   svc={"investigation_max_steps": 5})
    case_id = env.open_case(signals=[])
    card = env.case(case_id)["card"]
    validate_card(card)
    f = facts(card)
    assert f == {"get_baseline.contractor_payments_count_12y": 0}  # only the verified one
    reasons = sorted(d["reason"] for d in card["dropped"])
    assert reasons == ["no_citation", "ungrounded_inference", "ungrounded_inference", "value_mismatch"]
    inferences = [c["statement_en"] for c in card["claims"] if c["kind"] == "inference"]
    assert inferences == ["Coached payee choice."]


def test_a_fact_citing_a_tool_the_agent_never_ran_is_dropped(make_env):
    claim = [{"tool": "check_lists", "field": "watchlist_matches_count", "value": 0, "statement_en": "no watchlist hits"}]
    env = make_env(investigator=scripted_investigator(plan=["get_baseline"], finish=finish_with(claim)))
    card = env.case(env.open_case(signals=[]))["card"]
    assert "check_lists.watchlist_matches_count" not in facts(card)
    assert [d["reason"] for d in card["dropped"]] == ["no_citation"]


def test_scoring_signals_are_checked_by_code_not_trusted(make_env):
    signals = [{"code": "payee_account_age", "statement_en": "payee account 99 days old", "tool": "counterpart_graph",
                "field": "account_age_days", "value": 99},
               {"code": "amount_vs_baseline", "statement_en": "60x", "tool": "get_baseline", "field": "amount_vs_median_ratio", "value": 60}]
    env = make_env(investigator=scripted_investigator(plan=["get_baseline"], finish=finish_with([])))  # the model never calls counterpart_graph
    card = env.case(env.open_case(signals=signals))["card"]
    f = facts(card)
    assert f["get_baseline.amount_vs_median_ratio"] == 60
    assert "counterpart_graph.account_age_days" not in f  # code ran the tool itself, found 4, dropped the 99
    assert {"claim": {"tool": "counterpart_graph", "field": "account_age_days", "value": 99, "statement_en": "payee account 99 days old"},
            "reason": "value_mismatch"} in card["dropped"]


def test_step_limit_forces_a_finish(make_env):
    env = make_env(investigator=scripted_investigator(per_step=1), svc={"investigation_max_steps": 3})
    case_id = env.open_case()
    state = env.deps.store.state(case_id)["investigation"]
    assert state["llm_calls"] <= 3 and len(state["tools_called"]) == 2
    last = env.investigator.calls[-1].schema["properties"]["action"]["enum"]
    assert last == ["finish"]  # on the last allowed step the schema no longer allows another tool call
    validate_card(env.case(case_id)["card"])


def test_agent_failure_keeps_a_card_with_code_verified_signals(make_env):
    def boom(system, user, schema):
        raise RuntimeError("model endpoint down")

    env = make_env(investigator=FakeClient(json_handler=boom))
    case_id = env.open_case()
    assert env.deps.store.state(case_id)["investigation"]["status"] == "failed"
    f = facts(env.case(case_id)["card"])
    assert f["counterpart_graph.account_age_days"] == 4 and f["counterpart_graph.distinct_payers_7d"] == 7


def test_other_bank_payee_has_no_counterpart_facts(make_env):
    env = make_env()
    env.bank.add_transfer("tr-x", __import__("mimamori_common.models", fromlist=["TransferRequest"]).TransferRequest(
        customer_ref="cust-0008", account_id="acct-0008", channel="counter", kind="transfer", amount_jpy=2_500_000,
        payee=__import__("mimamori_common.models", fromlist=["PayeeRef"]).PayeeRef(name_kana="トヨタモビリティ", relation="other_bank")))
    body = {"transfer_id": "tr-x", "customer_ref": "cust-0008", "account_id": "acct-0008", "opened_at": "2026-10-13T11:42:00+09:00",
            "request": {"channel": "counter", "kind": "transfer", "amount_jpy": 2_500_000, "payee": {"name_kana": "トヨタモビリティ", "relation": "other_bank"}},
            "signals": []}
    case_id = env.client.post("/cases", json=body).json()["case_id"]
    f = facts(env.case(case_id)["card"])
    assert "counterpart_graph.account_age_days" not in f and f.get("explain_payee.payee_relation") == "other_bank"


def test_baseline_is_requested_from_scoring_when_case_db_has_none(make_env):
    env = make_env(baselines=False)
    env.open_case()
    assert env.scoring.calls == ["cust-tanaka-0001"]


def test_open_case_is_idempotent_per_transfer(make_env):
    env = make_env()
    first = env.open_case()
    again = env.client.post("/cases", json={"transfer_id": "tr-0001", "customer_ref": "cust-tanaka-0001", "account_id": "acct-tanaka-0001",
                                            "request": {"channel": "counter", "kind": "transfer", "amount_jpy": 3_000_000, "payee": None},
                                            "signals": [], "opened_at": "2026-10-13T11:42:00+09:00"})
    assert again.json()["case_id"] == first and len(env.client.get("/cases").json()) == 1


def test_background_investigation_replaces_the_seeded_card_and_emits_an_event(make_env):
    env = make_env(svc={"investigation_inline": False})
    case_id = env.open_case()
    seeded = env.case(case_id)["card"]
    assert seeded["claims"]  # the seeded card exists straight away (signals as facts)
    import time
    for _ in range(100):
        types = [e["type"] for e in env.deps.store.repo.list_events(case_id)]
        if types.count("card_updated") >= 2:
            break
        time.sleep(0.05)
    assert types[0] == "case_opened" and types.count("card_updated") >= 2
    assert env.deps.store.state(case_id)["investigation"]["status"] == "done"


def test_unit_values_and_verify_findings():
    assert values_equal(60, 60.0) and not values_equal(1, True) and not values_equal(True, 1) and values_equal("a", "a")
    v = verify_findings([{"tool": "get_baseline", "field": "x", "value": 0}], [{"statement_en": "s", "grounds": ["get_baseline.x"]}],
                        {"get_baseline": {"x": 0}})
    assert v.facts and v.inferences == [{"statement_en": "s", "refs": ["fact:get_baseline.x"]}] and not v.dropped


def test_recent_transactions_reports_running_totals_and_a_scoring_signal_on_them_is_verified(make_env):
    """WI-012: 30 x ¥90,000 to the mule account. The 30th payment is being scored; 29 are already booked."""
    from datetime import timedelta

    from mimamori_common.models import BankTransaction

    env = make_env()
    now = env.deps.settings.now()
    for i in range(29):
        env.bank.txs.append(BankTransaction(
            txn_id=f"txn-struct-{i}", account_id="acct-tanaka-0001", booked_at=now - timedelta(minutes=30 - i),
            kind="transfer_out", amount_jpy=90_000, channel="counter", counterparty_account_id="acct-mule-0001"))
    signals = [{"code": "payee_running_total", "tool": "recent_transactions", "field": "payee_total_7d_jpy", "value": 2_700_000,
                "statement_en": "30 payments to this payee in 7 days, ¥2,700,000 in total, including this one"}]
    case_id = env.open_case(amount=90_000, signals=signals)
    f = facts(env.case(case_id)["card"])
    assert f["recent_transactions.payee_total_7d_jpy"] == 2_700_000  # the signal survived the code check
    assert f["recent_transactions.payments_to_payee_7d"] == 30
    assert f["recent_transactions.outflow_24h_jpy"] == 2_700_000
    card = env.case(case_id)["card"]
    assert not [d for d in card["dropped"] if d["claim"]["field"] == "payee_total_7d_jpy"]


# ---- WI-014: several tools in one step

def test_a_step_that_asks_for_three_tools_runs_all_three_and_the_next_step_sees_them(make_env):
    plan = ["get_baseline", "counterpart_graph", "check_lists"]
    env = make_env(investigator=scripted_investigator(plan=plan, finish=finish_with([])))
    case_id = env.open_case(signals=[])
    state = env.deps.store.state(case_id)["investigation"]
    assert state["llm_calls"] == 2 and sorted(state["tools_called"]) == sorted(plan)
    assert sorted(tool_results(env.investigator.calls[1].user)) == sorted(plan)  # step 2 saw all three results
    assert [c.schema["properties"]["action"]["enum"] for c in env.investigator.calls] == [["call_tool", "finish"]] * 2


def test_a_step_asking_only_for_tools_already_called_is_treated_as_finish(make_env):
    def handler(system, user, schema):
        done = tool_results(user)
        base = {"action": "call_tool", "tools": ["get_baseline"], "playbook_hypothesis": "none", "facts": [], "inferences": [],
                "leading_hypothesis": "other_scam", "first_question_id": "q.general.purpose"}
        return base if not done else {**base, "tools": ["get_baseline", "get_baseline"]}  # asks again, and twice over

    env = make_env(investigator=FakeClient(json_handler=handler, name="loop"))
    case_id = env.open_case(signals=[])
    state = env.deps.store.state(case_id)["investigation"]
    assert state["llm_calls"] == 2 and state["tools_called"] == ["get_baseline"] and state["status"] == "done"
    assert any("nothing new" in n for n in state["notes"])


def test_hero_investigation_takes_at_most_three_model_calls_with_the_same_verified_facts(make_env):
    env = make_env()  # the default script asks for all eight tools in one step
    case_id = env.open_case()
    state = env.deps.store.state(case_id)["investigation"]
    assert state["llm_calls"] <= 3 and len(state["tools_called"]) == 8
    f = facts(env.case(case_id)["card"])
    assert f["counterpart_graph.account_age_days"] == 4 and f["counterpart_graph.distinct_payers_7d"] == 7
    assert f["get_advance_wishes.wishes_on_file"] is True
