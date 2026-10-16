import pytest

from mimamori_common.config import Settings
from mimamori_common.models import WatchlistSnapshot
from mimamori_common.store import CaseRepo, InMemoryStore, open_case_repo, open_intel_repo, open_ref_repo


def test_crud_and_filters():
    s = InMemoryStore()
    s.set("c", "a", {"id": "a", "n": 2, "k": "x"})
    s.set("c", "b", {"id": "b", "n": 1, "k": "y"})
    assert s.get("c", "a")["n"] == 2 and s.get("c", "zzz") is None
    assert [d["id"] for d in s.list("c", order_by="n")] == ["b", "a"]
    assert [d["id"] for d in s.list("c", where={"k": "y"})] == ["b"]
    assert s.update("c", "a", {"n": 3})["n"] == 3
    s.delete("c", "a")
    assert s.get("c", "a") is None


def test_documents_are_copied_not_shared():
    s = InMemoryStore()
    doc = {"x": [1]}
    s.set("c", "a", doc)
    doc["x"].append(2)
    s.get("c", "a")["x"].append(3)
    assert s.get("c", "a") == {"x": [1]}


def test_repos_opened_twice_share_data_per_database():
    open_intel_repo().put_playbook({"id": "pb.x.y", "status": "pending"})
    assert open_intel_repo().get_playbook("pb.x.y")["status"] == "pending"
    assert open_case_repo().get_case("nope") is None


def test_active_wishes_picks_latest_active_version():
    repo = open_case_repo()
    repo.put_wishes({"customer_ref": "c1", "version": 1, "status": "superseded"})
    repo.put_wishes({"customer_ref": "c1", "version": 2, "status": "active"})
    repo.put_wishes({"customer_ref": "c2", "version": 1, "status": "active"})
    assert repo.get_active_wishes("c1")["version"] == 2
    assert [w["version"] for w in repo.list_wishes("c1")] == [1, 2]


def test_events_are_sequenced_and_replayable():
    repo = open_case_repo()
    for t in ("case_opened", "card_updated", "decision_logged"):
        repo.append_event("case-1", {"type": t})
    repo.append_event("case-2", {"type": "case_opened"})
    assert [e["seq"] for e in repo.list_events("case-1")] == [1, 2, 3]
    assert [e["type"] for e in repo.list_events("case-1", after_seq=1)] == ["card_updated", "decision_logged"]


def test_audit_is_append_only_in_order():
    repo = open_case_repo()
    repo.append_audit({"case_id": "case-1", "actor": "teller-1", "action": "pause", "why": "wishes", "at": "2026-10-13T11:50:00+09:00"})
    repo.append_audit({"case_id": "case-1", "actor": "teller-1", "action": "police_summary", "why": "officer request", "at": "2026-10-13T11:55:00+09:00"})
    assert [a["action"] for a in repo.list_audit("case-1")] == ["pause", "police_summary"]


def test_playbook_approval_records_who():
    repo = open_intel_repo()
    repo.put_playbook({"id": "pb.a.b", "status": "pending"})
    repo.set_playbook_status("pb.a.b", "approved", "analyst-1", "2026-10-13T00:00:00+09:00")
    assert repo.get_playbook("pb.a.b")["approved_by"] == "analyst-1"
    assert [p["id"] for p in repo.list_playbooks("approved")] == ["pb.a.b"]


def test_watchlist_latest_pointer():
    repo = open_ref_repo()
    assert repo.get_latest_snapshot() is None
    snap = WatchlistSnapshot.model_validate({"snapshot_id": "2026-10-13", "created_at": "2026-10-13T03:00:00+09:00", "sources": [], "entries": [], "content_hash": "abc"})
    repo.put_snapshot(snap)
    assert repo.get_latest_snapshot()["snapshot_id"] == "2026-10-13"


@pytest.mark.parametrize("service", ["conversation-svc", "watchlist-loader", "intel-job", "sim-job", "web-ui", "core-bank-mock"])
def test_case_db_is_closed_to_services_without_a_grant(service):
    with pytest.raises(PermissionError):
        open_case_repo(Settings(service_name=service))


@pytest.mark.parametrize("service", ["scoring", "case-svc"])
def test_case_db_is_open_to_scoring_and_case_svc(service):
    assert isinstance(open_case_repo(Settings(service_name=service)), CaseRepo)
