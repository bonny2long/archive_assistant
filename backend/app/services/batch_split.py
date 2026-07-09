from __future__ import annotations

import re
from copy import deepcopy
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session, selectinload

from app.core.config import settings
from app.core.time import now_utc
from app.models.archive import IngestBatch, IngestFile
from app.models.media_metadata import CandidateMember, MediaIdentityCandidate, UniversalIngestionReviewAction

_SAFE_PART_PATTERN = re.compile(r'[<>:"/\\|?*]+')

AUDIO_EXTENSIONS = {
    ".mp3", ".flac", ".m4a", ".aac", ".wav", ".ogg", ".opus", ".wma", ".aiff", ".alac"
}

ARTWORK_EXTENSIONS = {
    ".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp", ".tiff"
}

SIDECAR_EXTENSIONS = {
    ".txt", ".log", ".cue", ".m3u", ".m3u8", ".nfo", ".sfv", ".md5", ".ffp"
}


def safe_path_part(value: object, fallback: str = "Unknown") -> str:
    text = str(value or "").strip()
    if not text:
        text = fallback
    text = _SAFE_PART_PATTERN.sub(" ", text)
    text = re.sub(r"\s+", " ", text).strip(" .")
    return text or fallback


def _norm_match(value: object) -> str:
    text = str(value or "").strip().casefold()
    text = re.sub(r"\s+", " ", text)
    text = re.sub(r"[^\w\s-]+", "", text)
    return text.strip()


def _is_unknownish(value: object) -> bool:
    return _norm_match(value) in {
        "",
        "unknown",
        "unknown artist",
        "unknown album",
        "various artists",
        "mixed discography",
        "mixed",
        "none",
        "null",
    }


def _same_or_missing(left: object, right: object) -> bool:
    if _is_unknownish(left) or _is_unknownish(right):
        return True
    return _norm_match(left) == _norm_match(right)


def _first_non_empty(*values: object, fallback: str = "") -> str:
    for value in values:
        if value is None:
            continue
        text = str(value).strip()
        if text and not _is_unknownish(text):
            return text
    return fallback


def _file_extension(ingest_file: IngestFile) -> str:
    ext = getattr(ingest_file, "extension", None)
    if ext:
        return str(ext).lower().strip()
    name = getattr(ingest_file, "file_name", "") or ""
    return Path(name).suffix.lower().strip()


def _is_audio_file(ingest_file: IngestFile) -> bool:
    ext = _file_extension(ingest_file)
    role = str(getattr(ingest_file, "detected_role", "") or "").lower()
    return ext in AUDIO_EXTENSIONS or role in {"music_track", "discography_track", "audio", "music_audio"}


def _is_artwork_file(ingest_file: IngestFile) -> bool:
    ext = _file_extension(ingest_file)
    role = str(getattr(ingest_file, "detected_role", "") or "").lower()
    return ext in ARTWORK_EXTENSIONS or role in {"artwork", "cover_art", "album_artwork"}


def _is_sidecar_file(ingest_file: IngestFile) -> bool:
    ext = _file_extension(ingest_file)
    role = str(getattr(ingest_file, "detected_role", "") or "").lower()
    return ext in SIDECAR_EXTENSIONS or role in {"sidecar", "metadata_sidecar", "playlist", "log"}


def _partition_child_files(files_to_move: list[IngestFile]) -> dict[str, list[IngestFile]]:
    audio: list[IngestFile] = []
    artwork: list[IngestFile] = []
    sidecars: list[IngestFile] = []
    other: list[IngestFile] = []

    for ingest_file in files_to_move:
        if _is_audio_file(ingest_file):
            audio.append(ingest_file)
        elif _is_artwork_file(ingest_file):
            artwork.append(ingest_file)
        elif _is_sidecar_file(ingest_file):
            sidecars.append(ingest_file)
        else:
            other.append(ingest_file)

    return {
        "audio": audio,
        "artwork": artwork,
        "sidecars": sidecars,
        "other": other,
    }


def _embedded_fields(ingest_file: IngestFile) -> dict[str, Any]:
    meta = ingest_file.metadata_json or {}
    embedded = meta.get("embedded_metadata_fields")
    if isinstance(embedded, dict):
        return embedded
    embedded_metadata = meta.get("embedded_metadata")
    if isinstance(embedded_metadata, dict) and isinstance(embedded_metadata.get("fields"), dict):
        return embedded_metadata["fields"]
    return {}


def _track_number_value(value: object) -> int | str | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    first = re.split(r"[/\-]", text)[0].strip()
    return int(first) if first.isdigit() else text


def _track_from_audio_file(ingest_file: IngestFile) -> dict[str, Any]:
    meta = ingest_file.metadata_json or {}
    embedded = _embedded_fields(ingest_file)
    title = _first_non_empty(
        embedded.get("title"),
        meta.get("title"),
        Path(getattr(ingest_file, "file_name", "") or "").stem,
        fallback="Unknown Track",
    )
    track_number = _first_non_empty(
        embedded.get("track_number"),
        embedded.get("tracknumber"),
        meta.get("tracknumber"),
        meta.get("track_number"),
        fallback="",
    )
    disc_number = _first_non_empty(
        embedded.get("disc_number"),
        embedded.get("discnumber"),
        meta.get("discnumber"),
        meta.get("disc_number"),
        fallback="1",
    )
    return {
        "title": title,
        "track_number": _track_number_value(track_number),
        "disc_number": _track_number_value(disc_number) or 1,
        "file_name": getattr(ingest_file, "file_name", None),
    }


def _latest_identity_override(
    db: Session,
    batch_id: int,
    candidate_id: int,
) -> UniversalIngestionReviewAction | None:
    return db.query(UniversalIngestionReviewAction).filter(
        UniversalIngestionReviewAction.batch_id == batch_id,
        UniversalIngestionReviewAction.candidate_id == candidate_id,
        UniversalIngestionReviewAction.action_type == "override_identity",
        UniversalIngestionReviewAction.decision_status != "cleared",
    ).order_by(
        UniversalIngestionReviewAction.updated_at.desc(),
        UniversalIngestionReviewAction.id.desc(),
    ).first()


def _candidate_title(candidate: MediaIdentityCandidate | None, override: UniversalIngestionReviewAction | None) -> str:
    if candidate is None:
        return ""
    value = override.override_title if override and override.override_title else candidate.candidate_title
    return "" if _is_unknownish(value) else str(value or "").strip()


def _candidate_artist(candidate: MediaIdentityCandidate | None, override: UniversalIngestionReviewAction | None) -> str:
    if candidate is None:
        return ""
    value = (
        override.override_primary_creator
        if override and override.override_primary_creator
        else candidate.candidate_primary_creator
    )
    return "" if _is_unknownish(value) else str(value or "").strip()


def _candidate_year(candidate: MediaIdentityCandidate | None, override: UniversalIngestionReviewAction | None) -> str:
    if candidate is None:
        return ""
    value = override.override_year if override and override.override_year else candidate.candidate_year
    return "" if _is_unknownish(value) else str(value or "").strip()


def _album_source_folder(album: dict[str, Any]) -> str | None:
    value = album.get("source_folder") or album.get("folder") or album.get("source")
    return str(value).strip() if value else None


def _candidate_source_folder(candidate: MediaIdentityCandidate) -> str | None:
    evidence = candidate.identity_evidence_json or {}
    for key in ("source_folder", "folder", "source"):
        value = evidence.get(key)
        if value:
            return str(value).strip()
    return None


def _album_matches_candidate(
    album: dict[str, Any],
    candidate: MediaIdentityCandidate,
    override: UniversalIngestionReviewAction | None = None,
) -> bool:
    title = album.get("album") or album.get("title")
    artist = album.get("artist") or album.get("album_artist")
    year = album.get("year")
    source_folder = (_album_source_folder(album) or "").casefold()

    candidate_title = _candidate_title(candidate, override)
    candidate_artist = _candidate_artist(candidate, override)
    candidate_year = _candidate_year(candidate, override)
    candidate_key = str(candidate.candidate_key or "").casefold()
    candidate_source_folder = (_candidate_source_folder(candidate) or "").casefold()

    if candidate_source_folder and source_folder and candidate_source_folder == source_folder:
        return True
    if candidate_key and source_folder and source_folder in candidate_key:
        return True
    if title and candidate_title and _norm_match(title) == _norm_match(candidate_title):
        artist_matches = _same_or_missing(artist, candidate_artist)
        year_matches = _same_or_missing(year, candidate_year)
        return artist_matches and year_matches
    return False


def _find_album_for_candidate(
    candidate: MediaIdentityCandidate,
    batch_metadata: dict[str, Any],
    override: UniversalIngestionReviewAction | None = None,
) -> dict[str, Any] | None:
    albums = batch_metadata.get("albums")
    if not isinstance(albums, list):
        return None
    for album in albums:
        if isinstance(album, dict) and _album_matches_candidate(album, candidate, override):
            return album
    return None


def _file_album_source_folder(ingest_file: IngestFile) -> str | None:
    metadata = ingest_file.metadata_json or {}
    album_metadata = metadata.get("_discography_album")
    if isinstance(album_metadata, dict):
        value = _album_source_folder(album_metadata)
        if value:
            return value
    return None


def _files_for_source_folder(files: list[IngestFile], source_folder: str) -> list[IngestFile]:
    normalized = _norm_match(source_folder)
    return [ingest_file for ingest_file in files if _norm_match(_file_album_source_folder(ingest_file)) == normalized]


def _candidate_source_folders_from_members(
    db: Session,
    parent_batch: IngestBatch,
    candidate_id: int,
) -> list[str]:
    member_rows = db.query(CandidateMember).filter(CandidateMember.candidate_id == candidate_id).all()
    file_ids = {row.batch_file_id for row in member_rows if row.batch_file_id is not None}
    if not file_ids:
        return []

    source_folders: list[str] = []
    seen: set[str] = set()
    for ingest_file in parent_batch.files:
        if ingest_file.id not in file_ids:
            continue
        source_folder = _file_album_source_folder(ingest_file)
        if not source_folder:
            continue
        key = _norm_match(source_folder)
        if key and key not in seen:
            seen.add(key)
            source_folders.append(source_folder)
    return source_folders


def _find_album_by_source_folder(batch_metadata: dict[str, Any], source_folder: str) -> dict[str, Any] | None:
    albums = batch_metadata.get("albums")
    if not isinstance(albums, list):
        return None

    target = _norm_match(source_folder)
    for album in albums:
        if not isinstance(album, dict):
            continue
        album_source = _album_source_folder(album)
        if album_source and _norm_match(album_source) == target:
            return album
    return None


def _album_from_candidate_and_files(
    candidate: MediaIdentityCandidate,
    override: UniversalIngestionReviewAction | None,
    files_to_move: list[IngestFile],
    source_folder: str,
) -> dict[str, Any]:
    first_file = files_to_move[0] if files_to_move else None
    first_meta = first_file.metadata_json or {} if first_file else {}
    album_meta = first_meta.get("_discography_album") if isinstance(first_meta.get("_discography_album"), dict) else {}

    title = (
        _candidate_title(candidate, override)
        or album_meta.get("album")
        or album_meta.get("title")
        or first_meta.get("album")
        or source_folder
        or "Unknown Album"
    )
    artist = (
        _candidate_artist(candidate, override)
        or album_meta.get("artist")
        or album_meta.get("album_artist")
        or first_meta.get("album_artist")
        or first_meta.get("albumartist")
        or first_meta.get("artist")
        or "Unknown Artist"
    )
    year = (
        _candidate_year(candidate, override)
        or album_meta.get("year")
        or first_meta.get("year")
        or first_meta.get("date")
        or ""
    )

    return {
        "source_folder": source_folder,
        "album": title,
        "title": title,
        "artist": artist,
        "album_artist": artist,
        "year": year,
        "genre": album_meta.get("genre") or first_meta.get("genre") or "Unknown",
        "primary_genre": album_meta.get("primary_genre") or first_meta.get("primary_genre") or album_meta.get("genre") or first_meta.get("genre"),
        "release_type": album_meta.get("release_type") or "album",
        "track_count": len(files_to_move),
        "include": True,
        "synthesized_for_split": True,
    }


def _library_album_destination(album: dict[str, Any]) -> str:
    artist = safe_path_part(album.get("artist") or album.get("album_artist") or "Unknown Artist", "Unknown Artist")
    title = safe_path_part(album.get("album") or album.get("title") or "Unknown Album", "Unknown Album")
    year = safe_path_part(album.get("year") or "", "").strip()
    album_folder = f"{year} - {title}" if year else title
    format_value = str(album.get("format") or "").strip().upper()
    root = settings.music_flac_dir if format_value == "FLAC" else settings.music_mp3_dir
    return str(Path(root) / artist / album_folder)


def _build_album_batch_metadata(
    album: dict[str, Any],
    parent_batch: IngestBatch,
    files_to_move: list[IngestFile],
    source_folder: str,
    candidate: MediaIdentityCandidate | None = None,
    identity_override: UniversalIngestionReviewAction | None = None,
) -> dict[str, Any]:
    parts = _partition_child_files(files_to_move)
    audio_files = parts["audio"]
    artwork_files = parts["artwork"]
    sidecar_files = parts["sidecars"]
    other_files = parts["other"]

    first_audio = audio_files[0] if audio_files else (files_to_move[0] if files_to_move else None)
    first_meta = first_audio.metadata_json or {} if first_audio else {}
    embedded = _embedded_fields(first_audio) if first_audio else {}

    manual_artist = album.get("artist") or album.get("album_artist") if candidate is None else None
    manual_title = album.get("album") or album.get("title") if candidate is None else None
    manual_year = album.get("year") if candidate is None else None
    artist = _first_non_empty(
        _candidate_artist(candidate, identity_override) if candidate else None,
        manual_artist,
        embedded.get("album_artist"),
        embedded.get("albumartist"),
        first_meta.get("albumartist"),
        first_meta.get("album_artist"),
        first_meta.get("artist"),
        album.get("artist"),
        album.get("album_artist"),
        fallback="Unknown Artist",
    )
    title = _first_non_empty(
        _candidate_title(candidate, identity_override) if candidate else None,
        manual_title,
        embedded.get("album"),
        first_meta.get("album"),
        album.get("album"),
        album.get("title"),
        fallback="Unknown Album",
    )
    year = _first_non_empty(
        _candidate_year(candidate, identity_override) if candidate else None,
        manual_year,
        first_meta.get("year"),
        embedded.get("date"),
        first_meta.get("date"),
        album.get("year"),
        fallback="",
    )
    if len(year) >= 4 and year[:4].isdigit():
        year = year[:4]

    genre = _first_non_empty(
        album.get("genre") if candidate is None else None,
        album.get("primary_genre") if candidate is None else None,
        first_meta.get("genre"),
        embedded.get("genre"),
        album.get("genre"),
        album.get("primary_genre"),
        fallback="Unknown",
    )
    primary_genre = _first_non_empty(
        album.get("primary_genre") if candidate is None else None,
        album.get("genre") if candidate is None else None,
        first_meta.get("primary_genre"),
        album.get("primary_genre"),
        genre,
        fallback=genre,
    )
    format_value = _first_non_empty(
        first_meta.get("format"),
        album.get("format"),
        _file_extension(first_audio).lstrip(".").upper() if first_audio else None,
        fallback="Unknown",
    )
    release_type = _first_non_empty(album.get("release_type"), first_meta.get("release_type"), fallback="album")

    tracks = [_track_from_audio_file(file) for file in audio_files]
    tracks.sort(key=lambda item: (item.get("disc_number") or 1, item.get("track_number") or 9999, item.get("file_name") or ""))

    artwork_names = [getattr(file, "file_name", "") for file in artwork_files if getattr(file, "file_name", "")]
    sidecar_names = [getattr(file, "file_name", "") for file in sidecar_files if getattr(file, "file_name", "")]
    other_names = [getattr(file, "file_name", "") for file in other_files if getattr(file, "file_name", "")]

    warnings: list[str] = []
    if not audio_files:
        warnings.append("split_child_has_no_audio_files")
    if other_files:
        warnings.append("split_child_has_unclassified_files")

    metadata: dict[str, Any] = {
        "source_folder": source_folder,
        "artist": artist,
        "albumartist": artist,
        "album": title,
        "title": title,
        "year": year,
        "date": year,
        "genre": genre,
        "primary_genre": primary_genre,
        "format": format_value,
        "release_type": release_type,
        "include": True,
        "type": "music_album",
        "review_type": "music_album",
        "review_mode": "single_item",
        "review_origin": "multi_artist_discography_split",
        "metadata_quality": "good" if audio_files else "needs_review",
        "metadata_confirmed": False,
        "track_count": len(audio_files),
        "disc_count": len({track.get("disc_number") or 1 for track in tracks}) if tracks else 0,
        "tracks": tracks,
        "artwork_count": len(artwork_files),
        "artwork_files": artwork_names,
        "ignored_sidecar_count": len(sidecar_files),
        "ignored_sidecar_files": sidecar_names,
        "unclassified_file_count": len(other_files),
        "unclassified_files": other_names,
        "metadata_warnings": warnings,
        "blocking_review_items": [],
        "non_blocking_review_items": warnings,
        "split_from_batch_id": parent_batch.id,
        "split_from_source_path": parent_batch.source_path,
        "split_source_folder": source_folder,
    }

    for optional_key in ("metadata_assist_version",):
        if optional_key in album:
            metadata[optional_key] = album[optional_key]
        elif isinstance(parent_batch.metadata_json, dict) and optional_key in parent_batch.metadata_json:
            metadata[optional_key] = parent_batch.metadata_json[optional_key]

    if album.get("synthesized_for_split"):
        metadata["synthesized_for_split"] = True

    return metadata


def _suggested_metadata(album: dict[str, Any]) -> dict[str, Any]:
    return {
        "artist": album.get("artist") or album.get("album_artist") or "Unknown Artist",
        "album": album.get("album") or album.get("title") or "Unknown Album",
        "year": album.get("year"),
        "primary_genre": album.get("primary_genre") or album.get("genre"),
    }


def _active_materialization_actions(db: Session, batch_id: int, candidate_id: int) -> list[UniversalIngestionReviewAction]:
    return db.query(UniversalIngestionReviewAction).filter(
        UniversalIngestionReviewAction.batch_id == batch_id,
        UniversalIngestionReviewAction.candidate_id == candidate_id,
        UniversalIngestionReviewAction.action_type.in_({"split_candidate", "approve_candidate"}),
        UniversalIngestionReviewAction.decision_status != "cleared",
    ).all()


def _resolve_split_album_and_files(
    db: Session,
    parent_batch: IngestBatch,
    candidate: MediaIdentityCandidate,
    batch_metadata: dict[str, Any],
    identity_override: UniversalIngestionReviewAction | None,
) -> tuple[dict[str, Any], str, list[IngestFile]]:
    source_folders = _candidate_source_folders_from_members(db, parent_batch, candidate.id)

    if len(source_folders) > 1:
        raise ValueError(
            "Selected candidate maps to multiple source folders "
            f"({', '.join(source_folders)}). Extract one release at a time or use the full editor."
        )

    if len(source_folders) == 1:
        source_folder = source_folders[0]
        files_to_move = _files_for_source_folder(parent_batch.files, source_folder)
        if not files_to_move:
            raise ValueError(
                f"Candidate resolved to source_folder '{source_folder}', but no files are still attached to that folder. "
                "It may have already been split."
            )
        album = _find_album_by_source_folder(batch_metadata, source_folder)
        if album is None:
            album = _album_from_candidate_and_files(candidate, identity_override, files_to_move, source_folder)
        return album, source_folder, files_to_move

    album = _find_album_for_candidate(candidate, batch_metadata, identity_override)
    if album is None:
        raise ValueError(
            "Could not match candidate to a discography album. "
            "No CandidateMember -> IngestFile source_folder evidence was available, "
            "and title/artist fallback matching failed."
        )

    source_folder = _album_source_folder(album)
    if not source_folder:
        raise ValueError("Matched album has no source_folder")

    files_to_move = _files_for_source_folder(parent_batch.files, source_folder)
    if not files_to_move:
        raise ValueError(
            f"No ingest files matched source_folder '{source_folder}'. "
            "The batch may have already been partially split."
        )
    return album, source_folder, files_to_move


def _existing_split_child_id(db: Session, split_history: list[dict[str, Any]], source_folder: str) -> int | None:
    target = _norm_match(source_folder)
    for item in split_history:
        if not isinstance(item, dict):
            continue
        if _norm_match(item.get("source_folder")) != target:
            continue
        child_id = int(item.get("child_batch_id") or 0)
        if child_id and db.get(IngestBatch, child_id) is not None:
            return child_id
    return None


def execute_split_discography_releases(db: Session, batch_id: int) -> dict[str, Any]:
    parent_batch = db.query(IngestBatch).options(selectinload(IngestBatch.files)).filter(IngestBatch.id == batch_id).first()
    if parent_batch is None:
        raise ValueError("Batch not found")
    if parent_batch.detected_type != "music_discography":
        raise ValueError("Only music discography batches can create release child batches")
    if parent_batch.status in {"moved", "move_failed", "merged"}:
        raise ValueError("Moved or closed batches cannot create child batches")

    timestamp = now_utc()
    batch_metadata = deepcopy(parent_batch.metadata_json or {})
    albums = [item for item in batch_metadata.get("albums", []) if isinstance(item, dict)]
    included_albums = [
        album for album in albums
        if album.get("include", True) is not False and album.get("release_type") != "exclude"
    ]
    split_history = batch_metadata.get("split_history") if isinstance(batch_metadata.get("split_history"), list) else []
    if not included_albums:
        existing_child_ids = [
            int(item.get("child_batch_id") or 0)
            for item in split_history
            if isinstance(item, dict) and item.get("child_batch_id") and db.get(IngestBatch, int(item.get("child_batch_id") or 0)) is not None
        ]
        if existing_child_ids:
            remaining_parent_file_count = db.query(IngestFile).filter(IngestFile.batch_id == parent_batch.id).count()
            return {
                "parent_batch_id": parent_batch.id,
                "created_child_batch_ids": [],
                "existing_child_batch_ids": existing_child_ids,
                "created_count": 0,
                "skipped_count": len(existing_child_ids),
                "remaining_parent_file_count": remaining_parent_file_count,
                "parent_status": parent_batch.status,
                "parent_review_state": batch_metadata.get("parent_review_state") or parent_batch.status,
                "message": "Included release child batches already exist.",
            }
        raise ValueError("No included discography releases are available to create child batches.")

    created_child_batch_ids: list[int] = []
    skipped_child_batch_ids: list[int] = []
    skipped_sources: list[str] = []
    split_sources: set[str] = set()

    for album in included_albums:
        source_folder = _album_source_folder(album)
        if not source_folder:
            skipped_sources.append(str(album.get("album") or album.get("title") or "Unknown release"))
            continue

        existing_child_id = _existing_split_child_id(db, split_history, source_folder)
        if existing_child_id is not None:
            skipped_child_batch_ids.append(existing_child_id)
            split_sources.add(_norm_match(source_folder))
            continue

        files_to_move = _files_for_source_folder(parent_batch.files, source_folder)
        if not files_to_move:
            skipped_sources.append(source_folder)
            continue

        album_metadata = _build_album_batch_metadata(
            album=album,
            parent_batch=parent_batch,
            files_to_move=files_to_move,
            source_folder=source_folder,
            candidate=None,
            identity_override=None,
        )
        child_batch = IngestBatch(
            source_kind=parent_batch.source_kind,
            source_path=parent_batch.source_path,
            detected_type="music_album",
            status="pending_review",
            confidence=max(parent_batch.confidence or 0.0, 0.7),
            suggested_destination=_library_album_destination(album_metadata),
            suggested_metadata=_suggested_metadata(album_metadata),
            metadata_json=album_metadata,
            metadata_confirmed=False,
            created_at=timestamp,
            updated_at=timestamp,
        )
        db.add(child_batch)
        db.flush()

        for ingest_file in files_to_move:
            ingest_file.batch_id = child_batch.id

        split_history.append({
            "candidate_id": None,
            "child_batch_id": child_batch.id,
            "source_folder": source_folder,
            "album": album_metadata.get("album") or album_metadata.get("title"),
            "artist": album_metadata.get("artist") or album_metadata.get("album_artist"),
            "moved_file_count": len(files_to_move),
            "split_at": timestamp.isoformat(),
            "source": "discography_editor_release_split",
        })
        created_child_batch_ids.append(child_batch.id)
        split_sources.add(_norm_match(source_folder))

    remaining_parent_file_count = db.query(IngestFile).filter(IngestFile.batch_id == parent_batch.id).count()

    if not created_child_batch_ids and not skipped_child_batch_ids and remaining_parent_file_count > 0:
        raise ValueError(
            "No child batches were created. Make sure each included release has a source folder with attached files."
        )

    remaining_albums = [
        album for album in albums
        if _norm_match(_album_source_folder(album)) not in split_sources
    ]
    batch_metadata["albums"] = remaining_albums
    batch_metadata["album_count"] = len(remaining_albums)
    batch_metadata["release_count"] = len(remaining_albums)
    batch_metadata["split_history"] = split_history
    db.flush()
    batch_metadata["materialized_child_count"] = len(split_history)
    batch_metadata["child_candidate_count"] = len(split_history)
    batch_metadata["remaining_parent_file_count"] = remaining_parent_file_count
    
    if remaining_parent_file_count == 0:
        batch_metadata["parent_review_state"] = "split_complete"
    else:
        batch_metadata["parent_review_state"] = "split_complete" if not remaining_albums else "parent_partially_materialized"
        
    parent_batch.status = "split_complete" if batch_metadata["parent_review_state"] == "split_complete" else "pending_review"
    parent_batch.metadata_json = batch_metadata
    parent_batch.updated_at = timestamp
    db.commit()
    db.refresh(parent_batch)

    created_count = len(created_child_batch_ids)
    skipped_count = len(skipped_child_batch_ids) + len(skipped_sources)
    message = (
        f"Created {created_count} child batch{'es' if created_count != 1 else ''} from included releases."
        if created_count
        else "Included release child batches already exist."
    )
    if skipped_sources:
        message += f" {len(skipped_sources)} release{'s' if len(skipped_sources) != 1 else ''} had no attached files and stayed on the parent."

    return {
        "parent_batch_id": parent_batch.id,
        "created_child_batch_ids": created_child_batch_ids,
        "existing_child_batch_ids": skipped_child_batch_ids,
        "created_count": created_count,
        "skipped_count": skipped_count,
        "remaining_parent_file_count": batch_metadata["remaining_parent_file_count"],
        "parent_status": parent_batch.status,
        "parent_review_state": batch_metadata["parent_review_state"],
        "message": message,
    }


def execute_split_candidate(db: Session, batch_id: int, candidate_id: int) -> dict[str, Any]:
    parent_batch = db.query(IngestBatch).options(selectinload(IngestBatch.files)).filter(IngestBatch.id == batch_id).first()
    if parent_batch is None:
        raise ValueError("Batch not found")
    if parent_batch.detected_type != "music_discography":
        raise ValueError("Only music discography batches can be split by candidate")
    if parent_batch.status in {"moved", "move_failed", "merged"}:
        raise ValueError("Moved or closed batches cannot be split")

    candidate = db.query(MediaIdentityCandidate).filter(
        MediaIdentityCandidate.id == candidate_id,
        MediaIdentityCandidate.batch_id == batch_id,
    ).first()
    if candidate is None:
        raise ValueError("Candidate not found for this batch")

    batch_metadata = deepcopy(parent_batch.metadata_json or {})
    identity_override = _latest_identity_override(db, batch_id, candidate_id)
    album, source_folder, files_to_move = _resolve_split_album_and_files(
        db,
        parent_batch,
        candidate,
        batch_metadata,
        identity_override,
    )

    timestamp = now_utc()
    album_metadata = _build_album_batch_metadata(
        album=album,
        parent_batch=parent_batch,
        files_to_move=files_to_move,
        source_folder=source_folder,
        candidate=candidate,
        identity_override=identity_override,
    )
    child_batch = IngestBatch(
        source_kind=parent_batch.source_kind,
        source_path=parent_batch.source_path,
        detected_type="music_album",
        status="pending_review",
        confidence=max(parent_batch.confidence or 0.0, 0.7),
        suggested_destination=_library_album_destination(album_metadata),
        suggested_metadata=_suggested_metadata(album_metadata),
        metadata_json=album_metadata,
        metadata_confirmed=False,
        created_at=timestamp,
        updated_at=timestamp,
    )
    db.add(child_batch)
    db.flush()

    moved_file_count = len(files_to_move)
    original_file_count = len(parent_batch.files)
    for ingest_file in files_to_move:
        ingest_file.batch_id = child_batch.id

    albums = [item for item in batch_metadata.get("albums", []) if isinstance(item, dict)]
    remaining_albums = [item for item in albums if _norm_match(_album_source_folder(item)) != _norm_match(source_folder)]
    batch_metadata["albums"] = remaining_albums
    batch_metadata["album_count"] = len(remaining_albums)
    batch_metadata["release_count"] = len(remaining_albums)
    split_history = batch_metadata.get("split_history") if isinstance(batch_metadata.get("split_history"), list) else []
    split_history.append({
        "candidate_id": candidate.id,
        "child_batch_id": child_batch.id,
        "source_folder": source_folder,
        "album": album_metadata.get("album") or album_metadata.get("title"),
        "artist": album_metadata.get("artist") or album_metadata.get("album_artist"),
        "moved_file_count": moved_file_count,
        "split_at": timestamp.isoformat(),
    })
    batch_metadata["split_history"] = split_history
    parent_batch.metadata_json = batch_metadata
    parent_batch.updated_at = timestamp
    if not remaining_albums:
        parent_batch.status = "split_complete"

    for action in _active_materialization_actions(db, batch_id, candidate.id):
        action.decision_status = "applied"
        action.updated_at = timestamp
        action.applied_at = timestamp

    db.commit()
    db.refresh(parent_batch)
    db.refresh(child_batch)

    return {
        "parent_batch_id": parent_batch.id,
        "child_batch_id": child_batch.id,
        "moved_file_count": moved_file_count,
        "remaining_parent_file_count": max(0, original_file_count - moved_file_count),
        "parent_status": parent_batch.status,
        "child_detected_type": child_batch.detected_type,
        "child_status": child_batch.status,
        "suggested_destination": child_batch.suggested_destination,
        "artist": child_batch.suggested_metadata.get("artist") if child_batch.suggested_metadata else None,
        "album": child_batch.suggested_metadata.get("album") if child_batch.suggested_metadata else None,
    }