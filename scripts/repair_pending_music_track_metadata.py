"""Repair stored track evidence for existing pending music batches."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = PROJECT_ROOT / "backend"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.db.session import SessionLocal  # noqa: E402
from app.services.track_metadata_repair import (  # noqa: E402
    repair_all_pending_music_track_metadata,
    repair_pending_music_batch_track_metadata,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Rebuild stored track evidence and completeness from files already "
            "attached to pending music batches. This does not scan or move files."
        ),
    )
    target = parser.add_mutually_exclusive_group(required=True)
    target.add_argument("--batch-id", type=int, help="Repair one pending music batch")
    target.add_argument(
        "--all-pending",
        action="store_true",
        help="Repair every pending music batch with attached files",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Calculate and print repairs, then roll back all database changes",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    with SessionLocal() as db:
        try:
            if args.batch_id is not None:
                result: object = repair_pending_music_batch_track_metadata(
                    db,
                    args.batch_id,
                    commit=not args.dry_run,
                )
            else:
                result = repair_all_pending_music_track_metadata(
                    db,
                    commit=not args.dry_run,
                )
            if args.dry_run:
                db.rollback()
        except ValueError as exc:
            db.rollback()
            print(f"ERROR: {exc}", file=sys.stderr)
            return 1

    print(json.dumps({"dry_run": args.dry_run, "result": result}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())