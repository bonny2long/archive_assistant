from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.archive import ArchiveItem, IngestBatch, IngestFile, MoveAction


@dataclass(frozen=True)
class DevResetSummary:
    status: str
    restored_tracks: int
    removed_reports: int
    removed_move_logs: int
    removed_empty_dirs: int
    cleared_batches: int
    message: str


class DevResetBlockedError(Exception):
    def __init__(self, errors: list[str]):
        super().__init__("; ".join(errors))
        self.errors = errors


def _is_within(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False


def _remove_empty_directories(root: Path) -> int:
    if not root.exists():
        return 0
    removed = 0
    directories = sorted(
        (path for path in root.rglob("*") if path.is_dir()),
        key=lambda path: len(path.parts),
        reverse=True,
    )
    for directory in directories:
        try:
            directory.rmdir()
            removed += 1
        except OSError:
            pass
    return removed


def _remove_batch_reports(batch_ids: list[int]) -> int:
    removed = 0
    for batch_id in batch_ids:
        report = settings.reports_dir / f"batch-{batch_id}.json"
        if report.exists():
            report.unlink()
            removed += 1
    return removed


def _remove_move_logs() -> int:
    removed = 0
    roots = [
        settings.data_root / "Music" / "Library",
        settings.music_discographies_dir,
        settings.move_logs_dir,
    ]
    for root in roots:
        if not root.exists():
            continue
        for pattern in ("batch-*-move-log.json", "discography-move-log.json"):
            for path in root.rglob(pattern):
                if path.is_file():
                    path.unlink()
                    removed += 1
    return removed


def _validate_moves(moves: list[MoveAction]) -> list[str]:
    errors: list[str] = []
    seen_sources: set[Path] = set()
    library_roots = [
        settings.data_root / "Music" / "Library",
        settings.music_discographies_dir,
        settings.quarantine_discography_dir,
    ]

    for move in moves:
        if move.status != "completed":
            continue

        source = Path(move.source_path)
        destination = Path(move.destination_path)
        if not _is_within(source, settings.ingest_music_dir):
            errors.append(f"Source is outside music ingest: {source}")
        if not any(_is_within(destination, root) for root in library_roots):
            errors.append(f"Destination is outside music library: {destination}")
        if source in seen_sources:
            errors.append(f"Duplicate restore target: {source}")
        seen_sources.add(source)
        if source.exists() and destination.exists():
            errors.append(f"Both restore paths exist; refusing to overwrite: {source}")

    return errors


def reset_music_test_data(db: Session, *, apply: bool) -> DevResetSummary:
    batches = (
        db.query(IngestBatch)
        .filter(IngestBatch.detected_type.in_(["music_album", "music_discography"]))
        .order_by(IngestBatch.id.asc())
        .all()
    )
    batch_ids = [batch.id for batch in batches]
    moves = (
        db.query(MoveAction)
        .filter(MoveAction.batch_id.in_(batch_ids))
        .order_by(MoveAction.id.asc())
        .all()
        if batch_ids
        else []
    )

    errors = _validate_moves(moves)
    if errors:
        raise DevResetBlockedError(errors)

    restorable = [
        move
        for move in moves
        if move.status == "completed" and Path(move.destination_path).exists()
    ]
    if not apply:
        return DevResetSummary(
            status="dry_run",
            restored_tracks=len(restorable),
            removed_reports=len(batch_ids),
            removed_move_logs=0,
            removed_empty_dirs=0,
            cleared_batches=len(batch_ids),
            message=(
                "Dry run only. "
                f"Would restore {len(restorable)} track(s) to ingest."
            ),
        )

    restored_tracks = 0
    for move in restorable:
        source = Path(move.source_path)
        destination = Path(move.destination_path)
        source.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(destination), str(source))
        restored_tracks += 1

    removed_reports = _remove_batch_reports(batch_ids)
    removed_move_logs = _remove_move_logs()
    removed_empty_dirs = sum(
        _remove_empty_directories(root)
        for root in (
            settings.data_root / "Music" / "Library",
            settings.music_discographies_dir,
            settings.quarantine_discography_dir,
        )
    )

    if batch_ids:
        db.query(MoveAction).filter(MoveAction.batch_id.in_(batch_ids)).delete(
            synchronize_session=False
        )
        db.query(IngestFile).filter(IngestFile.batch_id.in_(batch_ids)).delete(
            synchronize_session=False
        )
        db.query(ArchiveItem).filter(ArchiveItem.media_type == "music").delete(
            synchronize_session=False
        )
        db.query(IngestBatch).filter(IngestBatch.id.in_(batch_ids)).delete(
            synchronize_session=False
        )
        db.commit()

    return DevResetSummary(
        status="ok",
        restored_tracks=restored_tracks,
        removed_reports=removed_reports,
        removed_move_logs=removed_move_logs,
        removed_empty_dirs=removed_empty_dirs,
        cleared_batches=len(batch_ids),
        message=f"Music test data reset. Restored {restored_tracks} tracks to ingest.",
    )
