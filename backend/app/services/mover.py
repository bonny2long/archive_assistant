import json
import shutil
from datetime import datetime, timezone
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
from app.services.video_metadata import safe_tv_path_part


def _safe_path_part(value: str) -> str:
    return "".join(c if c not in '<>:"/\\|?*' else "_" for c in value).strip()


def _path_key(path: Path) -> str:
    return str(path.resolve()).casefold()


def _unique_artwork_destination(
    preferred: Path,
    reserved: set[str],
) -> Path:
    if _path_key(preferred) not in reserved and not preferred.exists():
        return preferred
    for index in range(2, 1000):
        candidate = preferred.with_name(
            f"{preferred.stem}__{index:02d}{preferred.suffix}"
        )
        if _path_key(candidate) not in reserved and not candidate.exists():
            return candidate
    raise RuntimeError(f"Could not allocate artwork destination for {preferred}")


def _completed_move_destination(
    db: Session,
    batch_id: int,
    source: Path,
) -> Path | None:
    action = (
        db.query(MoveAction)
        .filter(
            MoveAction.batch_id == batch_id,
            MoveAction.source_path == str(source),
            MoveAction.status == "completed",
        )
        .order_by(MoveAction.id.desc())
        .first()
    )
    if not action:
        return None
    destination = Path(action.destination_path)
    return destination if destination.exists() else None


def _move_movie_batch(
    db: Session,
    batch: IngestBatch,
) -> tuple[list[str], list[str]]:
    metadata = dict(batch.metadata_json or {})
    title = str(metadata.get("title") or "Unknown Movie")
    year = str(metadata.get("year") or "")[:4]
    destination = settings.movies_dir / _safe_path_part(
        f"{year or 'Unknown Year'} - {title}"
    )
    batch.suggested_destination = str(destination)
    if destination.exists() and not _same_batch_retry(db, batch.id, destination):
        warnings = list(metadata.get("metadata_warnings", []))
        warnings.append("movie_destination_exists")
        metadata["metadata_warnings"] = list(dict.fromkeys(warnings))
        metadata["metadata_alerts"] = [
            *[
                alert
                for alert in (metadata.get("metadata_alerts") or [])
                if not (
                    isinstance(alert, dict)
                    and alert.get("type") == "movie_destination_exists"
                )
            ],
            {
                "type": "movie_destination_exists",
                "message": (
                    "Movie folder already exists. No files were moved or overwritten."
                ),
                "existing_path": str(destination),
            },
        ]
        batch.metadata_json = metadata
        batch.status = "needs_metadata_review"
        batch.updated_at = now_utc()
        db.commit()
        return [], [f"Movie destination already exists: {destination}"]

    planned = []
    moved_files = []
    failed_files = []
    reserved: set[str] = set()
    for ingest_file in batch.files:
        source = Path(ingest_file.file_path)
        completed = _completed_move_destination(db, batch.id, source)
        if not source.exists() and completed:
            moved_files.append(str(completed))
            reserved.add(_path_key(completed))
            continue
        destination_file = destination / ingest_file.file_name
        if ingest_file.detected_role in {"movie_artwork", "subtitle"}:
            destination_file = _unique_artwork_destination(
                destination_file,
                reserved,
            )
        elif _path_key(destination_file) in reserved or destination_file.exists():
            metadata = dict(batch.metadata_json or {})
            warnings = list(metadata.get("metadata_warnings", []))
            warnings.append("destination_file_conflict")
            metadata["metadata_warnings"] = list(dict.fromkeys(warnings))
            batch.metadata_json = metadata
            batch.status = "needs_metadata_review"
            batch.updated_at = now_utc()
            db.commit()
            return [], [f"Destination file conflict: {destination_file}"]
        reserved.add(_path_key(destination_file))
        planned.append((ingest_file, destination_file))

    destination.mkdir(parents=True, exist_ok=True)
    for ingest_file, destination_file in planned:
        source = Path(ingest_file.file_path)
        if not source.exists():
            failed_files.append(f"Source not found: {source}")
            continue
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
            action.status = "failed"
            action.error_message = str(exc)
            failed_files.append(f"Failed to move {source}: {exc}")
            db.flush()

    metadata_dir = destination / "metadata"
    metadata_dir.mkdir(parents=True, exist_ok=True)
    metadata = batch.metadata_json or {}
    role_by_source = {
        ingest_file.file_path: ingest_file.detected_role
        for ingest_file in batch.files
    }
    completed_actions = (
        db.query(MoveAction)
        .filter(
            MoveAction.batch_id == batch.id,
            MoveAction.status == "completed",
        )
        .all()
    )
    completed_roles = [
        role_by_source.get(action.source_path)
        for action in completed_actions
    ]
    (metadata_dir / f"batch-{batch.id}-movie-move-log.json").write_text(
        json.dumps(
            {
                "batch_id": batch.id,
                "media_type": "video_movie",
                "title": metadata.get("title"),
                "year": metadata.get("year"),
                "summary": {
                    "video_files_moved": sum(
                        role == "video_file" for role in completed_roles
                    ),
                    "artwork_moved": sum(
                        role == "movie_artwork" for role in completed_roles
                    ),
                    "subtitles_moved": sum(
                        role == "subtitle" for role in completed_roles
                    ),
                    "ignored_sidecars": metadata.get("ignored_sidecar_count", 0),
                    "failed": len(failed_files),
                },
                "destination_path": str(destination),
                "moved_files": moved_files,
                "failed_files": failed_files,
                "moved_at": serialize_utc(now_utc()),
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    return moved_files, failed_files


def _tv_season_destination(root: Path, season_number: int) -> Path:
    return root / f"Season {season_number:02d}"


def _tv_special_group_destination(root: Path, group: str) -> Path:
    mapping = {
        "specials": "Specials",
        "oad": "Specials",
        "ova": "Specials",
        "extras": "Extras",
    }
    return root / mapping.get(group, "Specials")


def _tv_episode_destination(
    destination: Path,
    ingest_file,
) -> Path | None:
    metadata = ingest_file.metadata_json or {}
    season_number = metadata.get("season_number")
    is_special = bool(metadata.get("is_special"))
    special_label = str(metadata.get("special_label") or "").strip()
    preserve = bool(metadata.get("preserve_source_filename"))
    destination_group = str(metadata.get("destination_group") or "").strip()

    suffix = Path(ingest_file.file_name).suffix.lower()

    # Preserve original filename — just need a season/group folder
    if preserve:
        if season_number is not None:
            folder = _tv_season_destination(destination, int(season_number))
        elif destination_group in {"specials", "oad", "extras"}:
            folder = _tv_special_group_destination(destination, destination_group)
        else:
            return None
        return folder / ingest_file.file_name

    # Specials going to destination group folder (Specials / OADs / OVAs / Extras)
    if is_special and destination_group in {"specials", "oad", "extras"}:
        episode_title = str(metadata.get("episode_title") or "").strip()
        if special_label:
            file_name = (
                f"{special_label} - {safe_tv_path_part(episode_title)}{suffix}"
                if episode_title
                else f"{special_label}{suffix}"
            )
        else:
            file_name = ingest_file.file_name
        return _tv_special_group_destination(destination, destination_group) / file_name

    # Specials inside a season folder (e.g. S01E13.5, S04SP01)
    if is_special and special_label:
        if season_number is None:
            return None
        episode_title = str(metadata.get("episode_title") or "").strip()
        file_name = (
            f"{special_label} - {safe_tv_path_part(episode_title)}{suffix}"
            if episode_title
            else f"{special_label}{suffix}"
        )
        return _tv_season_destination(destination, int(season_number)) / file_name

    # Normal episode
    episode_code = metadata.get("episode_code")
    if season_number is None or not episode_code:
        return None
    episode_title = str(metadata.get("episode_title") or "").strip()
    file_name = (
        f"{episode_code} - {safe_tv_path_part(episode_title)}{suffix}"
        if episode_title
        else f"{episode_code}{suffix}"
    )
    return _tv_season_destination(destination, int(season_number)) / file_name


def _tv_subtitle_destination(
    destination: Path,
    ingest_file,
) -> Path | None:
    metadata = ingest_file.metadata_json or {}
    season_number = metadata.get("season_number")
    is_special = bool(metadata.get("is_special"))
    destination_group = str(metadata.get("destination_group") or "").strip()

    episode_code = metadata.get("episode_code")
    episode_title = str(metadata.get("episode_title") or "").strip()
    language_suffix = str(metadata.get("language_suffix") or "")
    suffix = Path(ingest_file.file_name).suffix.lower()

    if is_special and destination_group in {"oad", "ova", "extras", "specials"}:
        # Subtitle for a special — place alongside the episode
        file_name = (
            f"{episode_code}{language_suffix}{suffix}"
            if episode_code
            else ingest_file.file_name
        )
        return _tv_special_group_destination(destination, destination_group) / file_name

    if season_number is None:
        return None

    if episode_code:
        title_part = (
            f" - {safe_tv_path_part(episode_title)}"
            if episode_title
            else ""
        )
        file_name = (
            f"{episode_code}{title_part}{language_suffix}{suffix}"
        )
    else:
        file_name = ingest_file.file_name
    return _tv_season_destination(
        destination,
        int(season_number),
    ) / file_name


def _tv_artwork_destination(
    batch: IngestBatch,
    destination: Path,
    ingest_file,
) -> Path:
    file_metadata = ingest_file.metadata_json or {}
    season_number = file_metadata.get("season_number")
    artwork_scope = file_metadata.get("artwork_scope")
    parent = (
        _tv_season_destination(destination, int(season_number))
        if artwork_scope == "season" and season_number is not None
        else destination
    )
    return parent / ingest_file.file_name


def _validate_tv_file_metadata_ready(batch: IngestBatch) -> list[str]:
    errors: list[str] = []
    for ingest_file in batch.files:
        if ingest_file.detected_role != "tv_episode":
            continue
        meta = ingest_file.metadata_json or {}
        if not meta.get("include", True):
            continue
        source = ingest_file.file_name
        is_special = bool(meta.get("is_special"))
        preserve = bool(meta.get("preserve_source_filename"))
        destination_group = str(meta.get("destination_group") or "").strip()
        season_number = meta.get("season_number")
        episode_number = meta.get("episode_number")
        episode_code = str(meta.get("episode_code") or "").strip()
        special_label = str(meta.get("special_label") or "").strip()
        if preserve:
            if season_number is None and destination_group not in {"specials", "oad", "extras"}:
                errors.append(f"{source}: preserve original filename requires season number or special group")
            continue
        if is_special:
            if destination_group in {"specials", "oad", "extras"}:
                if not special_label and not episode_code:
                    errors.append(f"{source}: special item requires special_label or episode_code")
            elif destination_group in {"season", ""}:
                if season_number is None:
                    errors.append(f"{source}: season special requires season number")
                if not special_label and not episode_code:
                    errors.append(f"{source}: season special requires special_label or episode_code")
            else:
                errors.append(f"{source}: invalid destination group {destination_group}")
            continue
        if season_number is None:
            errors.append(f"{source}: missing season number")
        if episode_number is None:
            errors.append(f"{source}: missing episode number")
        if not episode_code:
            errors.append(f"{source}: missing episode code")
    return errors


def _move_tv_batch(
    db: Session,
    batch: IngestBatch,
) -> tuple[list[str], list[str]]:
    metadata = dict(batch.metadata_json or {})
    show_title = str(metadata.get("show_title") or "Unknown TV Show")
    destination = settings.tv_dir / safe_tv_path_part(show_title)
    batch.suggested_destination = str(destination)

    validation_errors = _validate_tv_file_metadata_ready(batch)
    if validation_errors:
        metadata["tv_file_metadata_not_ready"] = validation_errors
        warnings = list(metadata.get("metadata_warnings", []))
        warnings.append("tv_file_metadata_not_ready")
        metadata["metadata_warnings"] = list(dict.fromkeys(warnings))
        batch.metadata_json = metadata
        batch.status = "needs_metadata_review"
        batch.updated_at = now_utc()
        db.commit()
        return [], validation_errors

    if destination.exists() and not _same_batch_retry(db, batch.id, destination):
        warnings = list(metadata.get("metadata_warnings", []))
        warnings.append("tv_destination_exists")
        metadata["metadata_warnings"] = list(dict.fromkeys(warnings))
        metadata["metadata_alerts"] = [
            *[
                alert
                for alert in (metadata.get("metadata_alerts") or [])
                if not (
                    isinstance(alert, dict)
                    and alert.get("type") == "tv_destination_exists"
                )
            ],
            {
                "type": "tv_destination_exists",
                "message": (
                    "TV show folder already exists. No files were moved or overwritten."
                ),
                "existing_path": str(destination),
            },
        ]
        batch.metadata_json = metadata
        batch.status = "needs_metadata_review"
        batch.updated_at = now_utc()
        db.commit()
        return [], [f"TV destination already exists: {destination}"]

    planned = []
    moved_files = []
    failed_files = []
    reserved: set[str] = set()
    for ingest_file in batch.files:
        source = Path(ingest_file.file_path)
        completed = _completed_move_destination(db, batch.id, source)
        if not source.exists() and completed:
            moved_files.append(str(completed))
            reserved.add(_path_key(completed))
            continue

        # Skip episodes the user excluded during review
        if ingest_file.detected_role == "tv_episode":
            ep_meta = ingest_file.metadata_json or {}
            if not ep_meta.get("include", True):
                continue
            destination_file = _tv_episode_destination(
                destination,
                ingest_file,
            )
            if destination_file is None:
                return [], [
                    f"TV episode metadata missing for {ingest_file.file_name}"
                ]
        elif ingest_file.detected_role == "tv_subtitle":
            destination_file = _tv_subtitle_destination(
                destination,
                ingest_file,
            )
            if destination_file is None:
                return [], [
                    f"TV subtitle season missing for {ingest_file.file_name}"
                ]
        elif ingest_file.detected_role == "tv_artwork":
            destination_file = _tv_artwork_destination(
                batch,
                destination,
                ingest_file,
            )
            destination_file = _unique_artwork_destination(
                destination_file,
                reserved,
            )
        else:
            continue

        destination_key = _path_key(destination_file)
        if destination_key in reserved or destination_file.exists():
            metadata = dict(batch.metadata_json or {})
            warnings = list(metadata.get("metadata_warnings", []))
            warnings.append("destination_file_conflict")
            metadata["metadata_warnings"] = list(dict.fromkeys(warnings))
            batch.metadata_json = metadata
            batch.status = "needs_metadata_review"
            batch.updated_at = now_utc()
            db.commit()
            return [], [f"Destination file conflict: {destination_file}"]
        reserved.add(destination_key)
        planned.append((ingest_file, destination_file))

    for ingest_file, destination_file in planned:
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
            moved_files.append(str(destination_file))
        except Exception as exc:
            action.status = "failed"
            action.error_message = str(exc)
            failed_files.append(f"Failed to move {source}: {exc}")
            db.flush()

    metadata_dir = destination / "metadata"
    metadata_dir.mkdir(parents=True, exist_ok=True)
    role_by_source = {
        ingest_file.file_path: ingest_file.detected_role
        for ingest_file in batch.files
    }
    completed_actions = (
        db.query(MoveAction)
        .filter(
            MoveAction.batch_id == batch.id,
            MoveAction.status == "completed",
        )
        .all()
    )
    completed_roles = [
        role_by_source.get(action.source_path)
        for action in completed_actions
    ]
    move_files = [
        {
            "source": action.source_path,
            "destination": action.destination_path,
            "role": role_by_source.get(action.source_path),
            "status": action.status,
        }
        for action in completed_actions
    ]
    (metadata_dir / f"batch-{batch.id}-tv-move-log.json").write_text(
        json.dumps(
            {
                "batch_id": batch.id,
                "media_type": "tv_show",
                "show_title": show_title,
                "review_confirmed": bool(metadata.get("review_confirmed", False)),
                "metadata_quality": str(metadata.get("metadata_quality", "weak")),
                "season_count": metadata.get("season_count", 0),
                "episode_count": metadata.get("episode_count", 0),
                "subtitle_count": metadata.get("subtitle_count", 0),
                "artwork_count": metadata.get("artwork_count", 0),
                "ignored_sidecar_count": metadata.get(
                    "ignored_sidecar_count",
                    0,
                ),
                "ignored_corrupt_video_count": metadata.get(
                    "ignored_corrupt_video_count",
                    0,
                ),
                "ignored_corrupt_video_files_preserved_in_ingest": bool(
                    metadata.get("ignored_corrupt_video_count", 0)
                ),
                "warnings": metadata.get("metadata_warnings", []),
                "special_count": metadata.get("special_episode_count", 0),
                "excluded_count": sum(
                    not bool(e.get("include", True))
                    for season in metadata.get("seasons", [])
                    if isinstance(season, dict)
                    for e in season.get("episodes", [])
                ),
                "preserved_filename_count": sum(
                    bool(e.get("preserve_source_filename"))
                    for season in metadata.get("seasons", [])
                    if isinstance(season, dict)
                    for e in season.get("episodes", [])
                ),
                "destination": str(destination),
                "seasons": [
                    {
                        "season_number": season.get("season_number"),
                        "episode_count": season.get("episode_count", 0),
                    }
                    for season in metadata.get("seasons", [])
                    if isinstance(season, dict)
                ],
                "files": move_files,
                "summary": {
                    "episodes_moved": sum(
                        role == "tv_episode" for role in completed_roles
                    ),
                    "subtitles_moved": sum(
                        role == "tv_subtitle" for role in completed_roles
                    ),
                    "artwork_moved": sum(
                        role == "tv_artwork" for role in completed_roles
                    ),
                    "ignored_sidecars": metadata.get(
                        "ignored_sidecar_count",
                        0,
                    ),
                    "failed": len(failed_files),
                },
                "destination_path": str(destination),
                "moved_files": moved_files,
                "failed_files": failed_files,
                "moved_at": serialize_utc(now_utc()),
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    return moved_files, failed_files


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
    if destination.exists() and not _same_batch_retry(db, batch.id, destination):
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
    already_completed = []
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
        source = Path(ingest_file.file_path)
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

        completed_destination = _completed_move_destination(
            db,
            batch.id,
            source,
        )
        if not source.exists() and completed_destination:
            already_completed.append(
                (
                    ingest_file,
                    completed_destination,
                    quarantined,
                    release_type,
                )
            )
            seen_destinations.add(_path_key(completed_destination))
            continue

        if ingest_file.detected_role == "artwork":
            destination_file = _unique_artwork_destination(
                destination_file,
                seen_destinations,
            )

        destination_key = _path_key(destination_file)
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
    for ingest_file, destination_file, quarantined, release_type in already_completed:
        if quarantined:
            quarantined_files.append(str(destination_file))
        else:
            moved_files.append(str(destination_file))
            if ingest_file.detected_role != "artwork":
                album_metadata = (ingest_file.metadata_json or {}).get(
                    "_discography_album",
                    {},
                )
                release_key = (
                    release_type,
                    str(album_metadata.get("source_folder") or ""),
                )
                if release_key not in completed_release_folders:
                    completed_release_folders.add(release_key)
                    release_type_counts[release_type] = (
                        release_type_counts.get(release_type, 0) + 1
                    )

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
    db: Session | None = None,
) -> list[str]:
    conflicts = []
    planned_names = set()
    for ingest_file in sort_music_tracks(batch.files):
        source = Path(ingest_file.file_path)
        if (
            db
            and not source.exists()
            and _completed_move_destination(db, batch.id, source)
        ):
            continue
        if ingest_file.detected_role == "artwork":
            continue
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


def _lock_metadata_for_move(batch: IngestBatch) -> None:
    metadata = dict(batch.metadata_json or {})
    metadata["review_confirmed"] = True
    metadata["metadata_locked_for_move"] = True
    metadata["metadata_locked_at"] = datetime.now(timezone.utc).isoformat()
    batch.metadata_json = metadata
    batch.metadata_confirmed = True


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

            if batch.detected_type == "video_movie":
                moved_files, failed_files = _move_movie_batch(db, batch)
                if not moved_files:
                    if batch.status != "needs_metadata_review":
                        batch.status = "move_failed"
                    batch.updated_at = now_utc()
                    db.commit()
                    errors.extend(
                        f"Batch {batch.id}: {error}" for error in failed_files
                    )
                    continue
                batch.status = "move_failed" if failed_files else "moved"
                batch.updated_at = now_utc()
                if batch.status == "moved":
                    _lock_metadata_for_move(batch)
                metadata = batch.metadata_json or {}
                if not (
                    db.query(ArchiveItem)
                    .filter(
                        ArchiveItem.final_path == str(
                            Path(batch.suggested_destination or "")
                        )
                    )
                    .first()
                ):
                    db.add(
                        ArchiveItem(
                            media_type="video",
                            title=metadata.get("title") or "Unknown Movie",
                            year=metadata.get("year"),
                            source_kind=batch.source_kind,
                            final_path=batch.suggested_destination or "",
                            metadata_status="basic",
                        )
                    )
                db.commit()
                moved += 1
                if failed_files:
                    errors.extend(
                        f"Batch {batch.id}: {error}" for error in failed_files
                    )
                continue

            if batch.detected_type == "video_tv_show":
                moved_files, failed_files = _move_tv_batch(db, batch)
                if not moved_files:
                    if batch.status != "needs_metadata_review":
                        batch.status = "move_failed"
                    batch.updated_at = now_utc()
                    db.commit()
                    errors.extend(
                        f"Batch {batch.id}: {error}" for error in failed_files
                    )
                    continue
                batch.status = "move_failed" if failed_files else "moved"
                batch.updated_at = now_utc()
                if batch.status == "moved":
                    _lock_metadata_for_move(batch)
                metadata = batch.metadata_json or {}
                if not (
                    db.query(ArchiveItem)
                    .filter(
                        ArchiveItem.final_path == str(
                            Path(batch.suggested_destination or "")
                        )
                    )
                    .first()
                ):
                    db.add(
                        ArchiveItem(
                            media_type="tv",
                            title=metadata.get("show_title") or "Unknown TV Show",
                            year=metadata.get("year"),
                            source_kind=batch.source_kind,
                            final_path=batch.suggested_destination or "",
                            metadata_status="basic",
                        )
                    )
                db.commit()
                moved += 1
                if failed_files:
                    errors.extend(
                        f"Batch {batch.id}: {error}" for error in failed_files
                    )
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
                    if (
                        db.query(ArchiveItem)
                        .filter(ArchiveItem.final_path == str(dest))
                        .first()
                    ):
                        continue
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
                db,
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
            reserved_destinations: set[str] = set()
            for ingest_file in ordered_files:
                source = Path(ingest_file.file_path)
                completed_destination = _completed_move_destination(
                    db,
                    batch.id,
                    source,
                )
                if not source.exists() and completed_destination:
                    moved_files.append(str(completed_destination))
                    reserved_destinations.add(_path_key(completed_destination))
                    continue
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
                if ingest_file.detected_role == "artwork":
                    destination_file = _unique_artwork_destination(
                        destination_file,
                        reserved_destinations,
                    )
                reserved_destinations.add(_path_key(destination_file))

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
                if (
                    db.query(ArchiveItem)
                    .filter(ArchiveItem.final_path == str(dest))
                    .first()
                ):
                    continue
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
