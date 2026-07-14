#!/usr/bin/env python3
"""Repair unconfirmed audiobook children from their attached file tags."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = PROJECT_ROOT / "backend"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))
os.chdir(BACKEND_ROOT)

from app.db.session import SessionLocal  # noqa: E402
from app.services.approved_candidate_materialization import (  # noqa: E402
    repair_materialized_audiobook_children,
)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--parent-batch-id", type=int)
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Persist repairs. Without this flag the script is read-only.",
    )
    args = parser.parse_args()
    with SessionLocal() as db:
        result = repair_materialized_audiobook_children(
            db,
            parent_batch_id=args.parent_batch_id,
            apply=args.apply,
        )
        print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
