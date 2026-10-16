from mimamori_common.rules import assess_risk, merge_indicators, verify_quotes

TURNS = {"c1": "リフォーム代なんです", "c2": "警察の人から電話があってね", "c3": "誰にも　言うなって言われてるの"}


def ind(type_, turn, quote):
    return {"type": type_, "turn_id": turn, "quote": quote}


def test_exact_quote_kept():
    kept, dropped = verify_quotes([ind("cover_story", "c1", "リフォーム代")], TURNS)
    assert kept[0]["turn_id"] == "c1" and kept[0]["turn_id_corrected"] is False and not dropped


def test_wrong_turn_id_is_corrected():
    kept, dropped = verify_quotes([ind("impersonated_official", "c3", "警察の人から電話があってね")], TURNS)
    assert kept[0]["turn_id"] == "c2" and kept[0]["turn_id_corrected"] is True and not dropped


def test_normalised_match_across_width_and_whitespace():
    kept, _ = verify_quotes([ind("secrecy_instruction", "c3", "誰にも言うなって言われてるの")], TURNS)
    assert len(kept) == 1 and kept[0]["turn_id"] == "c3"


def test_joined_quote_is_dropped():
    kept, dropped = verify_quotes([ind("cover_story", "c1", "リフォーム代なんです…警察の人から")], TURNS)
    assert not kept and dropped[0]["reason"] == "quote_not_found"


def test_invented_quote_is_dropped():
    _, dropped = verify_quotes([ind("urgency", "c1", "今日中に")], TURNS)
    assert len(dropped) == 1


def test_merge_never_removes_and_dedupes():
    a = {**ind("urgency", "c1", "急いで"), "turn_id_corrected": False}
    b = {**ind("secrecy_instruction", "c2", "言うな"), "turn_id_corrected": False}
    merged = merge_indicators([a], [a, b])
    assert merged == [a, b]
    assert merge_indicators(merged, []) == merged


def risk(types, consistent="unknown", **facts):
    return assess_risk([ind(t, "c1", "x") for t in types], {"consistent_with_history": consistent}, facts)


def test_h1_two_core_groups_is_high():
    r = risk(["impersonated_official", "secrecy_instruction"])
    assert r["level"] == "high" and r["pause_recommended"] and r["fired"] == ["H1:impersonation+secrecy"]


def test_h2_one_core_plus_pressure_plus_cover_mismatch():
    r = risk(["impersonated_official", "urgency"], consistent="no")
    assert r["level"] == "high" and r["fired"][0].startswith("H2:impersonation+pressure+cover_mismatch")


def test_h2_with_risky_counterpart():
    r = risk(["safe_account_transfer", "third_party_pressure"], **{"counterpart_graph.account_age_days": 4})
    assert r["level"] == "high" and "risky_counterpart" in r["fired"][0]


def test_one_core_group_alone_is_elevated():
    r = risk(["impersonated_official"])
    assert r["level"] == "elevated" and not r["pause_recommended"]


def test_cover_mismatch_or_risky_counterpart_alone_is_elevated():
    assert risk([], consistent="no")["level"] == "elevated"
    assert risk([], **{"counterpart_graph.distinct_payers_7d": 5})["level"] == "elevated"
    assert risk([], **{"counterpart_graph.account_age_days": 31, "counterpart_graph.distinct_payers_7d": 4})["level"] == "low"


def test_pressure_alone_is_low():
    assert risk(["urgency", "cover_story"])["level"] == "low"
