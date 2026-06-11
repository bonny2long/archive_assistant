from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.archive import ArchiveItem, IngestBatch, IngestFile, MoveAction
from app.services.music_metadata import is_audio_file
from app.services.video_metadata import is_video_file


@dataclass(frozen=True)
class DevResetSummary:
    status: str
    restored_tracks: int
    restored_files: int
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
    for pattern in (
        "batch-*-move-log.json",
        "batch-*-movie-move-log.json",
        "batch-*-tv-move-log.json",
        "discography-move-log.json",
    ):
        for path in settings.data_root.rglob(pattern):
            if path.is_file():
                path.unlink()
                removed += 1
    return removed


def _media_roots() -> list[Path]:
    return [
        settings.data_root / "Music" / "Library",
        settings.music_discographies_dir,
        settings.quarantine_discography_dir,
        settings.movies_dir,
        settings.movies_metadata_dir,
        settings.tv_dir,
        settings.tv_metadata_dir,
        settings.books_dir,
        settings.audiobooks_dir,
    ]


def _validate_moves(moves: list[MoveAction]) -> list[str]:
    errors: list[str] = []
    seen_sources: set[Path] = set()
    library_roots = _media_roots()

    for move in moves:
        if move.status != "completed":
            continue

        source = Path(move.source_path)
        destination = Path(move.destination_path)
        if not _is_within(source, settings.ingest_root):
            errors.append(f"Source is outside ingest root: {source}")
        if not any(_is_within(destination, root) for root in library_roots):
            errors.append(f"Destination is outside managed media roots: {destination}")
        if source in seen_sources:
            errors.append(f"Duplicate restore target: {source}")
        seen_sources.add(source)
        if source.exists() and destination.exists():
            errors.append(f"Both restore paths exist; refusing to overwrite: {source}")
        elif not source.exists() and not destination.exists():
            errors.append(
                "Neither restore path exists; keeping database records for "
                f"manual recovery: {source} <- {destination}"
            )

    return errors


def _untracked_library_media(moves: list[MoveAction]) -> list[Path]:
    tracked_destinations = {
        Path(move.destination_path).resolve()
        for move in moves
        if move.status == "completed"
    }
    untracked = []
    for root in _media_roots():
        if not root.exists():
            continue
        for path in root.rglob("*"):
            if (
                path.is_file()
                and (is_audio_file(path) or is_video_file(path))
                and path.resolve() not in tracked_destinations
            ):
                untracked.append(path)
    return sorted(set(untracked))


def _validate_restore_completion(
    moves: list[MoveAction],
    quarantine_plan: list[tuple[Path, Path]],
) -> list[str]:
    errors = []
    for move in moves:
        if move.status != "completed":
            continue
        source = Path(move.source_path)
        destination = Path(move.destination_path)
        if not source.exists():
            errors.append(f"Restored source is missing: {source}")
        if destination.exists():
            errors.append(f"Library destination still exists after restore: {destination}")

    for quarantine_source, original in quarantine_plan:
        if not original.exists():
            errors.append(f"Restored quarantine source is missing: {original}")
        if quarantine_source.exists():
            errors.append(
                "Quarantine source still exists after restore: "
                f"{quarantine_source}"
            )
    return errors


def _quarantine_restore_plan(
    batches: list[IngestBatch],
) -> tuple[list[tuple[Path, Path]], list[str]]:
    plan: list[tuple[Path, Path]] = []
    errors: list[str] = []
    quarantine_root = settings.data_root / "_QUARANTINE"
    for batch in batches:
        if batch.status != "quarantined":
            continue
        metadata = batch.metadata_json or {}
        quarantine_source = Path(
            metadata.get("quarantine_destination")
            or batch.suggested_destination
            or ""
        )
        if not quarantine_source.exists():
            errors.append(
                f"Quarantine source not found for batch {batch.id}: "
                f"{quarantine_source}"
            )
            continue
        if not _is_within(quarantine_source, quarantine_root):
            errors.append(
                f"Quarantine source is outside quarantine root: "
                f"{quarantine_source}"
            )
            continue

        grouped_paths = [
            Path(value)
            for value in metadata.get("grouped_loose_files", [])
            if isinstance(value, str)
        ]
        if grouped_paths:
            for original in grouped_paths:
                candidate = quarantine_source / original.name
                if not candidate.exists():
                    errors.append(
                        f"Grouped quarantine file not found: {candidate}"
                    )
                    continue
                plan.append((candidate, original))
        else:
            plan.append((quarantine_source, Path(batch.source_path)))

    for quarantine_source, original in plan:
        if not _is_within(original, settings.ingest_root):
            errors.append(f"Restore destination is outside ingest: {original}")
        if original.exists():
            empty_directory = (
                original.is_dir()
                and not any(path.is_file() for path in original.rglob("*"))
            )
            if not empty_directory:
                errors.append(f"Restore destination already exists: {original}")
    return plan, errors


def _remove_quarantine_reports(batch_ids: list[int]) -> int:
    if not settings.quarantine_reports_dir.exists():
        return 0
    batch_suffixes = tuple(f"_{batch_id}.json" for batch_id in batch_ids)
    removed = 0
    for path in settings.quarantine_reports_dir.glob("*.json"):
        if path.name.endswith(batch_suffixes):
            path.unlink()
            removed += 1
    return removed


def reset_test_data(db: Session, *, apply: bool) -> DevResetSummary:
    batches = db.query(IngestBatch).order_by(IngestBatch.id.asc()).all()
    batch_ids = [batch.id for batch in batches]
    moves = (
        db.query(MoveAction)
        .filter(MoveAction.batch_id.in_(batch_ids))
        .order_by(MoveAction.id.asc())
        .all()
        if batch_ids
        else []
    )

    quarantine_plan, quarantine_errors = _quarantine_restore_plan(batches)
    errors = [*_validate_moves(moves), *quarantine_errors]
    untracked_media = _untracked_library_media(moves)
    if untracked_media:
        sample = ", ".join(str(path) for path in untracked_media[:3])
        errors.append(
            f"{len(untracked_media)} managed library media file(s) have no "
            f"completed move record. Reset will not clear the database. "
            f"Examples: {sample}"
        )
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
            restored_files=len(restorable) + len(quarantine_plan),
            removed_reports=len(batch_ids),
            removed_move_logs=0,
            removed_empty_dirs=0,
            cleared_batches=len(batch_ids),
            message=(
                "Dry run only. "
                f"Would restore {len(restorable) + len(quarantine_plan)} "
                "file(s) to ingest and "
                f"clear {len(batch_ids)} ingest batch(es)."
            ),
        )

    restored_tracks = 0
    for move in restorable:
        source = Path(move.source_path)
        destination = Path(move.destination_path)
        source.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(destination), str(source))
        restored_tracks += 1
    restored_files = restored_tracks

    for quarantine_source, original in quarantine_plan:
        if original.exists() and original.is_dir():
            original.rmdir()
        original.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(quarantine_source), str(original))
        restored_files += 1

    completion_errors = _validate_restore_completion(moves, quarantine_plan)
    remaining_untracked_media = _untracked_library_media(moves)
    if remaining_untracked_media:
        sample = ", ".join(str(path) for path in remaining_untracked_media[:3])
        completion_errors.append(
            f"{len(remaining_untracked_media)} untracked media file(s) remain "
            f"in managed libraries after restore. Examples: {sample}"
        )
    if completion_errors:
        db.rollback()
        raise DevResetBlockedError(completion_errors)

    # Destructive cleanup happens only after every file restore is verified.
    removed_reports = (
        _remove_batch_reports(batch_ids)
        + _remove_quarantine_reports(batch_ids)
    )
    removed_move_logs = _remove_move_logs()
    removed_empty_dirs = sum(
        _remove_empty_directories(root)
        for root in [*_media_roots(), settings.data_root / "_QUARANTINE"]
    )

    if batch_ids:
        db.query(MoveAction).filter(MoveAction.batch_id.in_(batch_ids)).delete(
            synchronize_session=False
        )
        db.query(IngestFile).filter(IngestFile.batch_id.in_(batch_ids)).delete(
            synchronize_session=False
        )
        db.query(ArchiveItem).delete(synchronize_session=False)
        db.query(IngestBatch).filter(IngestBatch.id.in_(batch_ids)).delete(
            synchronize_session=False
        )
        db.commit()

    return DevResetSummary(
        status="ok",
        restored_tracks=restored_tracks,
        restored_files=restored_files,
        removed_reports=removed_reports,
        removed_move_logs=removed_move_logs,
        removed_empty_dirs=removed_empty_dirs,
        cleared_batches=len(batch_ids),
        message=(
            "All ingest test data reset. "
            f"Restored {restored_files} file(s) and cleared "
            f"{len(batch_ids)} batch(es). Source files were not deleted."
        ),
    )


def reset_music_test_data(db: Session, *, apply: bool) -> DevResetSummary:
    """Compatibility alias for existing scripts and older API clients."""
    return reset_test_data(db, apply=apply)
