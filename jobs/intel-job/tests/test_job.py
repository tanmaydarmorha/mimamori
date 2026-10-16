from __future__ import annotations

import asyncio
import copy
import json
import logging
from datetime import date

import pytest

from intel_job.fetcher import Alert, FetchError, FixtureFetcher
from intel_job.job import PendingWriter, run
from intel_job.schema import model_schema
from intel_job.validate import validate_playbook
from mimamori_common.llm import FakeClient
from mimamori_common.store import InMemoryStore, IntelRepo

from conftest import FAKE_POLICE, handler, recorded


def go(client, repo, fetcher=None):
    return asyncio.run(run(fetcher or FixtureFetcher(), client, repo))


# ---- the happy path -------------------------------------------------------------------------

def test_fixture_alerts_become_valid_pending_playbooks_with_source_dates(client, repo):
    report = go(client, repo)
    assert report.ok and len(report.written) == 3 and not report.rejected
    alerts = {a.url: a for a in FixtureFetcher().fetch()}
    stored = repo.list_playbooks()
    assert {pb["status"] for pb in stored} == {"pending"}
    for pb in stored:
        assert validate_playbook(pb) == []
        assert pb["approved_by"] is None and pb["approved_at"] is None and pb["version"] == 1
        (src,) = pb["sources"]
        assert date.fromisoformat(src["published_at"]) == alerts[src["url"]].published_at  # kept, from the fetcher
    assert sorted(s["published_at"] for pb in stored for s in pb["sources"]) == ["2026-02-10", "2026-03-05", "2026-05-12"]


def test_rerun_is_idempotent(client, repo):
    go(client, repo)
    before = repo.list_playbooks()
    report = go(client, repo)
    assert report.written == [] and len(report.duplicates) == 3
    assert repo.list_playbooks() == before


def test_near_duplicate_from_another_alert_is_skipped(client, repo):
    go(client, repo)
    again = Alert("Other publisher", "https://example.invalid/other", date(2026, 3, 1), "資産を保全する と電話で言われた")
    other = FakeClient(json_handler=lambda *_: {**recorded("police"), "id": "pb.fake_police.other_name"})
    report = go(other, repo, type("F", (), {"fetch": lambda self: [again]})())
    assert report.written == [] and "near-duplicate" in report.duplicates[0][1]


def test_existing_approved_playbook_is_never_overwritten(client, repo):
    approved = {**recorded("police"), "status": "approved", "version": 1, "approved_by": "analyst", "sources": [
        {"publisher": "x", "url": "https://example.invalid/old", "published_at": "2025-01-01"}]}
    repo.put_playbook(approved)
    report = go(client, repo)
    assert any("already exists" in r or "near-duplicate" in r for _, r in report.duplicates)
    assert repo.get_playbook(approved["id"]) == approved


# ---- prompt injection and approval ----------------------------------------------------------

def test_injection_alert_yields_pending_playbook_only(client, repo):
    go(client, repo)
    pb = repo.get_playbook("pb.relative_in_trouble.cheque_pickup")
    assert pb["status"] == "pending" and pb["approved_by"] is None and pb["approved_at"] is None and pb["version"] == 1
    assert repo.list_playbooks("approved") == []


def test_alert_text_is_in_a_data_block_not_the_instructions(client, repo):
    go(client, repo)
    for call in client.calls:
        assert "ignore previous instructions" not in call.system
        assert "<data" in call.user and call.user.rstrip().endswith("</data>")
    injected = next(c for c in client.calls if "ignore previous instructions" in c.user)
    assert injected.user.index("<data") < injected.user.index("ignore previous instructions")
    assert "<data" in injected.system  # the prompt tells the model what the tags mean


def test_model_schema_cannot_express_approval():
    schema = model_schema()
    assert "$ref" not in json.dumps(schema)
    for field in ("status", "sources", "version", "approved_by", "approved_at"):
        assert field not in schema["properties"] and field not in schema["required"]


def test_job_code_cannot_write_approved(client):
    class Spy(InMemoryStore):
        writes: list = []

        def set(self, collection, doc_id, doc):
            Spy.writes.append((collection, doc))
            super().set(collection, doc_id, doc)

        def update(self, collection, doc_id, patch):
            raise AssertionError("the job must not update documents")

    Spy.writes = []
    repo = IntelRepo(Spy())
    go(client, repo)
    assert Spy.writes and all(c == "playbooks" and d["status"] == "pending" for c, d in Spy.writes)

    writer = PendingWriter(repo)
    assert not hasattr(writer, "set_playbook_status") and not hasattr(writer, "_repo_status")
    for bad in ({"status": "approved"}, {"approved_by": "me"}, {"status": "rejected"}):
        with pytest.raises(PermissionError):
            writer.put_pending({**recorded("gold"), "status": "pending", "approved_by": None, "approved_at": None, **bad})


# ---- invalid model output -------------------------------------------------------------------

def _break(fn):
    def h(system, user, schema):
        pb = handler(system, user, schema)
        fn(pb)
        return pb
    return h


BREAKAGES = {
    "bad id prefix": lambda pb: pb.update(id="pb.gold_bullion.x") if pb["hypothesis"] != "gold_bullion" else pb.update(id="pb.fake_police.x"),
    "banned wording": lambda pb: pb["question_bank"]["questions"][0].update(ja="認知機能に問題はありませんか。"),
    "slot mismatch": lambda pb: pb["question_bank"]["questions"][0].update(ja="{payee_name}ですか。", slots=[]),
    "question prefix": lambda pb: pb["question_bank"]["questions"][0].update(id="q.other_scam.x"),
    "missing field": lambda pb: pb.pop("impersonates"),
    "bad enum": lambda pb: pb.update(payment_methods=["bitcoin_atm"]),
    "extra field": lambda pb: pb.update(free_text_notes="hello"),
    "no hypothesis": lambda pb: pb.pop("hypothesis"),
    "legitimate hypothesis": lambda pb: pb.update(hypothesis="legitimate"),
}


@pytest.mark.parametrize("name", BREAKAGES)
def test_invalid_model_output_is_rejected_logged_and_not_stored(name, repo, caplog):
    caplog.set_level(logging.WARNING, logger="intel_job")
    report = go(FakeClient(json_handler=_break(BREAKAGES[name])), repo)
    assert report.written == [] and len(report.rejected) == 3
    assert repo.list_playbooks() == []
    assert sum("rejected model output" in r.message for r in caplog.records) == 3


def test_non_json_model_output_is_an_error_not_stored(repo, caplog):
    caplog.set_level(logging.ERROR, logger="intel_job")
    report = go(FakeClient(json_handler=lambda *_: "I am sorry, here is some prose"), repo)
    assert not report.ok and len(report.errors) == 3 and repo.list_playbooks() == []
    assert "extraction failed" in caplog.text


def test_future_source_date_and_wording_id_collision_rejected(repo):
    pb = {**copy.deepcopy(FAKE_POLICE), "version": 1, "status": "pending", "approved_by": None, "approved_at": None,
          "sources": [{"publisher": "p", "url": "u", "published_at": "2030-01-01"}]}
    assert any("future" in p for p in validate_playbook(pb, today=date(2026, 10, 14)))
    pb["sources"][0]["published_at"] = "2026-01-01"
    assert validate_playbook(pb, today=date(2026, 10, 14)) == []
    assert any("already exists" in p for p in validate_playbook(pb, taken_wording_ids={"q.fake_police.who_asked"}, today=date(2026, 10, 14)))


def test_one_bad_alert_does_not_block_the_others(repo):
    def h(system, user, schema):
        if "金の延べ棒" in user:
            return {"nonsense": True}
        return handler(system, user, schema)
    report = go(FakeClient(json_handler=h), repo)
    assert len(report.written) == 2 and len(report.rejected) == 1


def test_fetch_failure_fails_the_run(client, repo, tmp_path):
    bad = tmp_path / "alerts.json"
    bad.write_text("not json")
    with pytest.raises(FetchError):
        go(client, repo, FixtureFetcher(bad))
    assert repo.list_playbooks() == []
