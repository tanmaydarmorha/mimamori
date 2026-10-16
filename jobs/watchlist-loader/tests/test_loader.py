import copy
import hashlib
import json
import subprocess
import sys
from datetime import datetime, timedelta, timezone

import pytest

from mimamori_common.models.baseline import WatchlistSnapshot
from mimamori_common.store import InMemoryStore, RefRepo, reset_memory_stores

from watchlist_loader.cli import main
from watchlist_loader.loader import run
from watchlist_loader.sources import FileFetcher, FixtureFetcher, SourceError

JST = timezone(timedelta(hours=9))
T1 = datetime(2026, 10, 14, 3, 0, tzinfo=JST)


@pytest.fixture(autouse=True)
def _clean():
    reset_memory_stores()
    yield
    reset_memory_stores()


@pytest.fixture
def repo():
    return RefRepo(InMemoryStore())


@pytest.fixture
def source_doc():
    return json.loads(FixtureFetcher().path.read_text(encoding="utf-8"))


def write_source(tmp_path, doc, name="source.json"):
    p = tmp_path / name
    p.write_text(doc if isinstance(doc, str) else json.dumps(doc, ensure_ascii=False), encoding="utf-8")
    return FileFetcher(p)


def many_entries(n, list_name="dicj_frozen_accounts"):
    return [{"list_name": list_name, "name_ja": f"（架空）テスト{i}", "notice_date": "2026-09-01", "source_ref": f"syn-{i:03d}"} for i in range(n)]


def doc_with(entries_by_list):
    return {"sources": [{"list_name": k, "url": "https://example.invalid/" + k, "fetched_at": "2026-10-14T03:00:00+09:00", "entries": v} for k, v in entries_by_list.items()]}


def test_fixture_run_writes_valid_snapshot(repo):
    res = run(FixtureFetcher(), repo, T1)
    assert res.status == "written" and res.snapshot_id == "2026-10-14"
    snap = repo.get_latest_snapshot()
    parsed = WatchlistSnapshot.model_validate(snap)
    assert len(parsed.entries) == 4 and {s.list_name for s in parsed.sources} == {"dicj_frozen_accounts", "fsa_unregistered_firms"}
    expected = hashlib.sha256(json.dumps([e.model_dump(mode="json") for e in parsed.entries], ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    assert parsed.content_hash == expected
    assert repo.latest_pointer()["snapshot_id"] == "2026-10-14"


def test_rerun_unchanged_is_idempotent(repo):
    run(FixtureFetcher(), repo, T1)
    pointer = repo.latest_pointer()
    res = run(FixtureFetcher(), repo, T1 + timedelta(days=1))
    assert res.status == "unchanged" and res.snapshot_id == "2026-10-14"
    assert repo.latest_pointer() == pointer
    assert len(repo.store.list("watchlist_snapshots")) == 1


def test_formatting_noise_does_not_change_hash(repo, tmp_path, source_doc):
    run(FixtureFetcher(), repo, T1)
    noisy = copy.deepcopy(source_doc)
    noisy["sources"].reverse()
    noisy["sources"][0]["entries"].reverse()
    noisy["sources"][0]["entries"][0]["name_ja"] = "  " + noisy["sources"][0]["entries"][0]["name_ja"].replace("（", " （") + " "
    assert run(write_source(tmp_path, noisy), repo, T1 + timedelta(days=1)).status == "unchanged"


def test_changed_source_writes_new_snapshot_and_moves_latest(repo, tmp_path, source_doc):
    run(FixtureFetcher(), repo, T1)
    changed = copy.deepcopy(source_doc)
    changed["sources"][0]["entries"].append({"list_name": "dicj_frozen_accounts", "name_ja": "（架空）新規口座", "notice_date": "2026-10-13", "source_ref": "synthetic-dicj-003"})
    res = run(write_source(tmp_path, changed), repo, T1 + timedelta(days=1))
    assert res.status == "written" and res.snapshot_id == "2026-10-15"
    assert repo.latest_pointer()["snapshot_id"] == "2026-10-15"
    assert len(repo.get_latest_snapshot()["entries"]) == 5
    assert repo.store.get("watchlist_snapshots", "2026-10-14") is not None  # history kept


def test_second_change_same_day_gets_time_suffix(repo, tmp_path, source_doc):
    run(FixtureFetcher(), repo, T1)
    changed = copy.deepcopy(source_doc)
    changed["sources"][1]["entries"].pop()
    res = run(write_source(tmp_path, changed), repo, T1 + timedelta(hours=6))
    assert res.snapshot_id == "2026-10-14T0900"
    assert repo.latest_pointer()["snapshot_id"] == "2026-10-14T0900"
    assert repo.store.get("watchlist_snapshots", "2026-10-14") is not None


def assert_rejected_and_untouched(repo, fetcher, now=T1 + timedelta(days=1)):
    before = (repo.latest_pointer(), repo.get_latest_snapshot())
    with pytest.raises(SourceError):
        run(fetcher, repo, now)
    assert (repo.latest_pointer(), repo.get_latest_snapshot()) == before


def test_bad_json_fails_and_keeps_last_good(repo, tmp_path):
    run(FixtureFetcher(), repo, T1)
    assert_rejected_and_untouched(repo, write_source(tmp_path, "{not json"))


def test_missing_file_fails(repo, tmp_path):
    run(FixtureFetcher(), repo, T1)
    assert_rejected_and_untouched(repo, FileFetcher(tmp_path / "nope.json"))


@pytest.mark.parametrize("mutate", [
    lambda d: d.update(sources="x"),
    lambda d: d["sources"][0].pop("url"),
    lambda d: d["sources"][0].update(entries="x"),
    lambda d: d["sources"][0]["entries"][0].pop("source_ref"),
    lambda d: d["sources"][0]["entries"][0].pop("notice_date"),
    lambda d: d["sources"][0]["entries"][0].update(notice_date="not-a-date"),
    lambda d: d["sources"][0]["entries"][0].update(unexpected="field"),
    lambda d: d["sources"][0]["entries"][0].update(list_name="fsa_unregistered_firms"),
    lambda d: d["sources"][0]["entries"][0].update(list_name="made_up_list"),
    lambda d: d["sources"][0]["entries"].append("string"),
    lambda d: d["sources"][0]["entries"].append({"list_name": "dicj_frozen_accounts", "notice_date": "2026-01-01", "source_ref": "x"}),
    lambda d: d["sources"][0]["entries"].append(dict(d["sources"][0]["entries"][0])),
    lambda d: d["sources"][0].update(fetched_at="yesterday"),
    lambda d: d["sources"].append(copy.deepcopy(d["sources"][0])),
], ids=["sources-not-list", "no-url", "entries-not-list", "no-source-ref", "no-notice-date", "bad-date", "extra-field",
        "list-mismatch", "unknown-list", "entry-not-object", "entry-without-name", "duplicate-ref", "bad-fetched-at", "duplicate-list"])
def test_malformed_source_rejected(repo, tmp_path, source_doc, mutate):
    run(FixtureFetcher(), repo, T1)
    bad = copy.deepcopy(source_doc)
    mutate(bad)
    assert_rejected_and_untouched(repo, write_source(tmp_path, bad))


def test_zero_entries_after_many_is_rejected(repo, tmp_path):
    run(write_source(tmp_path, doc_with({"dicj_frozen_accounts": many_entries(30), "fsa_unregistered_firms": many_entries(5, "fsa_unregistered_firms")}), "a.json"), repo, T1)
    assert_rejected_and_untouched(repo, write_source(tmp_path, doc_with({"dicj_frozen_accounts": [], "fsa_unregistered_firms": []}), "b.json"))


def test_zero_entries_on_first_run_is_rejected(repo, tmp_path):
    with pytest.raises(SourceError):
        run(write_source(tmp_path, doc_with({"dicj_frozen_accounts": []})), repo, T1)
    assert repo.latest_pointer() is None


def test_one_list_going_empty_is_rejected(repo, tmp_path):
    run(FixtureFetcher(), repo, T1)
    assert_rejected_and_untouched(repo, write_source(tmp_path, doc_with({"dicj_frozen_accounts": many_entries(3), "fsa_unregistered_firms": []})))


def test_large_shrink_is_rejected_but_small_change_is_not(repo, tmp_path):
    run(write_source(tmp_path, doc_with({"dicj_frozen_accounts": many_entries(40)}), "a.json"), repo, T1)
    assert_rejected_and_untouched(repo, write_source(tmp_path, doc_with({"dicj_frozen_accounts": many_entries(10)}), "b.json"))
    assert run(write_source(tmp_path, doc_with({"dicj_frozen_accounts": many_entries(35)}), "c.json"), repo, T1 + timedelta(days=2)).status == "written"


def test_cli_exit_codes(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("MIMAMORI_SERVICE", "watchlist-loader")
    monkeypatch.setenv("MIMAMORI_DEMO_NOW", "2026-10-14T03:00:00+09:00")
    monkeypatch.delenv("WATCHLIST_SOURCE", raising=False)
    assert main() == 0
    assert "written snapshot=2026-10-14" in capsys.readouterr().out
    assert main() == 0
    assert "unchanged" in capsys.readouterr().out
    bad = tmp_path / "bad.json"
    bad.write_text("{oops")
    monkeypatch.setenv("WATCHLIST_SOURCE_PATH", str(bad))
    assert main() == 1
    monkeypatch.setenv("WATCHLIST_SOURCE", "live")
    assert main() == 1  # no live fetcher is built in
    monkeypatch.setenv("WATCHLIST_SOURCE", "fixture")
    monkeypatch.setenv("MIMAMORI_STORE", "bogus")
    assert main() == 2


def test_python_dash_m_exits_zero():
    r = subprocess.run([sys.executable, "-m", "watchlist_loader"], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr + r.stdout
    assert "written snapshot=" in r.stdout


def test_never_opens_case_db():
    import watchlist_loader.cli, watchlist_loader.loader, watchlist_loader.sources  # noqa: E401
    import inspect
    for mod in (watchlist_loader.cli, watchlist_loader.loader, watchlist_loader.sources):
        assert "case_repo" not in inspect.getsource(mod) and "case-db" not in inspect.getsource(mod)
