from __future__ import annotations

from typing import Any

from sqlalchemy import case, func, or_
from sqlalchemy.orm import Session

from app.models.archive import IngestBatch, IngestFile
from app.models.media_metadata import MediaIdentityCandidate, UniversalIngestionReviewAction


# Legacy parent_review_state values kept for response/history compatibility; current workflow uses parent_container_state.
PARENT_REVIEW_IN_PROGRESS = "review_in_progress"
PARENT_CANDIDATES_APPROVED_WAITING_MATERIALIZATION = "candidates_approved_waiting_materialization"
PARENT_PARTIALLY_MATERIALIZED = "parent_partially_materialized"
PARENT_SPLIT_COMPLETE = "split_complete"
PARENT_CONTAINER_ACTIVE = "active_parent_container"
PARENT_CONTAINER_PARTIAL = "partial_parent_container"
PARENT_CONTAINER_DRAINED = "drained_parent"
PARENT_CONTAINER_TYPES = {"music_discography"}

SUPPORT_FILE_EXTENSIONS = {
    ".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp", ".tiff",
    ".txt", ".log", ".cue", ".m3u", ".m3u8", ".nfo", ".sfv", ".md5", ".ffp",
    ".json", ".xml", ".opf", ".srt", ".ass", ".vtt", ".sub", ".lrc",
}
SUPPORT_FILE_ROLES = {
    "artwork", "cover_art", "album_artwork", "movie_artwork", "tv_artwork",
    "audiobook_artwork", "book_artwork", "sidecar", "metadata_sidecar",
    "playlist", "log", "subtitle",
}

MATERIALIZATION_DECISION_ACTIONS = {
    "approve_candidate",
    "exclude_from_move_plan",
    "mark_review_later",
    "block_candidate",
}


def is_parent_container_batch(batch: IngestBatch) -> bool:
    metadata = batch.metadata_json or {}
    if batch.detected_type in PARENT_CONTAINER_TYPES:
        return True
    has_own_split_evidence = bool(
        metadata.get("materialization_history")
        or metadata.get("split_history")
        or metadata.get("discography_split_audit")
    )
    if has_own_split_evidence:
        return True
    if metadata.get("split_from_batch_id") or metadata.get("source_parent_batch_id"):
        return False
    return bool(metadata.get("parent_review_state"))


def get_child_batch_count(batch: IngestBatch, db: Session) -> int:
    if batch.id is None:
        return 0
    return int(
        db.query(IngestBatch.id)
        .filter(
            IngestBatch.id != batch.id,
            or_(
                IngestBatch.metadata_json["split_from_batch_id"].as_integer() == batch.id,
                IngestBatch.metadata_json["source_parent_batch_id"].as_integer() == batch.id,
            ),
        )
        .count()
    )


def get_active_parent_file_count(batch: IngestBatch, db: Session) -> int:
    return db.query(IngestFile).filter(IngestFile.batch_id == batch.id).count()


def active_parent_file_count(db: Session, batch: IngestBatch) -> int:
    return get_active_parent_file_count(batch, db)


def get_parent_file_inventory(batch: IngestBatch, db: Session) -> dict[str, int]:
    if batch.id is None:
        return {"total": 0, "primary": 0, "support": 0}
    support_condition = or_(
        func.lower(IngestFile.extension).in_(SUPPORT_FILE_EXTENSIONS),
        func.lower(IngestFile.detected_role).in_(SUPPORT_FILE_ROLES),
    )
    total, support = db.query(
        func.count(IngestFile.id),
        func.coalesce(func.sum(case((support_condition, 1), else_=0)), 0),
    ).filter(IngestFile.batch_id == batch.id).one()
    total_count = int(total or 0)
    support_count = int(support or 0)
    return {
        "total": total_count,
        "primary": max(0, total_count - support_count),
        "support": support_count,
    }


def _actual_child_batch_count(db: Session, parent_batch_id: int) -> int:
    batch = db.get(IngestBatch, parent_batch_id)
    return get_child_batch_count(batch, db) if batch else 0


def get_parent_container_display_state(batch: IngestBatch, db: Session) -> str | None:
    if not is_parent_container_batch(batch):
        return None
    child_count = get_child_batch_count(batch, db)
    active_file_count = get_active_parent_file_count(batch, db)
    if child_count > 0 and active_file_count == 0:
        return PARENT_CONTAINER_DRAINED
    if child_count > 0 and active_file_count > 0:
        return PARENT_CONTAINER_PARTIAL
    if active_file_count > 0:
        return PARENT_CONTAINER_ACTIVE
    return None


def is_drained_parent(batch: IngestBatch, db: Session) -> bool:
    return get_parent_container_display_state(batch, db) == PARENT_CONTAINER_DRAINED


def _parent_container_flags(
    state: str | None,
    active_file_count: int,
    child_batch_count: int,
    primary_file_count: int = 0,
    support_file_count: int = 0,
) -> dict[str, Any]:
    media_extraction_complete = primary_file_count == 0 and (child_batch_count > 0 or support_file_count > 0)
    extraction_state = (
        "complete"
        if state == PARENT_CONTAINER_DRAINED
        else "media_extracted"
        if media_extraction_complete and child_batch_count > 0
        else "support_only"
        if media_extraction_complete
        else "in_progress"
        if child_batch_count > 0
        else "not_started"
    )
    return {
        "parent_container_state": state,
        "display_state": state,
        "parent_is_drained": state == PARENT_CONTAINER_DRAINED,
        "parent_media_extraction_complete": media_extraction_complete,
        "parent_extraction_state": extraction_state,
        "approval_allowed": False if state else True,
        "move_ready": False,
        "requires_review": state in {PARENT_CONTAINER_ACTIVE, PARENT_CONTAINER_PARTIAL} and not media_extraction_complete,
        "active_parent_file_count": active_file_count,
        "active_file_count": active_file_count,
        "remaining_primary_file_count": primary_file_count,
        "remaining_support_file_count": support_file_count,
        "parent_has_remaining_files": active_file_count > 0,
        "child_batch_count": child_batch_count,
    }


def empty_parent_candidate_summary() -> dict[str, Any]:
    return {
        "candidate_group_count": 0,
        "approved_candidate_count": 0,
        "excluded_candidate_count": 0,
        "blocked_candidate_count": 0,
        "review_later_candidate_count": 0,
        "unresolved_candidate_count": 0,
        "materialized_child_count": 0,
        "child_candidate_count": 0,
        "remaining_candidate_count": 0,
        "needs_materialization": False,
        "parent_review_state": None,
        "parent_container_state": None,
        "is_parent_review_container": False,
        "parent_is_drained": False,
        "parent_media_extraction_complete": False,
        "parent_extraction_state": None,
        "display_state": None,
        "approval_allowed": True,
        "move_ready": False,
        "requires_review": False,
        "active_parent_file_count": 0,
        "active_file_count": 0,
        "remaining_primary_file_count": 0,
        "remaining_support_file_count": 0,
        "child_batch_count": 0,
        "parent_has_remaining_files": False,
        "historical_scan_snapshot": False,
    }


def build_parent_candidate_summary(db: Session | None, batch: IngestBatch) -> dict[str, Any]:
    """Derive review-container state from DB-owned children/files and active audit actions."""
    if db is None:
        return empty_parent_candidate_summary()

    metadata = batch.metadata_json or {}
    candidate_ids = [
        candidate_id
        for (candidate_id,) in db.query(MediaIdentityCandidate.id)
        .filter(MediaIdentityCandidate.batch_id == batch.id)
        .all()
    ]
    candidate_group_count = len(candidate_ids)
    explicit_parent_container = is_parent_container_batch(batch)
    if not explicit_parent_container and candidate_group_count <= 1:
        return empty_parent_candidate_summary() | {
            "candidate_group_count": candidate_group_count,
            "remaining_candidate_count": candidate_group_count,
        }

    file_inventory = get_parent_file_inventory(batch, db) if explicit_parent_container else {"total": 0, "primary": 0, "support": 0}
    remaining_parent_file_count = file_inventory["total"]
    remaining_primary_file_count = file_inventory["primary"]
    remaining_support_file_count = file_inventory["support"]
    actual_child_count = get_child_batch_count(batch, db)
    if explicit_parent_container:
        if actual_child_count > 0 and remaining_parent_file_count == 0:
            parent_container_state = PARENT_CONTAINER_DRAINED
        elif actual_child_count > 0 and remaining_parent_file_count > 0:
            parent_container_state = PARENT_CONTAINER_PARTIAL
        elif remaining_parent_file_count > 0:
            parent_container_state = PARENT_CONTAINER_ACTIVE
        else:
            parent_container_state = None
    else:
        parent_container_state = None

    if parent_container_state == PARENT_CONTAINER_DRAINED:
        return empty_parent_candidate_summary() | {
            "candidate_group_count": actual_child_count,
            "materialized_child_count": actual_child_count,
            "child_candidate_count": actual_child_count,
            "remaining_candidate_count": 0,
            "needs_materialization": False,
            "parent_review_state": PARENT_SPLIT_COMPLETE,
            "is_parent_review_container": True,
            **_parent_container_flags(PARENT_CONTAINER_DRAINED, 0, actual_child_count, 0, 0),
            "historical_scan_snapshot": True,
        }

    metadata_parent_state = metadata.get("parent_review_state")

    if metadata_parent_state in {PARENT_PARTIALLY_MATERIALIZED, PARENT_SPLIT_COMPLETE}:
        historical_child_batch_count = actual_child_count
        extractable_count = int(metadata.get("extractable_candidate_count") or 0)
        review_later_count = int(metadata.get("review_later_candidate_count") or 0)
        excluded_count = int(metadata.get("excluded_candidate_count") or 0)
        blocked_count = int(metadata.get("blocked_candidate_count") or 0)
        unresolved_count = int(metadata.get("unresolved_candidate_count") or 0)
        explicit_remaining = extractable_count + review_later_count + excluded_count + blocked_count + unresolved_count
        remaining_candidate_count = explicit_remaining or (1 if remaining_parent_file_count > 0 else 0)
        parent_review_state = PARENT_REVIEW_IN_PROGRESS if remaining_parent_file_count > 0 else PARENT_SPLIT_COMPLETE
        state = parent_container_state or (PARENT_CONTAINER_PARTIAL if remaining_parent_file_count > 0 else None)
        return {
            "candidate_group_count": historical_child_batch_count + remaining_candidate_count,
            "approved_candidate_count": 0,
            "excluded_candidate_count": excluded_count,
            "blocked_candidate_count": blocked_count,
            "review_later_candidate_count": review_later_count,
            "unresolved_candidate_count": unresolved_count or (1 if remaining_parent_file_count > 0 and explicit_remaining == 0 else 0),
            "materialized_child_count": historical_child_batch_count,
            "child_candidate_count": historical_child_batch_count,
            "remaining_candidate_count": remaining_candidate_count,
            "needs_materialization": False,
            "parent_review_state": parent_review_state,
            "is_parent_review_container": True,
            **_parent_container_flags(state, remaining_parent_file_count, actual_child_count, remaining_primary_file_count, remaining_support_file_count),
        }

    if parent_container_state and (actual_child_count > 0 or candidate_group_count == 0):
        extractable_count = int(metadata.get("extractable_candidate_count") or 0)
        review_later_count = int(metadata.get("review_later_candidate_count") or 0)
        excluded_count = int(metadata.get("excluded_candidate_count") or 0)
        blocked_count = int(metadata.get("blocked_candidate_count") or 0)
        unresolved_count = int(metadata.get("unresolved_candidate_count") or 0)
        explicit_remaining = extractable_count + review_later_count + excluded_count + blocked_count + unresolved_count
        remaining_candidate_count = explicit_remaining or (1 if remaining_parent_file_count > 0 else 0)
        fallback_count = int(
            metadata.get("release_count")
            or metadata.get("album_count")
            or metadata.get("candidate_group_count")
            or 0
        )
        parent_review_state = PARENT_SPLIT_COMPLETE if parent_container_state == PARENT_CONTAINER_DRAINED else PARENT_REVIEW_IN_PROGRESS
        return {
            "candidate_group_count": max(candidate_group_count, actual_child_count + remaining_candidate_count, fallback_count),
            "approved_candidate_count": 0,
            "excluded_candidate_count": excluded_count,
            "blocked_candidate_count": blocked_count,
            "review_later_candidate_count": review_later_count,
            "unresolved_candidate_count": unresolved_count or (1 if remaining_parent_file_count > 0 and explicit_remaining == 0 else 0),
            "materialized_child_count": actual_child_count,
            "child_candidate_count": actual_child_count,
            "remaining_candidate_count": remaining_candidate_count,
            "needs_materialization": False,
            "parent_review_state": parent_review_state,
            "is_parent_review_container": True,
            **_parent_container_flags(parent_container_state, remaining_parent_file_count, actual_child_count, remaining_primary_file_count, remaining_support_file_count),
        }
    if batch.status == PARENT_SPLIT_COMPLETE:
        history_entries: list[dict[str, Any]] = []
        for key in ("materialization_history", "split_history"):
            value = metadata.get(key)
            if isinstance(value, list):
                history_entries.extend(item for item in value if isinstance(item, dict))
        history_child_count = len([
            item for item in history_entries
            if item.get("child_batch_id") or item.get("candidate_id")
        ])
        completed_child_count = actual_child_count or history_child_count
        fallback_count = int(
            metadata.get("release_count")
            or metadata.get("album_count")
            or metadata.get("candidate_group_count")
            or 0
        )
        has_remaining_parent_files = remaining_parent_file_count > 0
        split_count = (
            max(candidate_group_count, completed_child_count, fallback_count)
            if has_remaining_parent_files
            else candidate_group_count or completed_child_count or fallback_count
        )
        unresolved_remainder_count = 1 if has_remaining_parent_files else 0
        parent_review_state = PARENT_REVIEW_IN_PROGRESS if has_remaining_parent_files else PARENT_SPLIT_COMPLETE
        displayed_materialized_count = completed_child_count or (0 if has_remaining_parent_files else split_count)
        return {
            "candidate_group_count": max(split_count, displayed_materialized_count + unresolved_remainder_count),
            "approved_candidate_count": 0,
            "excluded_candidate_count": 0,
            "blocked_candidate_count": 0,
            "review_later_candidate_count": 0,
            "unresolved_candidate_count": unresolved_remainder_count,
            "materialized_child_count": displayed_materialized_count,
            "child_candidate_count": displayed_materialized_count,
            "remaining_candidate_count": unresolved_remainder_count,
            "needs_materialization": False,
            "parent_review_state": parent_review_state,
            "is_parent_review_container": True,
            **_parent_container_flags(parent_container_state, remaining_parent_file_count, actual_child_count, remaining_primary_file_count, remaining_support_file_count),
        }

    if candidate_group_count <= 1:
        return empty_parent_candidate_summary() | {
            "candidate_group_count": candidate_group_count,
            "remaining_candidate_count": candidate_group_count,
        }

    candidate_id_set = set(candidate_ids)
    latest_materialization_decision: dict[int, tuple[str, str]] = {}
    actions = (
        db.query(UniversalIngestionReviewAction)
        .filter(
            UniversalIngestionReviewAction.batch_id == batch.id,
            UniversalIngestionReviewAction.candidate_id.isnot(None),
            UniversalIngestionReviewAction.action_type.in_(MATERIALIZATION_DECISION_ACTIONS),
            UniversalIngestionReviewAction.decision_status != "cleared",
        )
        .order_by(
            UniversalIngestionReviewAction.created_at.asc(),
            UniversalIngestionReviewAction.id.asc(),
        )
        .all()
    )
    for action in actions:
        if action.candidate_id in candidate_id_set:
            latest_materialization_decision[int(action.candidate_id)] = (action.action_type, action.decision_status)

    history = metadata.get("materialization_history")
    materialized_candidate_ids = {
        int(item.get("candidate_id") or 0)
        for item in history or []
        if isinstance(item, dict) and item.get("candidate_id")
    } if isinstance(history, list) else set()
    materialized_history_count = len(materialized_candidate_ids & candidate_id_set)

    approved_candidate_count = sum(
        1
        for candidate_id, (action_type, decision_status) in latest_materialization_decision.items()
        if candidate_id not in materialized_candidate_ids
        and action_type == "approve_candidate"
        and decision_status != "applied"
    )
    excluded_candidate_count = sum(
        1 for action_type, _status in latest_materialization_decision.values() if action_type == "exclude_from_move_plan"
    )
    blocked_candidate_count = sum(
        1 for action_type, _status in latest_materialization_decision.values() if action_type == "block_candidate"
    )
    review_later_candidate_count = sum(
        1 for action_type, _status in latest_materialization_decision.values() if action_type == "mark_review_later"
    )
    resolved_candidate_ids = set(materialized_candidate_ids)
    resolved_candidate_ids.update(
        candidate_id
        for candidate_id, (action_type, _status) in latest_materialization_decision.items()
        if action_type in {"approve_candidate", "exclude_from_move_plan", "block_candidate", "mark_review_later"}
    )
    unresolved_candidate_count = max(0, candidate_group_count - len(resolved_candidate_ids & candidate_id_set))
    remaining_candidate_count = unresolved_candidate_count

    if materialized_history_count > 0:
        parent_review_state = PARENT_REVIEW_IN_PROGRESS
    elif approved_candidate_count > 0:
        parent_review_state = PARENT_CANDIDATES_APPROVED_WAITING_MATERIALIZATION
    else:
        parent_review_state = PARENT_REVIEW_IN_PROGRESS

    needs_materialization = approved_candidate_count > 0

    return {
        "candidate_group_count": candidate_group_count,
        "approved_candidate_count": approved_candidate_count,
        "excluded_candidate_count": excluded_candidate_count,
        "blocked_candidate_count": blocked_candidate_count,
        "review_later_candidate_count": review_later_candidate_count,
        "unresolved_candidate_count": unresolved_candidate_count,
        "materialized_child_count": materialized_history_count,
        "child_candidate_count": materialized_history_count,
        "remaining_candidate_count": remaining_candidate_count,
        "needs_materialization": needs_materialization,
        "parent_review_state": parent_review_state,
        "is_parent_review_container": True,
        **_parent_container_flags(parent_container_state or PARENT_CONTAINER_ACTIVE, remaining_parent_file_count, actual_child_count, remaining_primary_file_count, remaining_support_file_count),
    }
