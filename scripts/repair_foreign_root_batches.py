#!/usr/bin/env python3
"""Retire batches whose source lives outside the current data root.

Test runs pointed at a temporary data root (for example C:\\tmp\\bm-prod6c-nas)
can leave rows in the live database. Their files were never in this NAS, so
they inflate library counts and can get stuck in review states forever.

This script never deletes rows or files. Each matching row is set to
``merged`` (hidden from the dashboard) and its previous status is kept in
``metadata_json.foreign_root_retired`` so the change can be reversed.

Dry run by default. With ``--apply`` it first writes a verified SQLite backup
and a JSON change report.

Run from the backend folder so the backend .env is used:

    .venv\\Scripts\\python.exe ..\\scripts\\repair_foreign_root_batches.py
    .venv\\Scripts\\python.exe ..\\scripts\\repair_foreign_root_batches.py --apply
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "backend"))

from app.core.config import settings  # noqa: E402
from app.core.time import now_utc, serialize_utc  # noqa: E402
from app.db.session import SessionLocal  # noqa: E402
from app.models.archive import IngestBatch  # noqa: E402


def _inside_data_root(path_text: str) -> bool:
    try:
        Path(path_text).resolve().relative_to(settings.data_root.resolve())
        return True
    except (OSError, ValueError):
        return False


def _database_file() -> Path:
    url = settings.database_url
    if not url.startswith("sqlite:///"):
        raise SystemExit("Only SQLite databases are supported by this repair")
    return Path(url[len("sqlite:///"):]).resolve()


def _backup(database: Path, backup_dir: Path) -> dict:
    backup_dir.mkdir(parents=True, exist_ok=True)
    target = backup_dir / database.name
    if target.exists():
        raise SystemExit(f"Backup already exists, refusing to overwrite: {target}")
    source = sqlite3.connect(f"file:{database.as_posix()}?mode=ro", uri=True)
    destination = sqlite3.connect(str(target))
    source.backup(destination)
    destination.close()
    source.close()
    check = sqlite3.connect(str(target))
    integrity = check.execute("pragma integrity_check").fetchone()[0]
    batches = check.execute("select count(*) from ingest_batches").fetchone()[0]
    check.close()
    if integrity != "ok":
        raise SystemExit(f"Backup integrity check failed: {integrity}")
    return {
        "path": str(target),
        "sha256": hashlib.sha256(target.read_bytes()).hexdigest(),
        "size_bytes": target.stat().st_size,
        "integrity": integrity,
        "batch_count": batches,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--apply", action="store_true", help="make the change (default is a dry run)")
    parser.add_argument(
        "--backup-root",
        type=Path,
        default=None,
        help="folder for the backup (default: <data root parent>/Backups)",
    )
    args = parser.parse_args()

    with SessionLocal() as db:
        rows = [
            batch
            for batch in db.query(IngestBatch).filter(IngestBatch.status != "merged").all()
            if not _inside_data_root(batch.source_path)
        ]
        print(f"Data root: {settings.data_root}")
        print(f"Database:  {_database_file()}")
        print(f"Batches outside the data root: {len(rows)}")
        for batch in rows:
            print(f"  #{batch.id:<4} {batch.status:<18} {batch.detected_type:<18} {batch.source_path}")
        if not rows:
            return 0
        if not args.apply:
            print("\nDry run only. Re-run with --apply to retire these rows.")
            return 0

        stamp = now_utc().strftime("%Y%m%dT%H%M%SZ")
        backup_root = args.backup_root or (settings.data_root.parent / "Backups")
        backup_dir = backup_root / f"{stamp}-aa-foreign-root-repair"
        backup = _backup(_database_file(), backup_dir)
        print(f"\nBackup written and verified: {backup['path']}")

        changes = []
        retired_at = serialize_utc(now_utc())
        for batch in rows:
            metadata = dict(batch.metadata_json or {})
            metadata["foreign_root_retired"] = {
                "status_before": batch.status,
                "data_root_at_repair": str(settings.data_root),
                "retired_at": retired_at,
                "reason": "source path is outside the current data root",
            }
            changes.append({
                "batch_id": batch.id,
                "status_before": batch.status,
                "status_after": "merged",
                "source_path": batch.source_path,
            })
            batch.metadata_json = metadata
            batch.status = "merged"
            batch.updated_at = now_utc()
        db.commit()

        report = {
            "repair": "foreign_root_batches",
            "applied_at": retired_at,
            "data_root": str(settings.data_root),
            "backup": backup,
            "changes": changes,
            "undo": "set each batch's status back to metadata_json.foreign_root_retired.status_before",
        }
        report_path = backup_dir / "repair-report.json"
        report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
        print(f"Retired {len(changes)} batch(es). Report: {report_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
