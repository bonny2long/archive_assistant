from __future__ import annotations

from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session, selectinload

from app.core.time import now_utc
from app.models.archive import IngestBatch, IngestFile
from app.models.media_metadata import CandidateMember, MediaIdentityCandidate, UniversalIngestionReviewAction
from app.services.batch_split import (
    _album_from_candidate_and_files,
    _build_album_batch_metadata,
    _library_album_destination,
    _suggested_metadata as _music_suggested_metadata,
)
from app.services.destination_authority import rebuild_music_batch_destination_from_attached_files
from app.services.parent_candidate_materialization import (
    PARENT_PARTIALLY_MATERIALIZED,
    PARENT_SPLIT_COMPLETE,
    build_parent_candidate_summary,
)

CLOSED_PARENT_STATUSES = {"moved", "move_failed", "merged"}
GENERIC_AUDIO_EXTENSIONS = {".mp3", ".flac", ".m4a", ".aac", ".wav", ".ogg", ".opus", ".wma", ".aiff", ".alac"}


class MaterializationError(ValueError):
    pass


def _active_candidate_decisions(db: Session, batch_id: int, candidate_ids: set[int] | None = None) -> dict[int, str]:
    decisions: dict[int, str] = {}
    actions = (
        db.query(UniversalIngestionReviewAction)
        .filter(
            UniversalIngestionReviewAction.batch_id == batch_id,
            UniversalIngestionReviewAction.candidate_id.isnot(None),
            UniversalIngestionReviewAction.action_type.in_({"approve_candidate", "exclude_from_move_plan", "mark_review_later", "block_candidate"}),
            UniversalIngestionReviewAction.decision_status != "cleared",
        )
        .order_by(
            UniversalIngestionReviewAction.created_at.asc(),
            UniversalIngestionReviewAction.id.asc(),
        )
        .all()
    )
    for action in actions:
        candidate_id = int(action.candidate_id)
        if candidate_ids is not None and candidate_id not in candidate_ids:
            continue
        decisions[candidate_id] = action.action_type
    return decisions


def _history_entries(metadata: dict[str, Any]) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    for key in ("split_history", "materialization_history"):
        value = metadata.get(key)
        if isinstance(value, list):
            entries.extend(item for item in value if isinstance(item, dict))
    return entries


def _existing_child_batch_id(db: Session, parent_batch: IngestBatch, candidate_id: int) -> int | None:
    metadata = parent_batch.metadata_json or {}
    for entry in _history_entries(metadata):
        if int(entry.get("candidate_id") or 0) != candidate_id:
            continue
        child_id = int(entry.get("child_batch_id") or 0)
        if child_id and db.get(IngestBatch, child_id) is not None:
            return child_id
    return None


def _candidate_detected_type(candidate: MediaIdentityCandidate) -> str:
    value = (candidate.candidate_media_type or "unknown").casefold()
    if "music" in value or "audio_track" in value or "discography_track" in value:
        return "music_album"
    if "audiobook" in value or value == "audio":
        return "audiobook"
    if "comic" in value:
        return "book"
    if "book" in value or "ebook" in value:
        return "book"
    if "movie" in value:
        return "video_movie"
    if "tv" in value or "show" in value:
        return "video_tv_show"
    if "art" in value:
        return "unknown_type"
    return "unknown_type"


def _candidate_source_folder(candidate: MediaIdentityCandidate, files: list[IngestFile]) -> str:
    evidence = candidate.identity_evidence_json or {}
    for key in ("source_folder", "folder", "source"):
        value = evidence.get(key)
        if value:
            return str(value).strip()
    if files:
        path = Path(files[0].file_path or files[0].file_name or "")
        parent = path.parent.name
        if parent:
            return parent
    return str(candidate.candidate_key or candidate.id)


def _is_generic_audio_file(file: IngestFile) -> bool:
    role = str(file.detected_role or "").casefold()
    ext = str(file.extension or Path(file.file_name or "").suffix).casefold()
    return ext in GENERIC_AUDIO_EXTENSIONS or role in {"audio", "audio_track", "music_audio", "music_track", "discography_track"}


def _candidate_metadata(candidate: MediaIdentityCandidate, files: list[IngestFile], parent_batch: IngestBatch) -> dict[str, Any]:
    detected_type = _candidate_detected_type(candidate)
    title = candidate.candidate_title or "Unknown Title"
    creator = candidate.candidate_primary_creator or "Unknown Creator"
    metadata: dict[str, Any] = {
        "metadata_assist_version": "parent_candidate_materialization_v1",
        "source_parent_batch_id": parent_batch.id,
        "source_parent_path": parent_batch.source_path,
        "source_candidate_id": candidate.id,
        "candidate_key": candidate.candidate_key,
        "file_count": len(files),
        "files": [file.file_name for file in files],
        "year": candidate.candidate_year,
        "metadata_quality": "fair",
        "metadata_warnings": [],
    }
    if detected_type == "music_album":
        audio_files = [file for file in files if _is_generic_audio_file(file)]
        metadata.update({
            "artist": creator,
            "albumartist": creator,
            "album": title,
            "title": title,
            "type": "music_album",
            "review_type": "music_album",
            "track_count": len(audio_files),
            "audio_files": [file.file_name for file in audio_files],
        })
    elif detected_type == "audiobook":
        metadata.update({
            "author": creator,
            "title": title,
            "audiobook_file_count": len(files),
            "audio_files": [file.file_name for file in files],
        })
    elif detected_type == "video_movie":
        metadata.update({
            "title": title,
            "video_file_count": len(files),
            "video_files": [file.file_name for file in files],
        })
    elif detected_type == "video_tv_show":
        metadata.update({
            "show_title": title,
            "video_file_count": len(files),
            "video_files": [file.file_name for file in files],
        })
    else:
        metadata.update({
            "title": title,
            "author": creator,
            "book_file_count": len(files),
            "book_files": [file.file_name for file in files],
        })
    return metadata


def _suggested_metadata(candidate: MediaIdentityCandidate, detected_type: str) -> dict[str, Any]:
    title = candidate.candidate_title or "Unknown Title"
    creator = candidate.candidate_primary_creator or "Unknown Creator"
    if detected_type == "music_album":
        return {"artist": creator, "album": title, "year": candidate.candidate_year}
    if detected_type == "audiobook":
        return {"author": creator, "title": title, "year": candidate.candidate_year}
    if detected_type == "video_movie":
        return {"title": title, "year": candidate.candidate_year}
    if detected_type == "video_tv_show":
        return {"show_title": title, "year": candidate.candidate_year}
    return {"title": title, "author": creator, "year": candidate.candidate_year}


def _append_materialization_history(parent_batch: IngestBatch, candidate: MediaIdentityCandidate, child_batch: IngestBatch, file_count: int) -> None:
    metadata = dict(parent_batch.metadata_json or {})
    history = metadata.get("materialization_history")
    if not isinstance(history, list):
        history = []
    if not any(int(item.get("candidate_id") or 0) == candidate.id for item in history if isinstance(item, dict)):
        history.append({
            "candidate_id": candidate.id,
            "child_batch_id": child_batch.id,
            "title": candidate.candidate_title,
            "creator": candidate.candidate_primary_creator,
            "file_count": file_count,
            "materialized_at": now_utc().isoformat(),
        })
    metadata["materialization_history"] = history
    parent_batch.metadata_json = metadata


def _mark_candidate_materialized(db: Session, batch_id: int, candidate_id: int) -> None:
    timestamp = now_utc()
    actions = db.query(UniversalIngestionReviewAction).filter(
        UniversalIngestionReviewAction.batch_id == batch_id,
        UniversalIngestionReviewAction.candidate_id == candidate_id,
        UniversalIngestionReviewAction.action_type.in_({"approve_candidate", "split_candidate"}),
        UniversalIngestionReviewAction.decision_status != "cleared",
    ).all()
    for action in actions:
        action.decision_status = "applied"
        action.applied_at = action.applied_at or timestamp
        action.updated_at = timestamp


def _candidate_member_file_ids(db: Session, candidate_id: int) -> list[int]:
    ids = [
        int(file_id)
        for (file_id,) in db.query(CandidateMember.batch_file_id)
        .filter(CandidateMember.candidate_id == candidate_id, CandidateMember.batch_file_id.isnot(None))
        .all()
    ]
    return list(dict.fromkeys(ids))


def _existing_child_from_candidate_files(db: Session, candidate: MediaIdentityCandidate, file_ids: list[int], parent_batch_id: int) -> int | None:
    if not file_ids:
        return None
    files = db.query(IngestFile).filter(IngestFile.id.in_(file_ids)).all()
    child_ids = {file.batch_id for file in files if file.batch_id and file.batch_id != parent_batch_id}
    for child_id in child_ids:
        child = db.get(IngestBatch, child_id)
        metadata = child.metadata_json if child else None
        if isinstance(metadata, dict) and int(metadata.get("source_candidate_id") or 0) == candidate.id:
            return child_id
    return None


def _candidate_parent_files(db: Session, parent_batch: IngestBatch, candidate: MediaIdentityCandidate) -> list[IngestFile]:
    file_ids = _candidate_member_file_ids(db, candidate.id)
    if not file_ids:
        raise MaterializationError("Candidate has no scoped files available for materialization.")
    existing_child_id = _existing_child_from_candidate_files(db, candidate, file_ids, parent_batch.id)
    if existing_child_id is not None:
        return []
    files = db.query(IngestFile).filter(
        IngestFile.id.in_(file_ids),
        IngestFile.batch_id == parent_batch.id,
    ).all()
    if not files:
        raise MaterializationError("Candidate has no scoped files available for materialization.")
    return files


def _music_child_metadata(candidate: MediaIdentityCandidate, files: list[IngestFile], parent_batch: IngestBatch) -> dict[str, Any]:
    source_folder = _candidate_source_folder(candidate, files)
    album = _album_from_candidate_and_files(candidate, None, files, source_folder)
    metadata = _build_album_batch_metadata(
        album=album,
        parent_batch=parent_batch,
        files_to_move=files,
        source_folder=source_folder,
        candidate=candidate,
        identity_override=None,
    )
    metadata["metadata_assist_version"] = "parent_candidate_materialization_v1"
    metadata["source_parent_batch_id"] = parent_batch.id
    metadata["source_parent_path"] = parent_batch.source_path
    metadata["source_candidate_id"] = candidate.id
    metadata["candidate_key"] = candidate.candidate_key
    metadata["review_origin"] = "approved_candidate_materialization"
    return metadata


def _create_child_batch(db: Session, parent_batch: IngestBatch, candidate: MediaIdentityCandidate, files: list[IngestFile]) -> int:
    detected_type = _candidate_detected_type(candidate)
    if detected_type == "music_album":
        metadata = _music_child_metadata(candidate, files, parent_batch)
        suggested_metadata = _music_suggested_metadata(metadata)
        suggested_destination = _library_album_destination(metadata)
    else:
        metadata = _candidate_metadata(candidate, files, parent_batch)
        suggested_metadata = _suggested_metadata(candidate, detected_type)
        suggested_destination = None

    timestamp = now_utc()
    child_batch = IngestBatch(
        source_kind=parent_batch.source_kind,
        source_path=parent_batch.source_path,
        detected_type=detected_type,
        status="pending_review",
        confidence=max(parent_batch.confidence or 0.0, candidate.candidate_confidence or 0.0, 0.7),
        suggested_destination=suggested_destination,
        suggested_metadata=suggested_metadata,
        metadata_json=metadata,
        metadata_confirmed=False,
        created_at=timestamp,
        updated_at=timestamp,
    )
    db.add(child_batch)
    db.flush()
    for ingest_file in files:
        ingest_file.batch_id = child_batch.id
    child_batch.files = list(files)
    if detected_type == "music_album":
        rebuild_music_batch_destination_from_attached_files(child_batch, db)
    _append_materialization_history(parent_batch, candidate, child_batch, len(files))
    _mark_candidate_materialized(db, parent_batch.id, candidate.id)
    parent_batch.updated_at = timestamp
    return child_batch.id


def _materialize_candidate(db: Session, parent_batch: IngestBatch, candidate: MediaIdentityCandidate) -> tuple[int, bool]:
    existing_child_id = _existing_child_batch_id(db, parent_batch, candidate.id)
    if existing_child_id is not None:
        _mark_candidate_materialized(db, parent_batch.id, candidate.id)
        return existing_child_id, False

    file_ids = _candidate_member_file_ids(db, candidate.id)
    existing_from_files = _existing_child_from_candidate_files(db, candidate, file_ids, parent_batch.id)
    if existing_from_files is not None:
        _append_materialization_history(parent_batch, candidate, db.get(IngestBatch, existing_from_files), 0)
        _mark_candidate_materialized(db, parent_batch.id, candidate.id)
        return existing_from_files, False

    files = _candidate_parent_files(db, parent_batch, candidate)
    return _create_child_batch(db, parent_batch, candidate, files), True


def materialize_approved_candidates(db: Session, batch_id: int) -> dict[str, Any]:
    parent_batch = (
        db.query(IngestBatch)
        .options(selectinload(IngestBatch.files))
        .filter(IngestBatch.id == batch_id)
        .first()
    )
    if parent_batch is None:
        raise ValueError("Batch not found")
    if parent_batch.status in CLOSED_PARENT_STATUSES:
        raise ValueError("Moved or closed batches cannot be materialized")

    parent_summary = build_parent_candidate_summary(db, parent_batch)
    if not parent_summary["is_parent_review_container"]:
        raise ValueError("Batch is not a parent review container")
    current_candidates = {
        candidate.id: candidate
        for candidate in db.query(MediaIdentityCandidate)
        .filter(MediaIdentityCandidate.batch_id == batch_id)
        .all()
    }
    decisions = _active_candidate_decisions(db, batch_id, set(current_candidates))
    approved_candidate_ids = [candidate_id for candidate_id, action_type in decisions.items() if action_type == "approve_candidate"]
    if not approved_candidate_ids:
        raise ValueError("No approved current candidate groups are available to materialize. Approve safe candidate groups before creating child batches.")

    candidates = {
        candidate_id: current_candidates[candidate_id]
        for candidate_id in approved_candidate_ids
        if candidate_id in current_candidates
    }
    candidate_id_set = set(current_candidates)
    blocked_candidate_ids = sorted(candidate_id for candidate_id, action_type in decisions.items() if action_type == "block_candidate")
    excluded_candidate_ids = sorted(candidate_id for candidate_id, action_type in decisions.items() if action_type == "exclude_from_move_plan")
    review_later_candidate_ids = sorted(candidate_id for candidate_id, action_type in decisions.items() if action_type == "mark_review_later")
    decisioned_ids = set(approved_candidate_ids) | set(blocked_candidate_ids) | set(excluded_candidate_ids) | set(review_later_candidate_ids)
    unresolved_candidate_ids = sorted(candidate_id_set - decisioned_ids)

    child_batch_ids: list[int] = []
    materialized_candidate_ids: list[int] = []
    created_count = 0
    skipped_count = 0
    try:
        for candidate_id in approved_candidate_ids:
            candidate = candidates.get(candidate_id)
            if candidate is None:
                raise MaterializationError("Some approved candidates could not be materialized.")
            child_id, created = _materialize_candidate(db, parent_batch, candidate)
            child_batch_ids.append(child_id)
            materialized_candidate_ids.append(candidate_id)
            if created:
                created_count += 1
            else:
                skipped_count += 1

        timestamp = now_utc()
        metadata = dict(parent_batch.metadata_json or {})
        partial_audit = list(metadata.get("partial_materialization_audit") or [])
        partial_audit.append({
            "parent_batch_id": parent_batch.id,
            "materialized_candidate_ids": sorted(materialized_candidate_ids),
            "blocked_candidate_ids": blocked_candidate_ids,
            "excluded_candidate_ids": excluded_candidate_ids,
            "review_later_candidate_ids": review_later_candidate_ids,
            "unresolved_candidate_ids": unresolved_candidate_ids,
            "created_child_batch_ids": child_batch_ids,
            "materialized_at": timestamp.isoformat(),
        })
        metadata["partial_materialization_audit"] = partial_audit
        metadata["child_candidate_count"] = len(candidate_id_set)
        metadata["materialized_child_count"] = len({
            int(item.get("candidate_id") or 0)
            for item in metadata.get("materialization_history") or []
            if isinstance(item, dict) and item.get("candidate_id")
        })
        metadata["blocked_candidate_count"] = len(blocked_candidate_ids)
        metadata["excluded_candidate_count"] = len(excluded_candidate_ids)
        metadata["review_later_candidate_count"] = len(review_later_candidate_ids)
        remaining_parent_file_count = db.query(IngestFile).filter(IngestFile.batch_id == parent_batch.id).count()
        metadata["remaining_parent_file_count"] = remaining_parent_file_count
        metadata["unresolved_candidate_count"] = len(unresolved_candidate_ids)
        if remaining_parent_file_count > 0 and metadata["unresolved_candidate_count"] == 0:
            metadata["unresolved_candidate_count"] = 1
        all_candidates_materialized = (
            metadata["materialized_child_count"] >= len(candidate_id_set)
            and remaining_parent_file_count == 0
        )
        parent_batch.status = PARENT_SPLIT_COMPLETE if all_candidates_materialized else "pending_review"
        metadata["parent_review_state"] = PARENT_SPLIT_COMPLETE if all_candidates_materialized else PARENT_PARTIALLY_MATERIALIZED
        parent_batch.metadata_json = metadata
        parent_batch.updated_at = timestamp
        db.commit()
    except Exception:
        db.rollback()
        raise

    db.refresh(parent_batch)
    parent_summary = build_parent_candidate_summary(db, parent_batch)
    parent_state = parent_summary["parent_review_state"]
    remaining_detail = parent_summary["unresolved_candidate_count"] + parent_summary["review_later_candidate_count"] + parent_summary["blocked_candidate_count"]
    message = (
        f"Created {created_count} child batch{'es' if created_count != 1 else ''}. {remaining_detail} candidate{'s' if remaining_detail != 1 else ''} remain on the parent."
        if created_count and parent_state != PARENT_SPLIT_COMPLETE
        else f"Created {created_count} child batch{'es' if created_count != 1 else ''}. Parent marked split complete."
        if created_count
        else f"Approved child batches already exist. {remaining_detail} candidate{'s' if remaining_detail != 1 else ''} remain on the parent."
        if parent_state != PARENT_SPLIT_COMPLETE
        else "Approved child batches already exist. Parent marked split complete."
    )
    return {
        "parent_batch_id": parent_batch.id,
        "created_child_batch_ids": child_batch_ids,
        "created_count": created_count,
        "skipped_count": skipped_count,
        "materialized_child_count": parent_summary["materialized_child_count"],
        "unresolved_candidate_count": parent_summary["unresolved_candidate_count"],
        "blocked_candidate_count": parent_summary["blocked_candidate_count"],
        "excluded_candidate_count": parent_summary["excluded_candidate_count"],
        "review_later_candidate_count": parent_summary["review_later_candidate_count"],
        "parent_review_state": parent_state,
        "message": message,
    }
