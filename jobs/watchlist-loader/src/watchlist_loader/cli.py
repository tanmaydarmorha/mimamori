from __future__ import annotations

import logging
import os
import sys

from mimamori_common.config import Settings
from mimamori_common.store import open_ref_repo

from .loader import run
from .sources import SourceError, make_fetcher

log = logging.getLogger("watchlist_loader")


def main() -> int:
    """Exit 0: written or unchanged. 1: source rejected (last good snapshot untouched). 2: anything else."""
    logging.basicConfig(level=logging.INFO, stream=sys.stdout, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    try:
        settings = Settings.from_env()
        fetcher = make_fetcher(os.environ.get("WATCHLIST_SOURCE", "fixture"), os.environ.get("WATCHLIST_SOURCE_PATH") or None)
        result = run(fetcher, open_ref_repo(settings), settings.now())
    except SourceError as exc:
        log.error("source rejected, last good snapshot left in place: %s", exc)
        return 1
    except Exception:
        log.exception("watchlist-loader failed")
        return 2
    print(f"{result.status} snapshot={result.snapshot_id} entries={result.entries} hash={result.content_hash}")
    return 0
