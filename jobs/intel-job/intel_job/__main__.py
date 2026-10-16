"""`python -m intel_job`: run once. Exit 0 on success (including alerts rejected or skipped as
duplicates), 1 if the fetch failed or any alert hit an error. Fixture source unless
`INTEL_ALERTS_FILE` points elsewhere; a live fetcher does not exist."""

from __future__ import annotations

import asyncio
import logging
import os
import sys

from mimamori_common.llm import get_general_client
from mimamori_common.store import open_intel_repo

from .fetcher import FetchError, FixtureFetcher
from .job import run


def main() -> int:
    logging.basicConfig(level=os.environ.get("LOG_LEVEL", "INFO"), format="%(asctime)s %(levelname)s %(name)s %(message)s")
    fetcher = FixtureFetcher(os.environ.get("INTEL_ALERTS_FILE"))
    try:
        report = asyncio.run(run(fetcher, get_general_client(), open_intel_repo()))
    except FetchError as err:
        logging.getLogger("intel_job").error("fetch failed: %s", err)
        return 1
    return 0 if report.ok else 1


if __name__ == "__main__":
    sys.exit(main())
