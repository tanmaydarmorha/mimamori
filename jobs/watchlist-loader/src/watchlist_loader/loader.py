"""Validate, normalise, hash, compare with the last good snapshot, write.

Nothing is written until every check has passed, so a bad run can never replace a good snapshot.
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
import unicodedata
from dataclasses import dataclass
from datetime import datetime

from pydantic import ValidationError

from mimamori_common.models.baseline import WatchlistEntry, WatchlistSnapshot, WatchlistSource
from mimamori_common.store import RefRepo

from .sources import Fetcher, SourceError

log = logging.getLogger("watchlist_loader")

# If the previous snapshot had at least this many entries, a new one smaller than MIN_RETAIN_RATIO of
# it is treated as a broken source (a scraper that lost its selectors), not a real change.
SHRINK_CHECK_MIN_PREVIOUS = 10
MIN_RETAIN_RATIO = 0.5

_WS = re.compile(r"\s+")


def _clean(value):
    if not isinstance(value, str):
        return value
    # NFC + whitespace only: published characters are kept as is. Scoring does its own NFKC matching.
    value = _WS.sub(" ", unicodedata.normalize("NFC", value)).strip()
    return value or None


def normalise_entry(raw: object, list_name: str, where: str) -> WatchlistEntry:
    if not isinstance(raw, dict):
        raise SourceError(f"{where}: entry is not an object")
    cleaned = {k: _clean(v) for k, v in raw.items()}
    cleaned.setdefault("list_name", list_name)
    try:
        entry = WatchlistEntry.model_validate(cleaned)
    except ValidationError as exc:
        raise SourceError(f"{where}: invalid entry: {exc.errors(include_url=False, include_input=False)}") from exc
    if entry.list_name != list_name:
        raise SourceError(f"{where}: entry list_name {entry.list_name!r} does not match its source {list_name!r}")
    if not entry.source_ref:
        raise SourceError(f"{where}: empty source_ref")
    if not (entry.name_ja or entry.name_kana or entry.account_hint):
        raise SourceError(f"{where}: entry has no name or account hint")
    return entry


def content_hash(entries: list[WatchlistEntry]) -> str:
    canonical = json.dumps([e.model_dump(mode="json") for e in entries], ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class Result:
    status: str  # "written" | "unchanged"
    snapshot_id: str
    content_hash: str
    entries: int


def build_snapshot(fetcher: Fetcher, now: datetime, snapshot_id: str) -> WatchlistSnapshot:
    batches = fetcher.fetch()
    if not batches:
        raise SourceError("source returned no lists")
    entries: list[WatchlistEntry] = []
    sources: list[WatchlistSource] = []
    seen_lists: set[str] = set()
    for b in batches:
        if b.list_name in seen_lists:
            raise SourceError(f"list {b.list_name!r} appears twice")
        seen_lists.add(b.list_name)
        batch_entries = [normalise_entry(raw, b.list_name, f"{b.list_name}[{i}]") for i, raw in enumerate(b.entries)]
        try:
            fetched = datetime.fromisoformat(b.fetched_at)
            sources.append(WatchlistSource(list_name=b.list_name, url=b.url, fetched_at=fetched, entries=len(batch_entries)))
        except (ValueError, ValidationError) as exc:
            raise SourceError(f"{b.list_name}: bad source metadata: {exc}") from exc
        entries.extend(batch_entries)
    refs = [(e.list_name, e.source_ref) for e in entries]
    if len(set(refs)) != len(refs):
        dup = next(r for r in refs if refs.count(r) > 1)
        raise SourceError(f"duplicate source_ref {dup}")
    entries.sort(key=lambda e: (e.list_name, e.source_ref))
    sources.sort(key=lambda s: s.list_name)
    return WatchlistSnapshot(snapshot_id=snapshot_id, created_at=now, sources=sources, entries=entries, content_hash=content_hash(entries))


def check_against_previous(new: WatchlistSnapshot, previous: dict | None) -> None:
    if not new.entries:
        raise SourceError("source has zero entries; refusing to write an empty snapshot")
    if previous is None:
        return
    prev_by_list: dict[str, int] = {}
    for e in previous["entries"]:
        prev_by_list[e["list_name"]] = prev_by_list.get(e["list_name"], 0) + 1
    new_by_list = {s.list_name: s.entries for s in new.sources}
    for name, count in prev_by_list.items():
        if count and new_by_list.get(name, 0) == 0:
            raise SourceError(f"list {name!r} had {count} entries in snapshot {previous['snapshot_id']} and now has none")
    prev_total = len(previous["entries"])
    if prev_total >= SHRINK_CHECK_MIN_PREVIOUS and len(new.entries) < prev_total * MIN_RETAIN_RATIO:
        raise SourceError(f"entries fell from {prev_total} to {len(new.entries)} (below {MIN_RETAIN_RATIO:.0%}); treating the source as broken")


def run(fetcher: Fetcher, repo: RefRepo, now: datetime) -> Result:
    previous = repo.get_latest_snapshot()
    snapshot = build_snapshot(fetcher, now, snapshot_id=now.strftime("%Y-%m-%d"))
    if previous is not None and previous.get("content_hash") == snapshot.content_hash:
        log.info("unchanged: %d entries, latest stays %s", len(snapshot.entries), previous["snapshot_id"])
        return Result("unchanged", previous["snapshot_id"], snapshot.content_hash, len(snapshot.entries))
    check_against_previous(snapshot, previous)
    # One dated snapshot per day; a second changed run on the same day gets a time suffix (schema: YYYY-MM-DDTHHMM).
    if repo.store.get("watchlist_snapshots", snapshot.snapshot_id) is not None:
        snapshot = snapshot.model_copy(update={"snapshot_id": now.strftime("%Y-%m-%dT%H%M")})
        if repo.store.get("watchlist_snapshots", snapshot.snapshot_id) is not None:
            raise SourceError(f"snapshot {snapshot.snapshot_id} already exists with different content")
    repo.put_snapshot(snapshot)
    log.info("written: snapshot %s, %d entries, hash %s", snapshot.snapshot_id, len(snapshot.entries), snapshot.content_hash)
    return Result("written", snapshot.snapshot_id, snapshot.content_hash, len(snapshot.entries))
