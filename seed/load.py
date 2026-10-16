"""Load the synthetic seed into case-db, intel-db and ref-db (idempotent).

    MIMAMORI_STORE=firestore FIRESTORE_EMULATOR_HOST=localhost:8086 python seed/load.py
    python seed/load.py --db intel          # one database only

Core banking's data (seed/bank/) is not loaded here: core-bank-mock reads it into its own store.
With the default in-memory store this only makes sense inside one process (tests, notebooks).
"""

import argparse

from mimamori_common.config import Settings
from mimamori_common.seed import load_case_db, load_intel_db, load_ref_db
from mimamori_common.store import open_case_repo, open_intel_repo, open_ref_repo


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", choices=["case", "intel", "ref", "all"], default="all")
    args = ap.parse_args()
    settings = Settings.from_env()
    if args.db in ("case", "all"):
        load_case_db(open_case_repo(settings))
    if args.db in ("intel", "all"):
        load_intel_db(open_intel_repo(settings))
    if args.db in ("ref", "all"):
        load_ref_db(open_ref_repo(settings))
    print(f"seeded {args.db} ({settings.store_backend})")


if __name__ == "__main__":
    main()
