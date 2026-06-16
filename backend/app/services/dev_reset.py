from __future__ import annotations

import json
import shutil
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.archive import ArchiveItem, IngestBatch, IngestFile, MoveAction
from app.services.music_metadata import is_audio_file
from app.services.video_metadata import is_video_file


IGNORED_RESET_SIDECAR_EXTENSIONS = {
    ".txt",
    ".nfo",
    ".url",
    ".sfv",
    ".md",
    ".log",
    ".m3u",
    ".md5",
}


@dataclass(frozen=True)
class DevResetSummary:
    status: str
    restored_tracks: int
    restored_files: int
    recovered_media_files: int
    untracked_library_media_files: int
    removed_reports: int
    removed_move_logs: int
    removed_library_metadata: int
    removed_empty_dirs: int
    cleared_batches: int
    message: str


@dataclass(frozen=True)
class OrphanLibraryRestore:
    library_root: Path
    ingest_root: Path
    files: tuple[tuple[Path, Path], ...]


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


def _reset_recovery_root() -> Path:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return settings.data_root / "_RECOVERY" / f"reset-{stamp}"


def _count_payload_files(path: Path) -> int:
    if path.is_file():
        return 1
    if path.is_dir():
        return sum(1 for child in path.rglob("*") if child.is_file())
    return 0


def _move_existing_ingest_path_to_recovery(
    path: Path,
    recovery_root: Path,
) -> int:
    if not path.exists():
        return 0
    if not _is_within(path, settings.ingest_root):
        raise DevResetBlockedError([f"Recovery source is outside ingest: {path}"])
    relative = path.resolve().relative_to(settings.ingest_root.resolve())
    destination = recovery_root / relative
    if destination.exists():
        raise DevResetBlockedError([
            f"Recovery destination already exists: {destination}"
        ])
    destination.parent.mkdir(parents=True, exist_ok=True)
    count = _count_payload_files(path)
    shutil.move(str(path), str(destination))
    return count


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
        "move_manifest.json",
        "move_manifest.md",
        "*_move_manifest.json",
        "*_move_manifest.md",
    ):
        for path in settings.data_root.rglob(pattern):
            if (
                _is_within(path, settings.ingest_root)
                or _is_within(path, settings.data_root / "_RECOVERY")
            ):
                continue
            if path.is_file():
                path.unlink()
                removed += 1
    return removed


GENERATED_LIBRARY_MANIFESTS = {
    "audiobook.json",
    "book.json",
    "discography.json",
    "movie.json",
    "music-album.json",
    "tv-show.json",
}


def _destination_has_payload(destination: Path) -> bool:
    if not destination.exists():
        return False
    return any(
        path.is_file() and "metadata" not in {
            part.casefold() for part in path.relative_to(destination).parts
        }
        for path in destination.rglob("*")
    )


def _remove_orphaned_library_metadata() -> int:
    removed = 0
    for root in _media_roots():
        if not root.exists():
            continue
        for manifest in root.rglob("*.json"):
            if (
                manifest.name not in GENERATED_LIBRARY_MANIFESTS
                or manifest.parent.name.casefold() != "metadata"
            ):
                continue
            destination = manifest.parent.parent
            if _destination_has_payload(destination):
                continue
            manifest.unlink()
            removed += 1

    index_dirs = {
        settings.music_metadata_dir,
        settings.movies_metadata_dir,
        settings.tv_metadata_dir,
        settings.books_metadata_dir,
        settings.audiobooks_metadata_dir,
    }
    for index_dir in index_dirs:
        index_path = index_dir / "library-index.json"
        if not index_path.exists():
            continue
        try:
            loaded = json.loads(index_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            loaded = []
        entries = loaded if isinstance(loaded, list) else []
        kept = []
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            relative = entry.get("library_path") or entry.get(
                "destination_path"
            )
            if not relative:
                continue
            destination = settings.data_root / Path(
                str(relative).replace("\\", "/")
            )
            if _destination_has_payload(destination):
                kept.append(entry)
        if kept:
            if kept != entries:
                index_path.write_text(
                    json.dumps(kept, indent=2, ensure_ascii=False),
                    encoding="utf-8",
                )
                removed += len(entries) - len(kept)
        else:
            index_path.unlink()
            removed += max(1, len(entries))
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
        if not source.exists() and not destination.exists():
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


def _is_sidecar_only_ingest_folder(path: Path) -> bool:
    if not path.is_dir():
        return False
    files = [child for child in path.rglob("*") if child.is_file()]
    if not files:
        return False
    return all(
        child.suffix.casefold() in IGNORED_RESET_SIDECAR_EXTENSIONS
        and not is_audio_file(child)
        and not is_video_file(child)
        for child in files
    )


def _match_tokens(value: str) -> set[str]:
    ignored = {
        "1080p",
        "2160p",
        "720p",
        "480p",
        "4k",
        "bluray",
        "web",
        "webrip",
        "hdtv",
        "mp4",
        "mkv",
        "season",
        "series",
        "tv",
    }
    tokens = []
    current = []
    for char in value.casefold():
        if char.isalnum():
            current.append(char)
        elif current:
            tokens.append("".join(current))
            current = []
    if current:
        tokens.append("".join(current))
    return {
        token
        for token in tokens
        if len(token) > 2 and token not in ignored and not token.isdigit()
    }


def _sidecar_ingest_match(show_folder: Path) -> Path | None:
    if not settings.ingest_root.exists():
        return None
    show_tokens = _match_tokens(show_folder.name)
    if not show_tokens:
        return None
    candidates = []
    for candidate in settings.ingest_root.iterdir():
        if not _is_sidecar_only_ingest_folder(candidate):
            continue
        candidate_tokens = _match_tokens(candidate.name)
        if show_tokens.issubset(candidate_tokens):
            candidates.append(candidate)
    return candidates[0] if len(candidates) == 1 else None


def _orphan_tv_library_restore_plan(
    moves: list[MoveAction],
) -> list[OrphanLibraryRestore]:
    if not settings.tv_dir.exists():
        return []
    tracked_destinations = {
        Path(move.destination_path).resolve()
        for move in moves
        if move.status == "completed"
    }
    plan = []
    for show_folder in settings.tv_dir.iterdir():
        if not show_folder.is_dir():
            continue
        media_files = [
            path
            for path in show_folder.rglob("*")
            if path.is_file() and is_video_file(path)
        ]
        if not media_files:
            continue
        if any(path.resolve() in tracked_destinations for path in media_files):
            continue
        ingest_folder = _sidecar_ingest_match(show_folder)
        if not ingest_folder:
            continue
        plan.append(
            OrphanLibraryRestore(
                library_root=show_folder,
                ingest_root=ingest_folder,
                files=tuple(
                    (
                        source,
                        ingest_folder / source.relative_to(show_folder),
                    )
                    for source in media_files
                ),
            )
        )
    return plan


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
    orphan_tv_plan = _orphan_tv_library_restore_plan(moves)
    orphan_tv_file_count = sum(len(item.files) for item in orphan_tv_plan)
    untracked_media = _untracked_library_media(moves)
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
            restored_files=(
                len(restorable) + len(quarantine_plan) + orphan_tv_file_count
            ),
            recovered_media_files=0,
            untracked_library_media_files=len(untracked_media),
            removed_reports=len(batch_ids),
            removed_move_logs=0,
            removed_library_metadata=0,
            removed_empty_dirs=0,
            cleared_batches=len(batch_ids),
            message=(
                "Dry run only. "
                f"Would restore "
                f"{len(restorable) + len(quarantine_plan) + orphan_tv_file_count} "
                "file(s) to ingest and "
                f"clear {len(batch_ids)} ingest batch(es)."
            ),
        )

    recovery_root = _reset_recovery_root()
    recovered_media_files = 0
    restore_targets = [
        Path(move.source_path)
        for move in restorable
    ] + [
        original
        for _, original in quarantine_plan
    ] + [
        destination
        for orphan in orphan_tv_plan
        for _, destination in orphan.files
    ]
    for target in sorted(
        {path for path in restore_targets if path.exists()},
        key=lambda path: len(path.parts),
        reverse=True,
    ):
        recovered_media_files += _move_existing_ingest_path_to_recovery(
            target,
            recovery_root,
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
        original.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(quarantine_source), str(original))
        restored_files += 1

    for orphan in orphan_tv_plan:
        for library_source, ingest_destination in orphan.files:
            ingest_destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(library_source), str(ingest_destination))
            restored_files += 1

    completion_errors = _validate_restore_completion(moves, quarantine_plan)
    for orphan in orphan_tv_plan:
        for library_source, ingest_destination in orphan.files:
            if not ingest_destination.exists():
                completion_errors.append(
                    f"Restored orphan TV file is missing: {ingest_destination}"
                )
            if library_source.exists():
                completion_errors.append(
                    f"Orphan TV library source still exists after restore: {library_source}"
                )
    remaining_untracked_media = _untracked_library_media(moves)
    if completion_errors:
        db.rollback()
        raise DevResetBlockedError(completion_errors)

    # Destructive cleanup happens only after every file restore is verified.
    removed_reports = (
        _remove_batch_reports(batch_ids)
        + _remove_quarantine_reports(batch_ids)
    )
    removed_move_logs = _remove_move_logs()
    removed_library_metadata = _remove_orphaned_library_metadata()
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
        recovered_media_files=recovered_media_files,
        untracked_library_media_files=len(remaining_untracked_media),
        removed_reports=removed_reports,
        removed_move_logs=removed_move_logs,
        removed_library_metadata=removed_library_metadata,
        removed_empty_dirs=removed_empty_dirs,
        cleared_batches=len(batch_ids),
        message=(
            "All ingest test data reset. "
            f"Restored {restored_files} file(s) and cleared "
            f"{len(batch_ids)} batch(es). Removed "
            f"{removed_library_metadata} stale library metadata item(s). "
            f"Recovered {recovered_media_files} existing ingest media file(s) "
            "to _RECOVERY. Preserved "
            f"{len(remaining_untracked_media)} untracked library media file(s). "
            "Source files were not deleted."
        ),
    )


def reset_music_test_data(db: Session, *, apply: bool) -> DevResetSummary:
    """Compatibility alias for existing scripts and older API clients."""
    return reset_test_data(db, apply=apply)
