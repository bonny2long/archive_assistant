import json
import shutil
from datetime import datetime
from pathlib import Path
from sqlalchemy.orm import Session, selectinload
from app.core.config import settings
from app.models.archive import ArchiveItem, IngestBatch, MoveAction
from app.services.music_metadata import (
    canonical_album_key,
    canonical_artist_key,
    music_track_filename,
    sort_music_tracks,
)


def _format_bucket_for_path(path: Path) -> str:
    parts = {part.upper() for part in path.parts}
    return "FLAC" if "FLAC" in parts else "MP3"


def _destination_parts(destination: Path) -> tuple[str, str, str | None]:
    album_folder = destination.name
    artist_folder = destination.parent.name
    year = None
    album = album_folder
    if len(album_folder) >= 7 and album_folder[:4].isdigit() and album_folder[4:7] == " - ":
        year = album_folder[:4]
        album = album_folder[7:]
    return artist_folder, album, year


def _destination_conflict_payload(
    conflict_type: str,
    target_artist: str,
    target_album: str,
    existing_path: Path,
) -> dict:
    if conflict_type == "possible_artist_alias":
        return {
            "type": conflict_type,
            "message": (
                "Artist looks similar to existing folder: "
                f"{existing_path.name}."
            ),
            "existing_artist_folder": existing_path.name,
        }
    return {
        "type": conflict_type,
        "message": (
            "Possible duplicate destination found for "
            f"{target_artist} / {target_album}."
        ),
        "existing_path": str(existing_path),
    }


def _same_batch_retry(db: Session, batch_id: int, destination: Path) -> bool:
    prefix = str(destination)
    return (
        db.query(MoveAction)
        .filter(
            MoveAction.batch_id == batch_id,
            MoveAction.destination_path.like(f"{prefix}%"),
        )
        .count()
        > 0
    )


def _destination_identity(batch: IngestBatch) -> tuple[str, str, str | None, str]:
    metadata = batch.metadata_json or {}
    artist = str(metadata.get("artist") or metadata.get("albumartist") or "")
    album = str(metadata.get("album") or "")
    raw_year = str(metadata.get("year") or metadata.get("date") or "")[:4]
    year = raw_year if raw_year.isdigit() else None
    destination = Path(batch.suggested_destination or "")
    return artist, album, year, _format_bucket_for_path(destination)


def resolve_confirmed_destination_alias(
    db: Session,
    batch: IngestBatch,
) -> Path | None:
    if not batch.metadata_confirmed or not batch.suggested_destination:
        return None

    destination = Path(batch.suggested_destination)
    artist, album, year, format_bucket = _destination_identity(batch)
    artist_key = canonical_artist_key(artist)
    album_key = canonical_album_key(album)
    if not artist_key or not album_key:
        return None

    moved_batches = (
        db.query(IngestBatch)
        .filter(IngestBatch.id != batch.id, IngestBatch.status == "moved")
        .all()
    )
    for existing in moved_batches:
        if not existing.suggested_destination:
            continue
        existing_artist, existing_album, existing_year, existing_format = (
            _destination_identity(existing)
        )
        if (
            existing_format == format_bucket
            and canonical_artist_key(existing_artist) == artist_key
            and canonical_album_key(existing_album) == album_key
            and (not year or not existing_year or year == existing_year)
        ):
            resolved = Path(existing.suggested_destination)
            batch.suggested_destination = str(resolved)
            return resolved

    root = settings.music_flac_dir if format_bucket == "FLAC" else settings.music_mp3_dir
    if not root.exists():
        return None

    for artist_dir in sorted(path for path in root.iterdir() if path.is_dir()):
        if canonical_artist_key(artist_dir.name) != artist_key:
            continue
        for album_dir in sorted(path for path in artist_dir.iterdir() if path.is_dir()):
            _, existing_album, existing_year = _destination_parts(album_dir)
            if (
                canonical_album_key(existing_album) == album_key
                and (not year or not existing_year or year == existing_year)
            ):
                batch.suggested_destination = str(album_dir)
                return album_dir

        resolved = artist_dir / destination.name
        if resolved != destination:
            batch.suggested_destination = str(resolved)
            return resolved
    return None


def _destination_filename_conflicts(
    batch: IngestBatch,
    destination: Path,
    disc_count: int,
) -> list[str]:
    conflicts = []
    planned_names = set()
    for ingest_file in sort_music_tracks(batch.files):
        metadata = ingest_file.metadata_json or {}
        name = music_track_filename(
            metadata,
            ingest_file.extension,
            disc_count,
            ingest_file.file_name,
        )
        if name in planned_names:
            conflicts.append(f"Duplicate planned filename: {name}")
        planned_names.add(name)
        if (destination / name).exists():
            conflicts.append(f"Destination file already exists: {destination / name}")
    return conflicts


def find_possible_existing_destination(db: Session, batch: IngestBatch) -> dict | None:
    if not batch.suggested_destination:
        return None
    destination = Path(batch.suggested_destination)

    metadata = batch.metadata_json or {}
    target_artist = str(metadata.get("artist") or metadata.get("albumartist") or "")
    target_album = str(metadata.get("album") or "")
    target_year = str(metadata.get("year") or metadata.get("date") or "")[:4] or None
    if not target_artist or not target_album:
        return None

    target_format = _format_bucket_for_path(destination)
    target_artist_key = canonical_artist_key(target_artist)
    target_album_key = canonical_album_key(target_album)

    moved_batches = (
        db.query(IngestBatch)
        .filter(IngestBatch.id != batch.id, IngestBatch.status == "moved")
        .all()
    )
    for existing in moved_batches:
        existing_destination = Path(existing.suggested_destination or "")
        existing_meta = existing.metadata_json or {}
        existing_artist = str(
            existing_meta.get("artist") or existing_meta.get("albumartist") or ""
        )
        existing_album = str(existing_meta.get("album") or "")
        existing_year = (
            str(existing_meta.get("year") or existing_meta.get("date") or "")[:4]
            or None
        )
        if (
            _format_bucket_for_path(existing_destination) == target_format
            and canonical_artist_key(existing_artist) == target_artist_key
            and canonical_album_key(existing_album) == target_album_key
            and (not target_year or not existing_year or existing_year == target_year)
        ):
            return _destination_conflict_payload(
                "possible_duplicate_destination",
                target_artist,
                target_album,
                existing_destination,
            )

    root = settings.music_flac_dir if target_format == "FLAC" else settings.music_mp3_dir
    if not root.exists():
        return None

    for artist_dir in sorted(path for path in root.iterdir() if path.is_dir()):
        artist_key = canonical_artist_key(artist_dir.name)
        if artist_key != target_artist_key:
            continue
        if artist_dir.resolve() != destination.parent.resolve():
            return _destination_conflict_payload(
                "possible_artist_alias",
                target_artist,
                target_album,
                artist_dir,
            )
        for album_dir in sorted(path for path in artist_dir.iterdir() if path.is_dir()):
            existing_artist, existing_album, existing_year = _destination_parts(album_dir)
            if (
                canonical_artist_key(existing_artist) == target_artist_key
                and canonical_album_key(existing_album) == target_album_key
                and (not target_year or not existing_year or existing_year == target_year)
                and (
                    album_dir.resolve() != destination.resolve()
                    or not _same_batch_retry(db, batch.id, destination)
                )
            ):
                return _destination_conflict_payload(
                    "possible_duplicate_destination",
                    target_artist,
                    target_album,
                    album_dir,
                )
    return None


def move_approved_batches(db: Session) -> tuple[int, list[str]]:
    approved = (
        db.query(IngestBatch)
        .options(selectinload(IngestBatch.files))
        .filter(IngestBatch.status == "approved")
        .all()
    )
    moved = 0
    errors: list[str] = []

    for batch in approved:
        moved_files = []
        failed_files = []
        album_meta = batch.metadata_json or {}

        try:
            if (
                album_meta.get("metadata_quality") in {"weak", "broken"}
                and not batch.metadata_confirmed
            ):
                batch.status = "needs_metadata_review"
                batch.updated_at = datetime.utcnow()
                db.commit()
                errors.append(f"Batch {batch.id}: weak metadata must be confirmed before move")
                continue

            if not batch.suggested_destination:
                raise ValueError("Missing suggested destination")
            destination_dir = Path(batch.suggested_destination)

            resolved_destination = resolve_confirmed_destination_alias(db, batch)
            if resolved_destination:
                destination_dir = resolved_destination
                warnings = list(album_meta.get("metadata_warnings", []))
                warnings.append("possible_artist_alias_resolved")
                album_meta["metadata_warnings"] = list(dict.fromkeys(warnings))
                alerts = list(album_meta.get("metadata_alerts", []))
                alerts.append(
                    {
                        "type": "possible_artist_alias_resolved",
                        "message": (
                            "Confirmed metadata routed to existing canonical "
                            f"destination: {destination_dir}."
                        ),
                        "existing_path": str(destination_dir),
                    }
                )
                album_meta["metadata_alerts"] = alerts
                batch.metadata_json = album_meta
                db.flush()

            conflict = (
                None
                if resolved_destination
                else find_possible_existing_destination(db, batch)
            )
            if conflict:
                warnings = list(album_meta.get("metadata_warnings", []))
                warnings.append(conflict["type"])
                album_meta["metadata_warnings"] = list(dict.fromkeys(warnings))
                alerts = list(album_meta.get("metadata_alerts", []))
                alerts.append(conflict)
                album_meta["metadata_alerts"] = alerts
                batch.metadata_json = album_meta
                batch.status = "needs_metadata_review"
                batch.updated_at = datetime.utcnow()
                db.commit()
                errors.append(f"Batch {batch.id}: {conflict['message']}")
                continue

            disc_count = album_meta.get("disc_count", 1)
            filename_conflicts = _destination_filename_conflicts(
                batch,
                destination_dir,
                disc_count,
            )
            if filename_conflicts:
                warnings = list(album_meta.get("metadata_warnings", []))
                warnings.append("destination_file_conflict")
                album_meta["metadata_warnings"] = list(dict.fromkeys(warnings))
                album_meta["metadata_alerts"] = [
                    *list(album_meta.get("metadata_alerts", [])),
                    {
                        "type": "destination_file_conflict",
                        "message": "Move blocked because destination filenames already exist.",
                        "conflicts": filename_conflicts,
                    },
                ]
                batch.metadata_json = album_meta
                batch.status = "needs_metadata_review"
                batch.updated_at = datetime.utcnow()
                db.commit()
                errors.append(
                    f"Batch {batch.id}: destination filename conflict"
                )
                continue

            destination_dir.mkdir(parents=True, exist_ok=True)

            ordered_files = sort_music_tracks(batch.files)
            for ingest_file in ordered_files:
                source = Path(ingest_file.file_path)
                if not source.exists():
                    failed_files.append(f"Source not found: {source}")
                    continue

                meta = ingest_file.metadata_json or {}
                new_name = music_track_filename(
                    meta,
                    ingest_file.extension,
                    disc_count,
                    ingest_file.file_name,
                )
                destination_file = destination_dir / new_name

                action = MoveAction(
                    batch_id=batch.id,
                    source_path=str(source),
                    destination_path=str(destination_file),
                    status="running",
                )
                db.add(action)
                db.flush()

                try:
                    shutil.move(str(source), str(destination_file))
                    action.status = "completed"
                    action.completed_at = datetime.utcnow()
                    moved_files.append(str(destination_file))
                except Exception as exc:
                    failed_files.append(f"Failed to move {source}: {exc}")
                    action.status = "failed"
                    action.error_message = str(exc)
                    db.flush()
                    continue

            if failed_files or not moved_files:
                batch.status = "move_failed" if failed_files else "moved"
            else:
                batch.status = "moved"

            batch.updated_at = datetime.utcnow()
            db.flush()

            _write_move_log(batch, album_meta, moved_files, failed_files)

            for dest_path in moved_files:
                dest = Path(dest_path)
                metadata = batch.metadata_json or {}
                item = ArchiveItem(
                    media_type="music",
                    title=metadata.get("album") or dest.parent.name,
                    creator=metadata.get("artist") or metadata.get("album_artist"),
                    year=str(metadata.get("year") or "")[:4] or None,
                    primary_genre=metadata.get("genre"),
                    source_kind=batch.source_kind,
                    final_path=str(dest),
                    metadata_status="basic",
                )
                db.add(item)

            db.commit()
            if moved_files:
                moved += 1

        except Exception as exc:
            db.rollback()
            errors.append(f"Batch {batch.id}: {exc}")
            batch.status = "move_failed"
            batch.updated_at = datetime.utcnow()
            db.add(batch)
            db.commit()

    return moved, errors


def _write_move_log(batch: IngestBatch, album_meta: dict, moved_files: list[str], failed_files: list[str]) -> None:
    destination_dir = Path(batch.suggested_destination or "")
    metadata_dir = destination_dir / "metadata"
    metadata_dir.mkdir(exist_ok=True)
    (metadata_dir / f"batch-{batch.id}-move-log.json").write_text(
        json.dumps(
            {
                "batch_id": batch.id,
                "media_type": "music_album",
                "track_count": album_meta.get("track_count", len(moved_files)),
                "source_paths": [
                    str(f.file_path) for f in sort_music_tracks(batch.files)
                ],
                "destination_path": str(destination_dir),
                "moved_files": moved_files,
                "failed_files": failed_files,
                "status": "completed" if not failed_files else "partial",
                "moved_at": datetime.utcnow().isoformat(),
                "album_metadata": album_meta,
            },
            indent=2,
            default=str,
        ),
        encoding="utf-8",
    )
