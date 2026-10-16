"""Fetcher interface and the sources behind it.

A fetcher returns raw, unvalidated batches (one per published list). Validation and normalisation
happen in `loader`, so every source, fixture or live, goes through the same checks.

Only the fixture / file source exists today. A live HTTP fetcher is deliberately not written: see the
README for the source URLs and the terms of use to check first.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from importlib import resources
from pathlib import Path
from typing import Any, Protocol


class SourceError(Exception):
    """The source is unreadable or malformed. The job fails and the last good snapshot stays."""


@dataclass(frozen=True)
class RawBatch:
    list_name: str
    url: str
    fetched_at: str  # ISO 8601, as reported by the source
    entries: list[Any]  # unvalidated


class Fetcher(Protocol):
    def fetch(self) -> list[RawBatch]: ...


class FileFetcher:
    """Reads a JSON file: {"sources": [{"list_name", "url", "fetched_at", "entries": [...]}]}."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)

    def fetch(self) -> list[RawBatch]:
        try:
            text = self.path.read_text(encoding="utf-8")
        except OSError as exc:
            raise SourceError(f"cannot read source file {self.path}: {exc}") from exc
        return parse_source_document(text, origin=str(self.path))


class FixtureFetcher(FileFetcher):
    """The default local source: fictional entries bundled with the package."""

    def __init__(self) -> None:
        super().__init__(Path(str(resources.files("watchlist_loader").joinpath("fixtures/source.json"))))


def parse_source_document(text: str, origin: str = "source") -> list[RawBatch]:
    try:
        doc = json.loads(text)
    except json.JSONDecodeError as exc:
        raise SourceError(f"{origin}: not valid JSON: {exc}") from exc
    if not isinstance(doc, dict) or not isinstance(doc.get("sources"), list):
        raise SourceError(f"{origin}: expected an object with a 'sources' list")
    batches = []
    for i, src in enumerate(doc["sources"]):
        if not isinstance(src, dict):
            raise SourceError(f"{origin}: sources[{i}] is not an object")
        for key in ("list_name", "url", "fetched_at", "entries"):
            if key not in src:
                raise SourceError(f"{origin}: sources[{i}] is missing '{key}'")
        if not isinstance(src["entries"], list):
            raise SourceError(f"{origin}: sources[{i}].entries is not a list")
        batches.append(RawBatch(str(src["list_name"]), str(src["url"]), str(src["fetched_at"]), src["entries"]))
    return batches


def make_fetcher(kind: str, path: str | None = None) -> Fetcher:
    if kind == "fixture":
        return FileFetcher(path) if path else FixtureFetcher()
    if kind == "file":
        if not path:
            raise SourceError("WATCHLIST_SOURCE=file needs WATCHLIST_SOURCE_PATH")
        return FileFetcher(path)
    raise SourceError(f"unknown WATCHLIST_SOURCE {kind!r} (fixture | file); no live fetcher is built in")
