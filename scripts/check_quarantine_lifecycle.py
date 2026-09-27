#!/usr/bin/env python3
"""Regression checks for the quarantine lifecycle and disposition records.

Covers quarantine, discard, undo discard, restore, reject records, grouped
loose files, restore collision safety, and scanner re-classification after a
quarantine row is retired. Uses a temporary data root and an in-memory
database; it never touches the real ingest, quarantine, or library folders.
"""

from __future__ import annotations

import fnmatch
import json
import sys
import tempfile
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = PROJECT_ROOT / "backend"
sys.path.insert(0, str(BACKEND_ROOT))

from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.api import routes
from app.core.config import settings
from app.db.session import Base
from app.models.archive import IngestBatch
from app.services import quarantine, scanner


failures: list[str] = []


def check(condition: bool, message: str) -> None:
    if not condition:
        failures.append(message)


def _touch(path: Path, content: bytes = b"x") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)


def _point_settings_at(root: Path) -> dict:
    names = [
        "data_root",
        "ingest_root",
        "reports_dir",
        "quarantine_unknown_dir",
        "quarantine_unsupported_dir",
        "quarantine_reports_dir",
        "dispositions_dir",
    ]
    original = {name: getattr(settings, name) for name in names}
    settings.data_root = root
    settings.ingest_root = root / "_INGEST" / "ready"
    settings.reports_dir = root / "_REPORTS" / "archive-assistant" / "ingest-reports"
    settings.quarantine_unknown_dir = root / "_QUARANTINE" / "unknown-type"
    settings.quarantine_unsupported_dir = root / "_QUARANTINE" / "unsupported-file"
    settings.quarantine_reports_dir = (
        root / "_REPORTS" / "archive-assistant" / "quarantine-reports"
    )
    settings.dispositions_dir = root / "_REPORTS" / "archive-assistant" / "dispositions"
    settings.ingest_root.mkdir(parents=True)
    return original


def _records(action: str | None = None) -> list[dict]:
    if not settings.dispositions_dir.exists():
        return []
    rows = [
        json.loads(path.read_text(encoding="utf-8"))
        for path in sorted(settings.dispositions_dir.glob("*.json"))
    ]
    return [row for row in rows if action is None or row["action"] == action]


def _unknown_batch(path: Path) -> IngestBatch:
    return IngestBatch(
        source_path=str(path),
        detected_type="unknown_type",
        status="needs_quarantine_review",
        confidence=0.0,
        metadata_json={"name": path.name, "reason": "Unknown folder"},
    )


def check_folder_lifecycle(session) -> None:
    source = settings.ingest_root / "Mystery Folder"
    _touch(source / "notes.pdf", b"pdf")
    _touch(source / "inner" / "readme.bin", b"bin")
    batch = _unknown_batch(source)
    session.add(batch)
    session.commit()

    destination = quarantine.quarantine_batch(session, batch)
    check(batch.status == "quarantined", "folder should be quarantined")
    check(not source.exists(), "source should leave ingest after quarantine")
    check(
        destination.is_relative_to(settings.quarantine_unknown_dir),
        "unknown folder should land in unknown-type quarantine",
    )
    check(len(_records("quarantined")) == 1, "quarantine should write a disposition")

    for bad_reason in ("", "  ", "no"):
        try:
            quarantine.discard_quarantined_batch(session, batch, bad_reason)
            failures.append(f"discard accepted a weak reason: {bad_reason!r}")
        except ValueError:
            pass
    check(batch.status == "quarantined", "rejected discard must not change status")

    quarantine.discard_quarantined_batch(session, batch, "Damaged download")
    check(batch.status == "discard_approved", "discard should mark discard_approved")
    check((destination / "notes.pdf").exists(), "discard must not delete files")
    discard = _records("discard_approved")
    check(len(discard) == 1, "discard should write a disposition")
    if discard:
        record = discard[0]
        check(record["reason"] == "Damaged download", "discard record keeps reason")
        check(record["inventory"]["file_count"] == 2, "discard inventory counts files")
        check(
            record["current_path"].startswith("_QUARANTINE/unknown-type/"),
            "discard record path should be relative to the data root",
        )
        check(
            record["original_source_path"] == "_INGEST/ready/Mystery Folder",
            "discard record keeps the original ingest path",
        )

    try:
        routes.reject_batch(batch.id, session)
        failures.append("reject must refuse a discard_approved batch")
    except HTTPException:
        pass
    try:
        quarantine.restore_quarantined_batch(session, batch)
        failures.append("restore must refuse a discard_approved batch")
    except ValueError:
        pass

    quarantine.revoke_discard(session, batch)
    check(batch.status == "quarantined", "undo discard returns to quarantined")
    check(
        "discard_reason" not in (batch.metadata_json or {}),
        "undo discard clears the discard reason",
    )
    check(len(_records("discard_revoked")) == 1, "undo discard writes a disposition")

    # Restore must refuse to overwrite something new at the original path.
    _touch(source / "new.txt")
    try:
        quarantine.restore_quarantined_batch(session, batch)
        failures.append("restore must refuse an existing destination")
    except ValueError:
        pass
    check(batch.status == "quarantined", "failed restore leaves status alone")
    check((destination / "notes.pdf").exists(), "failed restore leaves quarantine intact")
    (source / "new.txt").unlink()
    source.rmdir()

    # The user edits the item while it sits in quarantine.
    _touch(destination / "added-while-quarantined.txt")
    quarantine.restore_quarantined_batch(session, batch)
    check(batch.status == "needs_quarantine_review", "restore returns to review")
    check((source / "notes.pdf").exists(), "restore moves files back to ingest")
    check(not destination.exists(), "restore empties the quarantine location")
    metadata = batch.metadata_json or {}
    check("quarantine_destination" not in metadata, "restore clears quarantine location")
    check(metadata.get("file_count") == 3, "restore refreshes counts after edits")
    events = [item["event"] for item in metadata.get("quarantine_history", [])]
    check(
        events == ["quarantined", "discard_approved", "discard_revoked", "restored"],
        f"history should record every step, got {events}",
    )
    check(len(_records("restored")) == 1, "restore writes a disposition")

    # A restored row is the live review row, so a rescan must not duplicate it.
    created = scanner._create_unknown_batch(session, source, "unknown_type")
    check(created is None, "rescan must not duplicate a restored review row")


def check_grouped_loose_files(session) -> None:
    first = settings.ingest_root / "setup.exe"
    second = settings.ingest_root / "archive.iso"
    _touch(first)
    _touch(second)
    batch = IngestBatch(
        source_path=str(settings.ingest_root),
        detected_type="unsupported_file",
        status="needs_quarantine_review",
        confidence=0.0,
        metadata_json={
            "name": "Unsupported loose files",
            "grouped_loose_files": [str(first), str(second)],
        },
    )
    session.add(batch)
    session.commit()

    destination = quarantine.quarantine_batch(session, batch)
    check(
        destination.is_relative_to(settings.quarantine_unsupported_dir),
        "unsupported files should land in unsupported-file quarantine",
    )
    check(not first.exists() and not second.exists(), "loose files leave ingest")
    check(
        len((batch.metadata_json or {}).get("quarantine_items", [])) == 2,
        "grouped quarantine records each file mapping",
    )

    quarantine.restore_quarantined_batch(session, batch)
    check(first.exists() and second.exists(), "grouped restore returns every file")
    check(not destination.exists(), "grouped restore removes the empty group folder")
    check(settings.ingest_root.exists(), "grouped restore never touches ingest root itself")
    check(batch.status == "needs_quarantine_review", "grouped restore returns to review")

    # Rows quarantined before item mappings existed must still restore.
    legacy_dir = settings.quarantine_unknown_dir / "loose-files" / "20260101T000000Z"
    legacy_file = settings.ingest_root / "old.bin"
    _touch(legacy_dir / "old.bin")
    legacy = IngestBatch(
        source_path=str(settings.ingest_root),
        detected_type="unsupported_file",
        status="quarantined",
        confidence=0.0,
        metadata_json={
            "name": "Unsupported loose files",
            "grouped_loose_files": [str(legacy_file)],
            "quarantine_destination": str(legacy_dir),
        },
    )
    session.add(legacy)
    session.commit()
    quarantine.restore_quarantined_batch(session, legacy)
    check(legacy_file.exists(), "legacy grouped restore falls back to file names")


def check_reject_record(session) -> None:
    source = settings.ingest_root / "Shared Discography"
    _touch(source / "a.flac")
    rejected = IngestBatch(
        source_path=str(source),
        detected_type="music_album",
        status="pending_review",
        confidence=0.7,
        metadata_json={"album": "Album A"},
    )
    sibling = IngestBatch(
        source_path=str(source),
        detected_type="music_album",
        status="pending_review",
        confidence=0.7,
        metadata_json={"album": "Album B"},
    )
    session.add_all([rejected, sibling])
    session.commit()

    routes.reject_batch(rejected.id, session)
    check(rejected.status == "rejected", "reject still sets rejected")
    check((source / "a.flac").exists(), "reject never moves or deletes files")
    records = [row for row in _records("rejected") if row["batch_id"] == rejected.id]
    check(len(records) == 1, "reject writes a disposition")
    if records:
        check(
            records[0]["shared_source_batch_ids"] == [sibling.id],
            "reject record lists batches sharing the source folder",
        )
        check(records[0]["status_before"] == "pending_review", "reject keeps prior status")


def check_retired_rows_do_not_block(session) -> None:
    source = settings.ingest_root / "Reused Name"
    source.mkdir()
    _touch(source / "thing.dat")
    retired = _unknown_batch(source)
    retired.status = "merged"
    session.add(retired)
    session.commit()
    created = scanner._create_unknown_batch(session, source, "unknown_type")
    check(created is not None, "a merged quarantine row must not block re-classification")


def check_recovery_routes_unknown_items_back_to_quarantine(session) -> None:
    source = settings.ingest_root / "Rejected Unknown"
    _touch(source / "blob.dat")
    unknown = _unknown_batch(source)
    session.add(unknown)
    session.commit()
    routes.reject_batch(unknown.id, session)
    routes.send_to_recovery(unknown.id, session)
    check(
        unknown.status == "needs_quarantine_review",
        f"recovery should return an unknown item to quarantine review, got {unknown.status}",
    )

    gone = _unknown_batch(Path(r"C:\tmp\definitely-missing-test-root\Gone"))
    moved = IngestBatch(
        source_path=str(settings.ingest_root / "Moved Album"),
        detected_type="music_album",
        status="moved",
        confidence=1.0,
        metadata_json={},
    )
    session.add_all([gone, moved])
    session.commit()
    for batch, label in ((gone, "unknown item outside ingest"), (moved, "moved batch")):
        before = batch.status
        try:
            routes.send_to_recovery(batch.id, session)
            failures.append(f"recovery must refuse a {label}")
        except HTTPException:
            pass
        check(batch.status == before, f"refused recovery must not change a {label}")

    stuck = _unknown_batch(Path(r"C:\tmp\definitely-missing-test-root\Stuck"))
    stuck.status = "metadata_recovery"
    stuck_rejected = _unknown_batch(Path(r"C:\tmp\definitely-missing-test-root\Stuck2"))
    stuck_rejected.status = "rejected"
    session.add_all([stuck, stuck_rejected])
    session.commit()
    scanner.repair_stale_media_batches(session, {})
    check(stuck.status == "merged", "scan should retire a stuck recovery row with no files")
    check(stuck_rejected.status == "merged", "scan should retire a rejected unknown row with no files")


def check_tv_scan_does_not_take_over_quarantined_row(session) -> None:
    source = settings.ingest_root / "Some Show Season 1"
    held = _unknown_batch(source)
    held.status = "quarantined"
    held.metadata_json = {
        **(held.metadata_json or {}),
        "quarantine_destination": str(settings.quarantine_unknown_dir / "Some Show Season 1"),
    }
    session.add(held)
    session.commit()
    _touch(source / "Some Show - S01E01 - Pilot.mkv", b"video")
    _touch(source / "Some Show - S01E02 - Second.mkv", b"video")
    created = scanner._create_tv_batch(session, source)
    check(created is not None and created.id != held.id, "a new TV folder must get its own batch")
    check(held.status == "quarantined", "the quarantined row must keep tracking its files")
    check(held.detected_type == "unknown_type", "the quarantined row must not be converted to TV")


def check_cleaner_does_not_mistake_records_for_manifests() -> None:
    names = [path.name for path in settings.dispositions_dir.glob("*.json")]
    check(bool(names), "disposition records should exist by now")
    for name in names:
        if name == "move_manifest.json" or fnmatch.fnmatch(name, "*_move_manifest.json"):
            failures.append(f"disposition record looks like a move manifest: {name}")


def run() -> None:
    temp_root = Path(r"C:\tmp")
    temp_root.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(
        prefix="archive-quarantine-lifecycle-",
        dir=temp_root,
    ) as temporary:
        original = _point_settings_at(Path(temporary))
        engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(engine)
        session = sessionmaker(bind=engine)()
        try:
            check_folder_lifecycle(session)
            check_grouped_loose_files(session)
            check_reject_record(session)
            check_retired_rows_do_not_block(session)
            check_recovery_routes_unknown_items_back_to_quarantine(session)
            check_tv_scan_does_not_take_over_quarantined_row(session)
            check_cleaner_does_not_mistake_records_for_manifests()
        finally:
            session.close()
            engine.dispose()
            for name, value in original.items():
                setattr(settings, name, value)

    if failures:
        print("FAIL - quarantine lifecycle")
        for failure in failures:
            print("  x", failure)
        raise SystemExit(1)
    print("PASS - quarantine lifecycle, discard records, and restore are safe")


if __name__ == "__main__":
    run()
