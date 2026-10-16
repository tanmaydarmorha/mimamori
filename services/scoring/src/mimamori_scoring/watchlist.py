"""Watchlist matching against the latest `ref-db` snapshot (cached briefly in process)."""

from __future__ import annotations

import time
import unicodedata

import anyio
from mimamori_common.models.baseline import WatchlistEntry, WatchlistSnapshot
from mimamori_common.store import RefRepo

_DROP = str.maketrans("", "", " 　()・")


def normalise(name: str | None) -> str:
    """NFKC, no spaces or brackets, katakana only: `カ）ミライ` and `ｶ)ﾐﾗｲ` compare equal."""
    if not name:
        return ""
    text = unicodedata.normalize("NFKC", name).translate(_DROP)
    return "".join(chr(ord(c) + 0x60) if "ぁ" <= c <= "ゖ" else c for c in text).upper()


class Watchlist:
    def __init__(self, repo: RefRepo, ttl_s: float) -> None:
        self.repo, self.ttl_s = repo, ttl_s
        self._loaded_at = float("-inf")
        self._entries: list[WatchlistEntry] = []
        self._snapshot_id: str | None = None

    def _load(self) -> None:
        doc = self.repo.get_latest_snapshot()
        self._entries = WatchlistSnapshot.model_validate(doc).entries if doc else []
        self._snapshot_id = doc["snapshot_id"] if doc else None
        self._loaded_at = time.monotonic()

    async def entries(self) -> list[WatchlistEntry]:
        if time.monotonic() - self._loaded_at > self.ttl_s:
            await anyio.to_thread.run_sync(self._load)
        return self._entries

    @property
    def snapshot_id(self) -> str | None:
        return self._snapshot_id

    async def match(self, name_kana: str | None, account_id: str | None) -> list[WatchlistEntry]:
        """Entries whose kana / Japanese name equals the payee name, or whose account hint contains the
        payee's account id as a whole token."""
        wanted = normalise(name_kana)
        hits = []
        for entry in await self.entries():
            names = {normalise(entry.name_kana), normalise(entry.name_ja)} - {""}
            by_name = bool(wanted) and wanted in names
            by_account = bool(account_id and entry.account_hint and account_id in entry.account_hint.split())
            if by_name or by_account:
                hits.append(entry)
        return hits
