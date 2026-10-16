import copy
from datetime import date

import pytest
from mimamori_common.models import Playbook
from mimamori_common.schemas import load_example

from sim_job.heldout import (
    CutoffViolation, assert_cases_after_cutoff, assert_playbooks_before_cutoff, load_heldout, to_scenarios,
)
from sim_job.params import T

T_ = date(2026, 4, 1)


def playbooks():
    return load_example("playbooks.json")


def test_t_is_the_decided_date():
    assert T == T_


def test_heldout_cases_are_all_published_on_or_after_T_and_counted_honestly():
    hs = load_heldout()
    assert all(date.fromisoformat(c["published_at"]) >= T_ for c in hs.cases)
    assert len(hs.cases) == 11 and len(hs.runnable) == 9  # what research.md R2 holds; the target of 20 is NOT met
    assert hs.target_cases == 20 and len(hs.cases) < hs.target_cases
    for c in hs.cases:
        assert c["source_url"].startswith("https://")
        if not c["runnable"]:
            assert c["not_runnable_reason"]
        else:
            assert c["assumptions"], f"{c['id']}: a replay without stated assumptions"


def test_case_before_T_is_rejected():
    hs = load_heldout()
    bad = copy.deepcopy(hs.cases)
    bad[0]["published_at"] = "2026-03-31"
    with pytest.raises(CutoffViolation, match="HO-01"):
        assert_cases_after_cutoff(bad, T_)


def test_seeded_approved_playbooks_pass_the_date_split_as_validated_models():
    rows = assert_playbooks_before_cutoff([Playbook.model_validate(p) for p in playbooks()], T_, load_heldout())
    assert {r["id"] for r in rows} >= {"pb.fake_police.safe_account"}
    assert all(r["latest_source_published_at"] < "2026-04-01" for r in rows)


@pytest.mark.parametrize("published", ["2026-04-01", "2026-09-30"])
def test_playbook_source_on_or_after_T_is_rejected(published):
    pbs = playbooks()
    pbs[0]["sources"][0]["published_at"] = published
    with pytest.raises(CutoffViolation, match="not before T"):
        assert_playbooks_before_cutoff(pbs, T_)


def test_playbook_without_published_at_or_sources_is_rejected():
    pbs = playbooks()
    pbs[0]["sources"][0]["published_at"] = None
    with pytest.raises(CutoffViolation, match="published_at"):
        assert_playbooks_before_cutoff(pbs, T_)
    pbs = playbooks()
    pbs[0]["sources"] = []
    with pytest.raises(CutoffViolation, match="no sources"):
        assert_playbooks_before_cutoff(pbs, T_)


def test_playbook_citing_a_held_out_source_is_rejected_leakage():
    hs = load_heldout()
    pbs = playbooks()
    pbs[0]["sources"].append({"publisher": "x", "url": hs.cases[0]["source_url"], "published_at": "2025-01-01"})
    with pytest.raises(CutoffViolation, match="held-out source"):
        assert_playbooks_before_cutoff(pbs, T_, hs)


def test_first_seen_after_T_is_rejected():
    pbs = playbooks()
    pbs[0]["first_seen"] = "2026-06-01"
    with pytest.raises(CutoffViolation, match="first_seen"):
        assert_playbooks_before_cutoff(pbs, T_)


def test_three_variants_per_runnable_case_all_scam_with_flagged_source_facts():
    hs = load_heldout()
    sc = to_scenarios(hs)
    assert len(sc) == 27 and {s.ground_truth for s in sc} == {"scam"}
    assert {s.source["variant"] for s in sc} == {"candid", "coached", "coached-papers"}
    papers = next(s for s in sc if s.id == "HO-01-coached-papers")
    later = next(s for s in sc if s.id == "HO-01-coached")
    assert papers.persona.replies["verify_purpose"] != later.persona.replies["verify_purpose"]
    ho06 = next(s for s in sc if s.id == "HO-06-candid")
    assert ho06.kind == "cash_withdrawal" and ho06.amount_jpy == 2_370_000 and ho06.payee is None
    ho07 = next(s for s in sc if s.id == "HO-07-coached")
    assert ho07.kind == "transfer" and ho07.amount_jpy == 23_270_000 and ho07.payee.relation == "other_bank"
    # the candid victim of a case whose source records secrecy says so; where it does not, there is no such line
    ho03 = next(s for s in sc if s.id == "HO-03-candid")
    ho04 = next(s for s in sc if s.id == "HO-04-candid")
    assert any("言ってはいけない" in x for x in ho03.persona.replies["check_contact"])
    assert not any("言ってはいけない" in x for x in ho04.persona.replies["check_contact"])
    assert "逮捕" in ho04.persona.replies["check_instructions"][0]  # HO-04: arrest warrant is recorded
