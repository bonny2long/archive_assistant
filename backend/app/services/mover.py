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
from app.services.book_metadata import (
    book_destination,
    build_book_item_destination,
)
from app.services.audiobook_metadata import audiobook_destination
from app.services.library_manifest import (
    _relative_library_path,
    append_library_index_entry,
    write_library_manifest,
)
from app.services.move_manifest import write_move_manifest


def _safe_path_part(value: str) -> str:
    return "".join(c if c not in '<>:"/\\|?*' else "_" for c in value).strip()


def _path_key(path: Path) -> str:
    return str(path.resolve()).casefold()


def _safe_write_library_metadata(
    destination: Path,
    filename: str,
    payload: dict,
    index_dir: Path,
    index_entry: dict,
) -> None:
    library_path = _relative_library_path(destination)
    try:
        write_library_manifest(destination, filename, payload)
    except Exception as exc:
        print(f"Failed to write library manifest for {destination}: {exc}")
    try:
        append_library_index_entry(
            index_dir,
            {"library_path": library_path, **index_entry},
        )
    except Exception as exc:
        print(f"Failed to update library index for {destination}: {exc}")


def _record_move_manifest(
    db: Session,
    batch: IngestBatch,
    failed_files: list[str],
) -> list[str]:
    actions = (
        db.query(MoveAction)
        .filter(MoveAction.batch_id == batch.id)
        .order_by(MoveAction.id.asc())
        .all()
    )
    pointer, warnings = write_move_manifest(
        batch=batch,
        move_actions=actions,
        failed_messages=failed_files,
    )
    if pointer:
        metadata = dict(batch.metadata_json or {})
        metadata["move_manifest"] = pointer
        batch.metadata_json = metadata
        db.flush()
    return warnings


def _update_movie_library_manifest_pointers(
    db: Session,
    batch: IngestBatch,
) -> None:
    pointer = (batch.metadata_json or {}).get("move_manifest")
    if not pointer or batch.detected_type != "video_movie":
        return
    actions = (
        db.query(MoveAction)
        .filter(
            MoveAction.batch_id == batch.id,
            MoveAction.status == "completed",
        )
        .all()
    )
    manifest_paths = {
        Path(action.destination_path).parent / "metadata" / "movie.json"
        for action in actions
        if Path(action.destination_path).suffix.lower()
        in {".mkv", ".mp4", ".m4v", ".mov", ".avi", ".webm", ".ts", ".m2ts"}
    }
    for path in manifest_paths:
        if not path.exists():
            continue
        try:
            document = json.loads(path.read_text(encoding="utf-8"))
            document["move_manifest"] = pointer
            path.write_text(
                json.dumps(document, indent=2, ensure_ascii=False, default=str),
                encoding="utf-8",
            )
        except (OSError, ValueError):
            continue


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
    edition = str(metadata.get("edition") or "").strip()
    destination_part = (
        f"{year or 'Unknown Year'} - {title}"
        if not edition
        else f"{year or 'Unknown Year'} - {title} [{edition}]"
    )
    destination = settings.movies_dir / _safe_path_part(destination_part)
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
    role_by_destination = {
        action.destination_path: role_by_source.get(action.source_path)
        for action in completed_actions
    }
    (metadata_dir / f"batch-{batch.id}-movie-move-log.json").write_text(
        json.dumps(
            {
                "batch_id": batch.id,
                "media_type": "video_movie",
                "title": metadata.get("title"),
                "year": metadata.get("year"),
                "edition": metadata.get("edition"),
                "format": metadata.get("format"),
                "source_path": batch.source_path,
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
                "warnings": list(dict.fromkeys(
                    (metadata.get("metadata_warnings") or [])
                    + (metadata.get("metadata_alerts") or [])
                )),
                "moved_at": serialize_utc(now_utc()),
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    if moved_files and not failed_files:
        video_files = [
            path
            for path in moved_files
            if role_by_destination.get(path) == "video_file"
        ]
        _safe_write_library_metadata(
            destination,
            "movie.json",
            {
                "media_kind": "movie",
                "title": metadata.get("title") or title,
                "year": metadata.get("year") or year or None,
                "edition": metadata.get("edition") or None,
                "resolution": metadata.get("resolution"),
                "source": metadata.get("source"),
                "format": metadata.get("format"),
                "source_path": batch.source_path,
                "primary_video_file": (
                    Path(video_files[0]).name if video_files else None
                ),
                "video_file_count": sum(
                    role == "video_file" for role in completed_roles
                ),
                "artwork_count": sum(
                    role == "movie_artwork" for role in completed_roles
                ),
                "subtitle_count": sum(
                    role == "subtitle" for role in completed_roles
                ),
                "metadata_quality": metadata.get("metadata_quality", "reviewed"),
                "review_confirmed": bool(
                    batch.metadata_confirmed
                    or metadata.get("review_confirmed")
                ),
                "accepted_unknown_title": bool(
                    metadata.get("accepted_unknown_title")
                ),
                "accepted_unknown_year": bool(
                    metadata.get("accepted_unknown_year")
                ),
                "lookup_later": bool(metadata.get("lookup_later")),
                "batch_id": batch.id,
            },
            settings.movies_metadata_dir,
            {
                "media_kind": "movie",
                "title": metadata.get("title") or title,
                "year": metadata.get("year") or year or None,
                "edition": metadata.get("edition") or None,
                "format": metadata.get("format"),
                "batch_id": batch.id,
            },
        )
    return moved_files, failed_files


def _move_movie_collection_batch(
    db: Session,
    batch: IngestBatch,
) -> tuple[list[str], list[str]]:
    """
    Move a movie collection batch where each video file becomes its own
    Movies/Library/<Year> - <Title>/ folder.

    Rules:
    - Each included movie_item maps to one video file.
    - Artwork and subtitles that cannot be safely matched to a specific item
      are placed in a _collection_sidecars/ folder under Movies/Library/.
    - No overwrite. No deletion.
    - A move log is written per movie item.
    """
    from app.services.video_metadata import safe_movie_path_part, VIDEO_EXTENSIONS

    metadata = dict(batch.metadata_json or {})
    movie_items = metadata.get("movie_items") or []

    if not movie_items:
        return [], ["Movie collection has no movie_items — cannot move"]

    moved_files: list[str] = []
    failed_files: list[str] = []
    reserved: set[str] = set()

    # Build source_file -> item map for included items
    item_by_source: dict[str, dict] = {}
    for item in movie_items:
        if isinstance(item, dict) and item.get("include", True):
            sf = str(item.get("source_file") or "").strip()
            if sf:
                item_by_source[sf.casefold()] = item

    # Categorize all ingest files
    video_ingest_files = []
    sidecar_ingest_files = []
    for ingest_file in batch.files:
        if Path(ingest_file.file_name).suffix.lower() in VIDEO_EXTENSIONS:
            video_ingest_files.append(ingest_file)
        else:
            sidecar_ingest_files.append(ingest_file)

    # Move each matched video file
    for ingest_file in video_ingest_files:
        key = ingest_file.file_name.casefold()
        item = item_by_source.get(key)

        if not item:
            continue

        title = str(item.get("title") or "Unknown Title").strip()
        raw_year = str(item.get("year") or "").strip()
        year = raw_year if len(raw_year) == 4 and raw_year.isdigit() else "Unknown Year"
        edition = str(item.get("edition") or "").strip()
        dest_label = (
            f"{year} - {title}"
            if not edition
            else f"{year} - {title} [{edition}]"
        )
        movie_folder = settings.movies_dir / _safe_path_part(dest_label)

        source = Path(ingest_file.file_path)
        completed = _completed_move_destination(db, batch.id, source)
        if not source.exists() and completed:
            moved_files.append(str(completed))
            reserved.add(_path_key(completed))
            continue

        destination_file = movie_folder / ingest_file.file_name
        if _path_key(destination_file) in reserved or destination_file.exists():
            failed_files.append(
                f"Destination conflict for {ingest_file.file_name}: {destination_file}"
            )
            continue

        movie_folder.mkdir(parents=True, exist_ok=True)
        reserved.add(_path_key(destination_file))

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

            # Write per-movie move log
            log_dir = movie_folder / "metadata"
            log_dir.mkdir(parents=True, exist_ok=True)
            (log_dir / f"batch-{batch.id}-movie-move-log.json").write_text(
                json.dumps(
                    {
                        "batch_id": batch.id,
                        "media_type": "video_movie_collection",
                        "title": title,
                        "year": year,
                        "edition": edition or None,
                        "format": item.get("format"),
                        "source_file": str(source),
                        "destination": str(destination_file),
                        "moved_at": serialize_utc(now_utc()),
                    },
                    indent=2,
                ),
                encoding="utf-8",
            )
            _safe_write_library_metadata(
                movie_folder,
                "movie.json",
                {
                    "media_kind": "movie",
                    "title": title,
                    "year": year,
                    "edition": edition or None,
                    "format": item.get("format"),
                    "resolution": item.get("resolution"),
                    "source": item.get("source"),
                    "source_path": str(source),
                    "primary_video_file": destination_file.name,
                    "video_file_count": 1,
                    "artwork_count": 0,
                    "subtitle_count": 0,
                    "metadata_quality": item.get(
                        "metadata_quality",
                        metadata.get("metadata_quality", "reviewed"),
                    ),
                    "review_confirmed": bool(
                        batch.metadata_confirmed
                        or metadata.get("review_confirmed")
                    ),
                    "accepted_unknown_title": bool(
                        item.get("accepted_unknown_title")
                    ),
                    "accepted_unknown_year": bool(
                        item.get("accepted_unknown_year")
                    ),
                    "lookup_later": bool(item.get("lookup_later")),
                    "batch_id": batch.id,
                },
                settings.movies_metadata_dir,
                {
                    "media_kind": "movie",
                    "title": title,
                    "year": year,
                    "edition": edition or None,
                    "format": item.get("format"),
                    "batch_id": batch.id,
                },
            )
        except Exception as exc:
            action.status = "failed"
            action.error_message = str(exc)
            failed_files.append(f"Failed to move {source}: {exc}")
            db.flush()

    # Move sidecars/artwork/subtitles to a shared _collection_sidecars folder
    if sidecar_ingest_files:
        collection_title = str(metadata.get("collection_title") or "collection").strip()
        sidecar_folder = settings.movies_dir / "_collection_sidecars" / _safe_path_part(collection_title)
        sidecar_folder.mkdir(parents=True, exist_ok=True)

        for ingest_file in sidecar_ingest_files:
            source = Path(ingest_file.file_path)
            completed = _completed_move_destination(db, batch.id, source)
            if not source.exists() and completed:
                moved_files.append(str(completed))
                continue
            if not source.exists():
                continue

            dest_file = sidecar_folder / ingest_file.file_name
            if dest_file.exists():
                dest_file = _unique_artwork_destination(dest_file, reserved)

            reserved.add(_path_key(dest_file))
            action = MoveAction(
                batch_id=batch.id,
                source_path=str(source),
                destination_path=str(dest_file),
                status="running",
            )
            db.add(action)
            db.flush()
            try:
                shutil.move(str(source), str(dest_file))
                action.status = "completed"
                action.completed_at = now_utc()
                moved_files.append(str(dest_file))
            except Exception as exc:
                action.status = "failed"
                action.error_message = str(exc)
                failed_files.append(f"Failed to move sidecar {source}: {exc}")
                db.flush()

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
    if moved_files and not failed_files:
        _safe_write_library_metadata(
            destination,
            "tv-show.json",
            {
                "media_kind": "tv_show",
                "show_title": show_title,
                "year": metadata.get("year"),
                "season_count": metadata.get("season_count", 0),
                "episode_count": metadata.get("episode_count", 0),
                "special_episode_count": metadata.get(
                    "special_episode_count",
                    0,
                ),
                "video_file_count": metadata.get(
                    "video_file_count",
                    sum(role == "tv_episode" for role in completed_roles),
                ),
                "format": metadata.get("format"),
                "metadata_quality": metadata.get(
                    "metadata_quality",
                    "reviewed",
                ),
                "review_confirmed": bool(
                    batch.metadata_confirmed
                    or metadata.get("review_confirmed")
                ),
                "accepted_unknown_show_title": bool(
                    metadata.get("accepted_unknown_show_title")
                ),
                "accepted_unknown_year": bool(
                    metadata.get("accepted_unknown_year")
                ),
                "lookup_later": bool(metadata.get("lookup_later")),
                "move_manifest": metadata.get("move_manifest"),
                "batch_id": batch.id,
            },
            settings.tv_metadata_dir,
            {
                "media_kind": "tv_show",
                "show_title": show_title,
                "year": metadata.get("year"),
                "season_count": metadata.get("season_count", 0),
                "episode_count": metadata.get("episode_count", 0),
                "special_episode_count": metadata.get(
                    "special_episode_count",
                    0,
                ),
                "batch_id": batch.id,
            },
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
    if moved_files and not failed_files:
        track_count = sum(
            not is_artwork_file(Path(path)) for path in moved_files
        )
        _safe_write_library_metadata(
            destination,
            "discography.json",
            {
                "media_kind": "music_discography",
                "artist": metadata.get("artist"),
                "discography_artist": metadata.get("artist"),
                "release_count": metadata.get(
                    "release_count",
                    sum(release_type_counts.values()),
                ),
                "track_count": metadata.get("track_count", track_count),
                "albums_completed": release_type_counts.get("album", 0),
                "singles_completed": release_type_counts.get("single", 0),
                "eps_completed": release_type_counts.get("ep", 0),
                "metadata_quality": metadata.get(
                    "metadata_quality",
                    "reviewed",
                ),
                "review_confirmed": bool(
                    batch.metadata_confirmed
                    or metadata.get("review_confirmed")
                ),
                "accepted_unknown_discography_artist": bool(
                    metadata.get("accepted_unknown_discography_artist")
                ),
                "lookup_later": bool(metadata.get("lookup_later")),
                "move_manifest": metadata.get("move_manifest"),
                "batch_id": batch.id,
            },
            settings.music_metadata_dir,
            {
                "media_kind": "music_discography",
                "artist": metadata.get("artist"),
                "release_count": metadata.get(
                    "release_count",
                    sum(release_type_counts.values()),
                ),
                "track_count": metadata.get("track_count", track_count),
                "batch_id": batch.id,
            },
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


def _move_audiobook_batch(
    db: Session,
    batch: IngestBatch,
) -> tuple[list[str], list[str]]:
    metadata = dict(batch.metadata_json or {})
    destination = audiobook_destination(
        audiobooks_root=settings.audiobooks_dir,
        author=str(metadata.get("author") or "Unknown Author"),
        title=str(metadata.get("title") or "Unknown Title"),
        year=str(metadata.get("year") or "").strip()[:4] or None,
    )
    batch.suggested_destination = str(destination)
    moved_files: list[str] = []
    failed_files: list[str] = []
    planned: list[tuple[object, Path]] = []
    source_root = Path(batch.source_path)
    reserved: set[str] = set()

    for ingest_file in batch.files:
        if ingest_file.detected_role not in {
            "audiobook_audio",
            "audiobook_artwork",
            "audiobook_sidecar",
        }:
            continue
        source = Path(ingest_file.file_path)
        completed = _completed_move_destination(db, batch.id, source)
        if not source.exists() and completed:
            moved_files.append(str(completed))
            reserved.add(_path_key(completed))
            continue
        relative_name = Path(ingest_file.file_name)
        if source_root.is_dir():
            try:
                relative_name = source.relative_to(source_root)
            except ValueError:
                relative_name = Path(ingest_file.file_name)
        destination_file = destination / relative_name
        if _path_key(destination_file) in reserved or destination_file.exists():
            failed_files.append(f"Destination file conflict: {destination_file}")
            continue
        reserved.add(_path_key(destination_file))
        planned.append((ingest_file, destination_file))

    if failed_files:
        warnings = list(metadata.get("metadata_warnings") or [])
        warnings.append("audiobook_destination_conflict")
        metadata["metadata_warnings"] = list(dict.fromkeys(warnings))
        batch.metadata_json = metadata
        batch.status = "needs_metadata_review"
        batch.updated_at = now_utc()
        db.commit()
        return [], failed_files

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

    if moved_files:
        metadata_dir = destination / "metadata"
        metadata_dir.mkdir(parents=True, exist_ok=True)
        (metadata_dir / f"batch-{batch.id}-audiobook-move-log.json").write_text(
            json.dumps(
                {
                    "batch_id": batch.id,
                    "media_type": "audiobook",
                    "source_path": batch.source_path,
                    "destination_path": str(destination),
                    "moved_files": moved_files,
                    "failed_files": failed_files,
                    "metadata": metadata,
                    "moved_at": serialize_utc(now_utc()),
                },
                indent=2,
            ),
            encoding="utf-8",
        )
        if not failed_files:
            audio_file_count = metadata.get(
                "audiobook_file_count",
                sum(
                    ingest_file.detected_role == "audiobook_audio"
                    for ingest_file in batch.files
                ),
            )
            _safe_write_library_metadata(
                destination,
                "audiobook.json",
                {
                    "media_kind": "audiobook",
                    "author": metadata.get("author"),
                    "title": metadata.get("title"),
                    "year": metadata.get("year"),
                    "narrator": metadata.get("narrator"),
                    "series": metadata.get("series"),
                    "series_index": metadata.get("series_index"),
                    "format": metadata.get("format"),
                    "audio_file_count": audio_file_count,
                    "chapter_count": metadata.get(
                        "chapter_count",
                        audio_file_count,
                    ),
                    "metadata_quality": metadata.get(
                        "metadata_quality",
                        "reviewed",
                    ),
                    "review_confirmed": bool(
                        batch.metadata_confirmed
                        or metadata.get("review_confirmed")
                    ),
                    "batch_id": batch.id,
                },
                settings.audiobooks_metadata_dir,
                {
                    "media_kind": "audiobook",
                    "author": metadata.get("author"),
                    "title": metadata.get("title"),
                    "year": metadata.get("year"),
                    "narrator": metadata.get("narrator"),
                    "batch_id": batch.id,
                },
            )
    return moved_files, failed_files


def _move_book_batch(
    db: Session,
    batch: IngestBatch,
) -> tuple[list[str], list[str]]:
    metadata = dict(batch.metadata_json or {})
    items = [
        item
        for item in (metadata.get("book_items") or [])
        if isinstance(item, dict) and item.get("include", True)
    ]
    collection = metadata.get("review_type") == "book_collection" or bool(items)
    collection_title = metadata.get("collection_title")
    keep_together = bool(metadata.get("keep_collection_together"))
    item_by_source = {
        str(item.get("source_file") or "").casefold(): item
        for item in items
        if item.get("source_file")
    }
    associated_item_by_path: dict[str, dict] = {}
    for item in items:
        for alternate in item.get("alternate_formats") or []:
            if isinstance(alternate, dict) and alternate.get("file"):
                associated_item_by_path[
                    str(alternate["file"]).replace("\\", "/").casefold()
                ] = item
        artwork = item.get("matched_artwork")
        if isinstance(artwork, dict) and artwork.get("file"):
            associated_item_by_path[
                str(artwork["file"]).replace("\\", "/").casefold()
            ] = item
    moved_files: list[str] = []
    failed_files: list[str] = []
    planned: list[tuple[object, Path]] = []
    reserved: set[str] = set()
    collection_destinations: dict[str, str] = {}

    if collection:
        for item in items:
            destination = build_book_item_destination(
                books_root=settings.books_dir,
                item=item,
                collection_title=(
                    str(collection_title) if collection_title else None
                ),
                keep_collection_together=keep_together,
            )
            destination_key = _path_key(destination)
            source_file = str(item.get("source_file") or "")
            previous = collection_destinations.get(destination_key)
            if previous:
                failed_files.append(
                    "Two included books resolve to the same destination: "
                    f"{destination} ({previous}, {source_file})"
                )
            else:
                collection_destinations[destination_key] = source_file

    if failed_files:
        warnings = list(metadata.get("metadata_warnings") or [])
        warnings.append("book_collection_duplicate_destination")
        metadata["metadata_warnings"] = list(dict.fromkeys(warnings))
        batch.metadata_json = metadata
        batch.status = "needs_metadata_review"
        batch.updated_at = now_utc()
        db.commit()
        return [], failed_files

    for ingest_file in batch.files:
        source = Path(ingest_file.file_path)
        completed = _completed_move_destination(db, batch.id, source)
        if not source.exists() and completed:
            moved_files.append(str(completed))
            reserved.add(_path_key(completed))
            continue

        if collection:
            item = item_by_source.get(ingest_file.file_name.casefold())
            if not item:
                try:
                    relative_source = source.relative_to(
                        Path(batch.source_path)
                    ).as_posix().casefold()
                except ValueError:
                    relative_source = ingest_file.file_name.casefold()
                item = associated_item_by_path.get(relative_source)
            if not item:
                continue
            destination = build_book_item_destination(
                books_root=settings.books_dir,
                item=item,
                collection_title=(
                    str(collection_title) if collection_title else None
                ),
                keep_collection_together=keep_together,
            )
        else:
            destination = book_destination(
                str(metadata.get("format") or source.suffix.lstrip(".") or "EPUB"),
                str(metadata.get("author") or "Unknown Author"),
                str(metadata.get("title") or "Unknown Title"),
                str(metadata.get("year") or "")[:4] or None,
                settings.books_dir,
            )

        destination_file = destination / ingest_file.file_name
        if _path_key(destination_file) in reserved or destination_file.exists():
            failed_files.append(f"Destination file conflict: {destination_file}")
            continue
        reserved.add(_path_key(destination_file))
        planned.append((ingest_file, destination_file))

    if failed_files:
        warnings = list(metadata.get("metadata_warnings") or [])
        warnings.append("book_destination_conflict")
        metadata["metadata_warnings"] = list(dict.fromkeys(warnings))
        batch.metadata_json = metadata
        batch.status = "needs_metadata_review"
        batch.updated_at = now_utc()
        db.commit()
        return [], failed_files

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

    destinations = sorted({str(Path(path).parent) for path in moved_files})
    for destination_value in destinations:
        destination = Path(destination_value)
        metadata_dir = destination / "metadata"
        metadata_dir.mkdir(parents=True, exist_ok=True)
        (metadata_dir / f"batch-{batch.id}-book-move-log.json").write_text(
            json.dumps(
                {
                    "batch_id": batch.id,
                    "media_type": "book_collection" if collection else "book",
                    "source_path": batch.source_path,
                    "destination_path": str(destination),
                    "moved_files": [
                        path
                        for path in moved_files
                        if Path(path).parent == destination
                    ],
                    "failed_files": failed_files,
                    "metadata": metadata,
                    "moved_at": serialize_utc(now_utc()),
                },
                indent=2,
            ),
            encoding="utf-8",
        )
        destination_files = [
            Path(path)
            for path in moved_files
            if Path(path).parent == destination
        ]
        primary_file = next(
            (
                path
                for path in destination_files
                if path.name.casefold() in item_by_source
            ),
            destination_files[0] if destination_files else None,
        )
        item = (
            item_by_source.get(primary_file.name.casefold(), {})
            if primary_file
            else {}
        )
        _safe_write_library_metadata(
            destination,
            "book.json",
            {
                "media_kind": "book",
                "title": item.get("title") or metadata.get("title"),
                "author": item.get("author") or metadata.get("author"),
                "year": item.get("year") or metadata.get("year"),
                "format": (
                    item.get("format")
                    or metadata.get("format")
                    or (
                        primary_file.suffix.lstrip(".").upper()
                        if primary_file
                        else None
                    )
                ),
                "source_path": batch.source_path,
                "metadata_quality": item.get(
                    "metadata_quality",
                    metadata.get("metadata_quality", "reviewed"),
                ),
                "review_confirmed": bool(
                    batch.metadata_confirmed
                    or metadata.get("review_confirmed")
                ),
                "batch_id": batch.id,
            },
            settings.books_metadata_dir,
            {
                "media_kind": "book",
                "title": item.get("title") or metadata.get("title"),
                "author": item.get("author") or metadata.get("author"),
                "year": item.get("year") or metadata.get("year"),
                "format": (
                    item.get("format")
                    or metadata.get("format")
                    or (
                        primary_file.suffix.lstrip(".").upper()
                        if primary_file
                        else None
                    )
                ),
                "batch_id": batch.id,
            },
        )
    return moved_files, failed_files


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
                metadata = dict(batch.metadata_json or {})
                if metadata.get("review_type") == "movie_collection" and metadata.get("movie_items"):
                    moved_files, failed_files = _move_movie_collection_batch(db, batch)
                else:
                    moved_files, failed_files = _move_movie_batch(db, batch)
                if not moved_files:
                    if batch.status != "needs_metadata_review":
                        batch.status = "move_failed"
                    batch.updated_at = now_utc()
                    manifest_warnings = _record_move_manifest(
                        db, batch, failed_files
                    )
                    db.commit()
                    errors.extend(
                        f"Batch {batch.id}: {error}" for error in failed_files
                    )
                    errors.extend(
                        f"Batch {batch.id}: {warning}"
                        for warning in manifest_warnings
                    )
                    continue
                batch.status = "move_failed" if failed_files else "moved"
                batch.updated_at = now_utc()
                if batch.status == "moved":
                    _lock_metadata_for_move(batch)
                manifest_warnings = _record_move_manifest(
                    db, batch, failed_files
                )
                _update_movie_library_manifest_pointers(db, batch)
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
                errors.extend(
                    f"Batch {batch.id}: {warning}"
                    for warning in manifest_warnings
                )
                continue

            if batch.detected_type == "video_tv_show":
                moved_files, failed_files = _move_tv_batch(db, batch)
                if not moved_files:
                    if batch.status != "needs_metadata_review":
                        batch.status = "move_failed"
                    batch.updated_at = now_utc()
                    manifest_warnings = _record_move_manifest(
                        db, batch, failed_files
                    )
                    db.commit()
                    errors.extend(
                        f"Batch {batch.id}: {error}" for error in failed_files
                    )
                    errors.extend(
                        f"Batch {batch.id}: {warning}"
                        for warning in manifest_warnings
                    )
                    continue
                batch.status = "move_failed" if failed_files else "moved"
                batch.updated_at = now_utc()
                if batch.status == "moved":
                    _lock_metadata_for_move(batch)
                manifest_warnings = _record_move_manifest(
                    db, batch, failed_files
                )
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
                errors.extend(
                    f"Batch {batch.id}: {warning}"
                    for warning in manifest_warnings
                )
                continue

            if batch.detected_type == "book":
                moved_files, failed_files = _move_book_batch(db, batch)
                if not moved_files:
                    if batch.status != "needs_metadata_review":
                        batch.status = "move_failed"
                    batch.updated_at = now_utc()
                    manifest_warnings = _record_move_manifest(
                        db, batch, failed_files
                    )
                    db.commit()
                    errors.extend(
                        f"Batch {batch.id}: {error}" for error in failed_files
                    )
                    errors.extend(
                        f"Batch {batch.id}: {warning}"
                        for warning in manifest_warnings
                    )
                    continue
                batch.status = "move_failed" if failed_files else "moved"
                batch.updated_at = now_utc()
                if batch.status == "moved":
                    _lock_metadata_for_move(batch)
                manifest_warnings = _record_move_manifest(
                    db, batch, failed_files
                )
                metadata = batch.metadata_json or {}
                book_items = {
                    str(item.get("source_file") or "").casefold(): item
                    for item in (metadata.get("book_items") or [])
                    if isinstance(item, dict)
                }
                for moved_path in moved_files:
                    path = Path(moved_path)
                    if path.suffix.casefold() not in {".epub", ".pdf"}:
                        continue
                    item = book_items.get(path.name.casefold(), {})
                    if not item:
                        continue
                    if (
                        db.query(ArchiveItem)
                        .filter(ArchiveItem.final_path == str(path))
                        .first()
                    ):
                        continue
                    db.add(ArchiveItem(
                        media_type="book",
                        title=item.get("title") or metadata.get("title") or path.stem,
                        creator=item.get("author") or metadata.get("author"),
                        year=item.get("year") or metadata.get("year"),
                        source_kind=batch.source_kind,
                        final_path=str(path),
                        metadata_status=(
                            "collection"
                            if metadata.get("review_type") == "book_collection"
                            else "basic"
                        ),
                    ))
                db.commit()
                moved += 1
                if failed_files:
                    errors.extend(
                        f"Batch {batch.id}: {error}" for error in failed_files
                    )
                errors.extend(
                    f"Batch {batch.id}: {warning}"
                    for warning in manifest_warnings
                )
                continue

            if batch.detected_type == "audiobook":
                moved_files, failed_files = _move_audiobook_batch(db, batch)
                if not moved_files:
                    if batch.status != "needs_metadata_review":
                        batch.status = "move_failed"
                    batch.updated_at = now_utc()
                    manifest_warnings = _record_move_manifest(
                        db, batch, failed_files
                    )
                    db.commit()
                    errors.extend(
                        f"Batch {batch.id}: {error}" for error in failed_files
                    )
                    errors.extend(
                        f"Batch {batch.id}: {warning}"
                        for warning in manifest_warnings
                    )
                    continue
                batch.status = "move_failed" if failed_files else "moved"
                batch.updated_at = now_utc()
                if batch.status == "moved":
                    _lock_metadata_for_move(batch)
                manifest_warnings = _record_move_manifest(
                    db, batch, failed_files
                )
                metadata = batch.metadata_json or {}
                destination = str(
                    audiobook_destination(
                        audiobooks_root=settings.audiobooks_dir,
                        author=str(
                            metadata.get("author") or "Unknown Author"
                        ),
                        title=str(metadata.get("title") or "Unknown Title"),
                        year=(
                            str(metadata.get("year") or "").strip()[:4]
                            or None
                        ),
                    )
                )
                if not (
                    db.query(ArchiveItem)
                    .filter(ArchiveItem.final_path == destination)
                    .first()
                ):
                    db.add(ArchiveItem(
                        media_type="audiobook",
                        title=metadata.get("title") or "Unknown Title",
                        creator=metadata.get("author"),
                        year=metadata.get("year"),
                        source_kind=batch.source_kind,
                        final_path=destination,
                        metadata_status="basic",
                    ))
                db.commit()
                moved += 1
                if failed_files:
                    errors.extend(
                        f"Batch {batch.id}: {error}" for error in failed_files
                    )
                errors.extend(
                    f"Batch {batch.id}: {warning}"
                    for warning in manifest_warnings
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
                    manifest_warnings = _record_move_manifest(
                        db, batch, failed_files
                    )
                    db.commit()
                    errors.extend(f"Batch {batch.id}: {error}" for error in failed_files)
                    errors.extend(
                        f"Batch {batch.id}: {warning}"
                        for warning in manifest_warnings
                    )
                    continue

                batch.status = "move_failed" if failed_files else "moved"
                batch.updated_at = now_utc()
                if batch.status == "moved":
                    _lock_metadata_for_move(batch)
                manifest_warnings = _record_move_manifest(
                    db, batch, failed_files
                )
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
                errors.extend(
                    f"Batch {batch.id}: {warning}"
                    for warning in manifest_warnings
                )
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
            if batch.status == "moved":
                _lock_metadata_for_move(batch)
            db.flush()

            _write_move_log(batch, album_meta, moved_files, failed_files)
            manifest_warnings = _record_move_manifest(
                db, batch, failed_files
            )
            if moved_files and not failed_files:
                track_count = sum(
                    not is_artwork_file(Path(path)) for path in moved_files
                )
                artwork_count = sum(
                    is_artwork_file(Path(path)) for path in moved_files
                )
                _safe_write_library_metadata(
                    destination_dir,
                    "music-album.json",
                    {
                        "media_kind": "music_album",
                        "album_artist": (
                            album_meta.get("artist")
                            or album_meta.get("album_artist")
                        ),
                        "album_title": album_meta.get("album"),
                        "artist": (
                            album_meta.get("artist")
                            or album_meta.get("album_artist")
                        ),
                        "album": album_meta.get("album"),
                        "year": album_meta.get("year"),
                        "genre": album_meta.get("genre"),
                        "format": album_meta.get(
                            "format",
                            _format_bucket_for_path(destination_dir),
                        ),
                        "track_count": album_meta.get(
                            "track_count",
                            track_count,
                        ),
                        "disc_count": album_meta.get("disc_count", 1),
                        "artwork_count": album_meta.get(
                            "artwork_count",
                            artwork_count,
                        ),
                        "metadata_quality": album_meta.get(
                            "metadata_quality",
                            "reviewed",
                        ),
                        "review_confirmed": bool(
                            batch.metadata_confirmed
                            or album_meta.get("review_confirmed")
                        ),
                        "accepted_unknown_album_artist": bool(
                            album_meta.get("accepted_unknown_album_artist")
                        ),
                        "accepted_unknown_album_title": bool(
                            album_meta.get("accepted_unknown_album_title")
                        ),
                        "accepted_unknown_year": bool(
                            album_meta.get("accepted_unknown_year")
                        ),
                        "lookup_later": bool(album_meta.get("lookup_later")),
                        "move_manifest": (
                            (batch.metadata_json or {}).get("move_manifest")
                        ),
                        "batch_id": batch.id,
                    },
                    settings.music_metadata_dir,
                    {
                        "media_kind": "music_album",
                        "artist": (
                            album_meta.get("artist")
                            or album_meta.get("album_artist")
                        ),
                        "album": album_meta.get("album"),
                        "year": album_meta.get("year"),
                        "genre": album_meta.get("genre"),
                        "format": album_meta.get(
                            "format",
                            _format_bucket_for_path(destination_dir),
                        ),
                        "batch_id": batch.id,
                    },
                )

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
            errors.extend(
                f"Batch {batch.id}: {warning}"
                for warning in manifest_warnings
            )

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
