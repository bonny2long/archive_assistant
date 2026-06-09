"""Preview or apply the reusable Archive Assistant all-media test reset."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = PROJECT_ROOT / "backend"
sys.path.insert(0, str(BACKEND_ROOT))

from app.db.init_db import init_db  # noqa: E402
from app.db.session import SessionLocal  # noqa: E402
from app.services.dev_reset import (  # noqa: E402
    DevResetBlockedError,
    reset_test_data,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Restore moved or quarantined media to original ingest paths and "
            "clear all test rows without dropping database tables."
        )
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Perform the reset. Without this flag, only print the planned summary.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    init_db()
    with SessionLocal() as db:
        try:
            summary = reset_test_data(db, apply=args.apply)
        except DevResetBlockedError as exc:
            print("Reset blocked:", file=sys.stderr)
            for error in exc.errors:
                print(f"  {error}", file=sys.stderr)
            return 1

    print(summary.message)
    print(f"Status: {summary.status}")
    print(f"Files: {summary.restored_files}")
    print(f"Reports: {summary.removed_reports}")
    print(f"Move logs: {summary.removed_move_logs}")
    print(f"Empty directories: {summary.removed_empty_dirs}")
    print(f"Batches: {summary.cleared_batches}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
