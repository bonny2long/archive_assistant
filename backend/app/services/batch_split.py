from __future__ import annotations

import re
from copy import deepcopy
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session, selectinload

from app.core.config import settings
from app.core.time import now_utc
from app.models.archive import IngestBatch, IngestFile
from app.models.media_metadata import MediaIdentityCandidate, UniversalIngestionReviewAction

_SAFE_PART_PATTERN = re.compile(r'[<>:"/\\|?*]+')
_UNKNOWN_IDENTITY_VALUES = {"", "unknown", "unknown artist", "unknown album", "various artists"}


def safe_path_part(value: object, fallback: str = "Unknown") -> str:
    text = str(value or "").strip()
    if not text:
        text = fallback
    text = _SAFE_PART_PATTERN.sub(" ", text)
    text = re.sub(r"\s+", " ", text).strip(" .")
    return text or fallback


def _match_text(value: object) -> str:
    text = str(value or "").strip().casefold()
    return "" if text in _UNKNOWN_IDENTITY_VALUES else text


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


def _candidate_title(candidate: MediaIdentityCandidate, override: UniversalIngestionReviewAction | None) -> str:
    return _match_text(override.override_title if override and override.override_title else candidate.candidate_title)


def _candidate_artist(candidate: MediaIdentityCandidate, override: UniversalIngestionReviewAction | None) -> str:
    return _match_text(
        override.override_primary_creator
        if override and override.override_primary_creator
        else candidate.candidate_primary_creator
    )


def _candidate_year(candidate: MediaIdentityCandidate, override: UniversalIngestionReviewAction | None) -> str:
    return _match_text(override.override_year if override and override.override_year else candidate.candidate_year)


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
    title = _match_text(album.get("album") or album.get("title"))
    artist = _match_text(album.get("artist") or album.get("album_artist"))
    year = _match_text(album.get("year"))
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
    if title and candidate_title and title == candidate_title:
        artist_matches = not artist or not candidate_artist or artist == candidate_artist
        year_matches = not year or not candidate_year or year == candidate_year
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
    normalized = source_folder.casefold()
    return [ingest_file for ingest_file in files if (_file_album_source_folder(ingest_file) or "").casefold() == normalized]


def _library_album_destination(album: dict[str, Any]) -> str:
    artist = safe_path_part(album.get("artist") or album.get("album_artist") or "Unknown Artist", "Unknown Artist")
    title = safe_path_part(album.get("album") or album.get("title") or "Unknown Album", "Unknown Album")
    year = safe_path_part(album.get("year") or "", "").strip()
    album_folder = f"{year} - {title}" if year else title
    return str(Path(settings.music_mp3_dir) / artist / album_folder)


def _build_album_batch_metadata(album: dict[str, Any], parent_batch: IngestBatch) -> dict[str, Any]:
    metadata = deepcopy(album)
    metadata["type"] = "music_album"
    metadata["split_from_batch_id"] = parent_batch.id
    metadata["split_from_source_path"] = parent_batch.source_path
    metadata["split_source_folder"] = _album_source_folder(album)
    metadata["review_origin"] = "multi_artist_discography_split"
    return metadata


def _suggested_metadata(album: dict[str, Any]) -> dict[str, Any]:
    return {
        "artist": album.get("artist") or album.get("album_artist") or "Unknown Artist",
        "album": album.get("album") or album.get("title") or "Unknown Album",
        "year": album.get("year"),
        "primary_genre": album.get("primary_genre") or album.get("genre"),
    }


def _active_split_actions(db: Session, batch_id: int, candidate_id: int) -> list[UniversalIngestionReviewAction]:
    return db.query(UniversalIngestionReviewAction).filter(
        UniversalIngestionReviewAction.batch_id == batch_id,
        UniversalIngestionReviewAction.candidate_id == candidate_id,
        UniversalIngestionReviewAction.action_type == "split_candidate",
        UniversalIngestionReviewAction.decision_status != "cleared",
    ).all()


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
    album = _find_album_for_candidate(candidate, batch_metadata, identity_override)
    if album is None:
        raise ValueError("Could not match candidate to a discography album")

    source_folder = _album_source_folder(album)
    if not source_folder:
        raise ValueError("Matched album has no source_folder")

    files_to_move = _files_for_source_folder(parent_batch.files, source_folder)
    if not files_to_move:
        raise ValueError("No ingest files matched the selected album")

    timestamp = now_utc()
    album_metadata = _build_album_batch_metadata(album, parent_batch)
    child_batch = IngestBatch(
        source_kind=parent_batch.source_kind,
        source_path=parent_batch.source_path,
        detected_type="music_album",
        status="pending_review",
        confidence=max(parent_batch.confidence or 0.0, 0.7),
        suggested_destination=_library_album_destination(album),
        suggested_metadata=_suggested_metadata(album),
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
    remaining_albums = [item for item in albums if (_album_source_folder(item) or "").casefold() != source_folder.casefold()]
    batch_metadata["albums"] = remaining_albums
    batch_metadata["album_count"] = len(remaining_albums)
    batch_metadata["release_count"] = len(remaining_albums)
    split_history = batch_metadata.get("split_history") if isinstance(batch_metadata.get("split_history"), list) else []
    split_history.append({
        "candidate_id": candidate.id,
        "child_batch_id": child_batch.id,
        "source_folder": source_folder,
        "album": album.get("album") or album.get("title"),
        "artist": album.get("artist") or album.get("album_artist"),
        "moved_file_count": moved_file_count,
        "split_at": timestamp.isoformat(),
    })
    batch_metadata["split_history"] = split_history
    parent_batch.metadata_json = batch_metadata
    parent_batch.updated_at = timestamp
    if not remaining_albums:
        parent_batch.status = "split_complete"

    for action in _active_split_actions(db, batch_id, candidate_id):
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