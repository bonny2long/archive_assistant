import json
import shutil
from pathlib import Path
from sqlalchemy.orm import Session, selectinload
from app.core.config import settings
from app.core.time import now_utc, serialize_utc
from app.models.archive import ArchiveItem, IngestBatch, MoveAction
from app.services.music_metadata import (
    canonical_album_key,
    canonical_artist_key,
    is_artwork_file,
    music_track_numbers,
    music_track_filename,
    sort_music_tracks,
)


def _safe_path_part(value: str) -> str:
    return "".join(c if c not in '<>:"/\\|?*' else "_" for c in value).strip()


def _discography_album_destination(root: Path, album_metadata: dict) -> Path:
    album = _safe_path_part(
        str(album_metadata.get("album") or album_metadata.get("source_folder") or "Unknown Album")
    )
    year = str(album_metadata.get("year") or "")[:4]
    release_type = str(album_metadata.get("release_type") or "album").lower()
    buckets = {
        "album": "Albums",
        "single": "Singles",
        "ep": "EPs",
        "compilation": "Compilations",
        "live": "Live",
        "other": "Other",
    }
    bucket = root / buckets.get(release_type, "Other")
    if release_type in {"single", "ep"} and year.isdigit():
        return bucket / year / album
    folder = f"{year} - {album}" if year.isdigit() else album
    return bucket / folder


def _discography_quarantine_destination(
    artist: str,
    album_metadata: dict,
    source_filename: str,
) -> Path:
    source_folder = _safe_path_part(
        str(album_metadata.get("source_folder") or "Unknown Release")
    )
    return (
        settings.quarantine_discography_dir
        / _safe_path_part(artist)
        / source_folder
        / source_filename
    )


def _move_discography_batch(
    db: Session,
    batch: IngestBatch,
) -> tuple[list[str], list[str], list[str]]:
    destination = Path(batch.suggested_destination or "")
    if not batch.suggested_destination:
        return [], [], ["Missing suggested discography destination"]
    if destination.exists():
        metadata = dict(batch.metadata_json or {})
        warnings = list(metadata.get("metadata_warnings", []))
        warnings.append("discography_destination_exists")
        metadata["metadata_warnings"] = list(dict.fromkeys(warnings))
        metadata["metadata_alerts"] = [
            *list(metadata.get("metadata_alerts", [])),
            {
                "type": "discography_destination_exists",
                "message": "Discography folder already exists. Review required before merging.",
                "existing_path": str(destination),
            },
        ]
        batch.metadata_json = metadata
        batch.status = "needs_metadata_review"
        batch.updated_at = now_utc()
        db.commit()
        return [], [], ["Discography destination already exists"]

    planned = []
    seen_destinations = set()
    collection_artist = str((batch.metadata_json or {}).get("artist") or "Unknown Artist")
    album_disc_counts: dict[str, int] = {}
    for ingest_file in batch.files:
        if ingest_file.detected_role == "artwork":
            continue
        metadata = ingest_file.metadata_json or {}
        album_metadata = metadata.get("_discography_album") or {}
        source_folder = str(album_metadata.get("source_folder") or "")
        disc, _ = music_track_numbers(metadata, ingest_file.file_name)
        album_disc_counts[source_folder] = max(
            album_disc_counts.get(source_folder, 1),
            disc,
        )

    for ingest_file in sort_music_tracks(batch.files):
        metadata = ingest_file.metadata_json or {}
        album_metadata = metadata.get("_discography_album") or {}
        included = bool(album_metadata.get("include", True))
        release_type = str(album_metadata.get("release_type") or "album").lower()
        disc_count = album_disc_counts.get(
            str(album_metadata.get("source_folder") or ""),
            1,
        )
        if not included or release_type == "exclude":
            destination_file = _discography_quarantine_destination(
                collection_artist,
                album_metadata,
                ingest_file.file_name,
            )
            quarantined = True
        else:
            album_destination = _discography_album_destination(
                destination,
                album_metadata,
            )
            destination_file = album_destination / (
                ingest_file.file_name
                if ingest_file.detected_role == "artwork"
                else music_track_filename(
                    metadata,
                    ingest_file.extension,
                    disc_count,
                    ingest_file.file_name,
                )
            )
            quarantined = False
        destination_key = str(destination_file).lower()
        if destination_key in seen_destinations or destination_file.exists():
            batch_metadata = dict(batch.metadata_json or {})
            warnings = list(batch_metadata.get("metadata_warnings", []))
            warnings.append("destination_file_conflict")
            batch_metadata["metadata_warnings"] = list(dict.fromkeys(warnings))
            batch.metadata_json = batch_metadata
            batch.status = "needs_metadata_review"
            batch.updated_at = now_utc()
            db.commit()
            return [], [], [f"Destination file conflict: {destination_file}"]
        seen_destinations.add(destination_key)
        planned.append((ingest_file, destination_file, quarantined, release_type))

    moved_files = []
    quarantined_files = []
    failed_files = []
    release_type_counts: dict[str, int] = {}
    completed_release_folders: set[tuple[str, str]] = set()
    for ingest_file, destination_file, quarantined, release_type in planned:
        source = Path(ingest_file.file_path)
        if not source.exists():
            failed_files.append(f"Source not found: {source}")
            continue
        destination_file.parent.mkdir(parents=True, exist_ok=True)
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
            action.completed_at = now_utc()
            if quarantined:
                quarantined_files.append(str(destination_file))
            else:
                moved_files.append(str(destination_file))
                album_metadata = (ingest_file.metadata_json or {}).get(
                    "_discography_album",
                    {},
                )
                release_key = (
                    release_type,
                    str(album_metadata.get("source_folder") or ""),
                )
                if (
                    ingest_file.detected_role != "artwork"
                    and release_key not in completed_release_folders
                ):
                    completed_release_folders.add(release_key)
                    release_type_counts[release_type] = (
                        release_type_counts.get(release_type, 0) + 1
                    )
        except Exception as exc:
            action.status = "failed"
            action.error_message = str(exc)
            failed_files.append(f"Failed to move {source}: {exc}")
            db.flush()

    metadata_dir = destination / "metadata"
    metadata_dir.mkdir(parents=True, exist_ok=True)
    metadata = batch.metadata_json or {}
    (metadata_dir / "discography-move-log.json").write_text(
        json.dumps(
            {
                "type": "discography_move",
                "batch_id": batch.id,
                "artist": metadata.get("artist"),
                "albums_completed": release_type_counts.get("album", 0),
                "singles_completed": release_type_counts.get("single", 0),
                "eps_completed": release_type_counts.get("ep", 0),
                "excluded_releases": len(
                    {
                        str(
                            ((ingest_file.metadata_json or {}).get(
                                "_discography_album",
                                {},
                            )).get("source_folder") or ""
                        )
                        for ingest_file in batch.files
                        if not bool(
                            ((ingest_file.metadata_json or {}).get(
                                "_discography_album",
                                {},
                            )).get("include", True)
                        )
                        or str(
                            ((ingest_file.metadata_json or {}).get(
                                "_discography_album",
                                {},
                            )).get("release_type") or ""
                        ).lower() == "exclude"
                    }
                ),
                "summary": {
                    "tracks_moved": sum(
                        not is_artwork_file(Path(path)) for path in moved_files
                    ),
                    "artwork_moved": sum(
                        is_artwork_file(Path(path)) for path in moved_files
                    ),
                    "failed": len(failed_files),
                },
                "tracks_completed": sum(
                    not is_artwork_file(Path(path)) for path in moved_files
                ),
                "artwork_completed": sum(
                    is_artwork_file(Path(path)) for path in moved_files
                ),
                "failed_moves": len(failed_files),
                "quarantined_files": quarantined_files,
                "release_type_counts": release_type_counts,
                "warnings": metadata.get("metadata_warnings", []),
                "destination": str(destination),
                "moved_files": moved_files,
                "actions": [
                    {
                        "type": "artwork" if is_artwork_file(Path(path)) else "track",
                        "destination": path,
                        "status": "completed",
                    }
                    for path in moved_files
                ],
                "failed_files": failed_files,
                "moved_at": serialize_utc(now_utc()),
            },
            indent=2,
            default=str,
        ),
        encoding="utf-8",
    )
    return moved_files, quarantined_files, failed_files


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
        name = (
            ingest_file.file_name
            if ingest_file.detected_role == "artwork"
            else music_track_filename(
                metadata,
                ingest_file.extension,
                disc_count,
                ingest_file.file_name,
            )
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
                batch.updated_at = now_utc()
                db.commit()
                errors.append(f"Batch {batch.id}: weak metadata must be confirmed before move")
                continue

            if batch.detected_type == "music_discography":
                moved_files, quarantined_files, failed_files = (
                    _move_discography_batch(db, batch)
                )
                if not moved_files and not quarantined_files:
                    if batch.status != "needs_metadata_review":
                        batch.status = "move_failed"
                    batch.updated_at = now_utc()
                    db.commit()
                    errors.extend(f"Batch {batch.id}: {error}" for error in failed_files)
                    continue

                batch.status = "move_failed" if failed_files else "moved"
                batch.updated_at = now_utc()
                for dest_path in moved_files:
                    dest = Path(dest_path)
                    if is_artwork_file(dest):
                        continue
                    metadata = batch.metadata_json or {}
                    db.add(
                        ArchiveItem(
                            media_type="music",
                            title=dest.parent.name,
                            creator=metadata.get("artist"),
                            year=dest.parent.name[:4] if dest.parent.name[:4].isdigit() else None,
                            source_kind=batch.source_kind,
                            final_path=str(dest),
                            metadata_status="discography",
                        )
                    )
                db.commit()
                moved += 1
                if failed_files:
                    errors.extend(f"Batch {batch.id}: {error}" for error in failed_files)
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
                batch.updated_at = now_utc()
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
                batch.updated_at = now_utc()
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
                new_name = (
                    ingest_file.file_name
                    if ingest_file.detected_role == "artwork"
                    else music_track_filename(
                        meta,
                        ingest_file.extension,
                        disc_count,
                        ingest_file.file_name,
                    )
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
                    action.completed_at = now_utc()
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

            batch.updated_at = now_utc()
            db.flush()

            _write_move_log(batch, album_meta, moved_files, failed_files)

            for dest_path in moved_files:
                dest = Path(dest_path)
                if is_artwork_file(dest):
                    continue
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
            batch.updated_at = now_utc()
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
                "artwork_count": album_meta.get("artwork_count", 0),
                "summary": {
                    "tracks_moved": sum(
                        not is_artwork_file(Path(path)) for path in moved_files
                    ),
                    "artwork_moved": sum(
                        is_artwork_file(Path(path)) for path in moved_files
                    ),
                    "failed": len(failed_files),
                },
                "source_paths": [
                    str(f.file_path) for f in sort_music_tracks(batch.files)
                ],
                "destination_path": str(destination_dir),
                "moved_files": moved_files,
                "actions": [
                    {
                        "type": "artwork" if is_artwork_file(Path(path)) else "track",
                        "destination": path,
                        "status": "completed",
                    }
                    for path in moved_files
                ],
                "failed_files": failed_files,
                "status": "completed" if not failed_files else "partial",
                "moved_at": serialize_utc(now_utc()),
                "album_metadata": album_meta,
            },
            indent=2,
            default=str,
        ),
        encoding="utf-8",
    )
