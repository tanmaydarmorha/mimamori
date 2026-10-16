"""Where alerts come from. The job only sees the `AlertFetcher` interface; the default (and the only
one tests and CI use) reads a fixture file. There is deliberately no live fetcher: see the README
for candidate sources and what to check before one is written."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Protocol

DEFAULT_FIXTURES = Path(__file__).parent / "fixtures" / "alerts.json"


@dataclass(frozen=True)
class Alert:
    publisher: str
    url: str
    published_at: date  # from the source's metadata, never from the model
    text: str  # untrusted prose
    title: str = ""


class FetchError(RuntimeError):
    pass


class AlertFetcher(Protocol):
    def fetch(self) -> list[Alert]: ...


class FixtureFetcher:
    def __init__(self, path: str | Path | None = None) -> None:
        self.path = Path(path) if path else DEFAULT_FIXTURES

    def fetch(self) -> list[Alert]:
        try:
            rows = json.loads(self.path.read_text(encoding="utf-8"))
            return [Alert(r["publisher"], r["url"], date.fromisoformat(r["published_at"]), r["text"], r.get("title", "")) for r in rows]
        except (OSError, ValueError, KeyError, TypeError) as err:
            raise FetchError(f"cannot read alerts from {self.path}: {err}") from err
