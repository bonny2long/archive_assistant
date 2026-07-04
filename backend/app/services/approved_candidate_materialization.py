from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session, selectinload

from app.core.time import now_utc
from app.models.archive import IngestBatch, IngestFile
from app.models.media_metadata import CandidateMember, MediaIdentityCandidate, UniversalIngestionReviewAction
from app.services.batch_split import execute_split_candidate
from app.services.parent_candidate_materialization import (
    PARENT_SPLIT_COMPLETE,
    build_parent_candidate_summary,
)

CLOSED_PARENT_STATUSES = {"moved", "move_failed", "merged"}


def _active_candidate_decisions(db: Session, batch_id: int) -> dict[int, str]:
    decisions: dict[int, str] = {}
    actions = (
        db.query(UniversalIngestionReviewAction)
        .filter(
            UniversalIngestionReviewAction.batch_id == batch_id,
            UniversalIngestionReviewAction.candidate_id.isnot(None),
            UniversalIngestionReviewAction.action_type.in_({"approve_candidate", "exclude_from_move_plan"}),
            UniversalIngestionReviewAction.decision_status != "cleared",
        )
        .order_by(
            UniversalIngestionReviewAction.created_at.asc(),
            UniversalIngestionReviewAction.id.asc(),
        )
        .all()
    )
    for action in actions:
        decisions[int(action.candidate_id)] = action.action_type
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
    if "music" in value or "audio_track" in value:
        return "music_album"
    if "audiobook" in value or value == "audio":
        return "audiobook"
    if "book" in value or "ebook" in value or "comic" in value:
        return "book"
    if "movie" in value:
        return "video_movie"
    if "tv" in value or "show" in value:
        return "video_tv_show"
    return "unknown_type"


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
        metadata.update({
            "artist": creator,
            "albumartist": creator,
            "album": title,
            "track_count": len([file for file in files if file.detected_role in {"audio_track", "music_audio"}]),
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


def _materialize_generic_candidate(db: Session, parent_batch: IngestBatch, candidate: MediaIdentityCandidate) -> int:
    members = db.query(CandidateMember).filter(CandidateMember.candidate_id == candidate.id).all()
    batch_file_ids = [member.batch_file_id for member in members if member.batch_file_id]
    if not batch_file_ids:
        raise ValueError(f"Candidate {candidate.id} has no scoped batch files")
    files = db.query(IngestFile).filter(
        IngestFile.id.in_(batch_file_ids),
        IngestFile.batch_id == parent_batch.id,
    ).all()
    if not files:
        raise ValueError(f"Candidate {candidate.id} has no remaining parent files to materialize")

    detected_type = _candidate_detected_type(candidate)
    metadata = _candidate_metadata(candidate, files, parent_batch)
    timestamp = now_utc()
    child_batch = IngestBatch(
        source_kind=parent_batch.source_kind,
        source_path=parent_batch.source_path,
        detected_type=detected_type,
        status="pending_review",
        confidence=max(parent_batch.confidence or 0.0, candidate.candidate_confidence or 0.0, 0.7),
        suggested_destination=None,
        suggested_metadata=_suggested_metadata(candidate, detected_type),
        metadata_json=metadata,
        metadata_confirmed=False,
        created_at=timestamp,
        updated_at=timestamp,
    )
    db.add(child_batch)
    db.flush()

    for ingest_file in files:
        ingest_file.batch_id = child_batch.id

    _append_materialization_history(parent_batch, candidate, child_batch, len(files))
    _mark_candidate_materialized(db, parent_batch.id, candidate.id)
    parent_batch.updated_at = timestamp
    db.commit()
    db.refresh(child_batch)
    db.refresh(parent_batch)
    return child_batch.id


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
    if parent_summary["remaining_candidate_count"] > 0:
        raise ValueError("All candidate groups must be approved or excluded before child batches can be created")

    decisions = _active_candidate_decisions(db, batch_id)
    approved_candidate_ids = [candidate_id for candidate_id, action_type in decisions.items() if action_type == "approve_candidate"]
    if not approved_candidate_ids:
        raise ValueError("No approved candidate groups are available to materialize")

    candidates = {
        candidate.id: candidate
        for candidate in db.query(MediaIdentityCandidate)
        .filter(MediaIdentityCandidate.batch_id == batch_id, MediaIdentityCandidate.id.in_(approved_candidate_ids))
        .all()
    }

    child_batch_ids: list[int] = []
    created_count = 0
    skipped_count = 0
    for candidate_id in approved_candidate_ids:
        candidate = candidates.get(candidate_id)
        if candidate is None:
            skipped_count += 1
            continue
        existing_child_id = _existing_child_batch_id(db, parent_batch, candidate_id)
        if existing_child_id is not None:
            child_batch_ids.append(existing_child_id)
            _mark_candidate_materialized(db, batch_id, candidate_id)
            skipped_count += 1
            continue

        if parent_batch.detected_type == "music_discography":
            result = execute_split_candidate(db, batch_id, candidate_id)
            child_batch_ids.append(int(result["child_batch_id"]))
        else:
            child_batch_ids.append(_materialize_generic_candidate(db, parent_batch, candidate))
        created_count += 1
        parent_batch = (
            db.query(IngestBatch)
            .options(selectinload(IngestBatch.files))
            .filter(IngestBatch.id == batch_id)
            .first()
        )

    parent_batch.status = PARENT_SPLIT_COMPLETE
    parent_batch.updated_at = now_utc()
    db.commit()
    db.refresh(parent_batch)
    message = (
        f"Created {created_count} child batch{'es' if created_count != 1 else ''}. Parent marked split complete."
        if created_count
        else "Approved child batches already exist. Parent marked split complete."
    )
    return {
        "parent_batch_id": parent_batch.id,
        "created_child_batch_ids": child_batch_ids,
        "created_count": created_count,
        "skipped_count": skipped_count,
        "parent_review_state": PARENT_SPLIT_COMPLETE,
        "message": message,
    }
