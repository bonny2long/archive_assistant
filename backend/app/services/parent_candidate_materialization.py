from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.models.archive import IngestBatch, IngestFile
from app.models.media_metadata import MediaIdentityCandidate, UniversalIngestionReviewAction


PARENT_REVIEW_IN_PROGRESS = "review_in_progress"
PARENT_CANDIDATES_APPROVED_WAITING_MATERIALIZATION = "candidates_approved_waiting_materialization"
PARENT_PARTIALLY_MATERIALIZED = "parent_partially_materialized"
PARENT_SPLIT_COMPLETE = "split_complete"

MATERIALIZATION_DECISION_ACTIONS = {
    "approve_candidate",
    "exclude_from_move_plan",
    "mark_review_later",
    "block_candidate",
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
        "is_parent_review_container": False,
    }


def build_parent_candidate_summary(db: Session | None, batch: IngestBatch) -> dict[str, Any]:
    """Derive review-container state from candidates and active audit actions."""
    if db is None:
        return empty_parent_candidate_summary()

    remaining_parent_file_count = db.query(IngestFile).filter(IngestFile.batch_id == batch.id).count()
    candidate_ids = [
        candidate_id
        for (candidate_id,) in db.query(MediaIdentityCandidate.id)
        .filter(MediaIdentityCandidate.batch_id == batch.id)
        .all()
    ]
    candidate_group_count = len(candidate_ids)
    metadata = batch.metadata_json or {}
    if batch.status == PARENT_SPLIT_COMPLETE:
        history = metadata.get("materialization_history")
        materialized_count = len([
            item for item in history or []
            if isinstance(item, dict) and (item.get("child_batch_id") or item.get("candidate_id"))
        ]) if isinstance(history, list) else 0
        fallback_count = int(
            metadata.get("release_count")
            or metadata.get("album_count")
            or metadata.get("candidate_group_count")
            or 0
        )
        split_count = max(candidate_group_count, materialized_count, fallback_count)
        has_remaining_parent_files = remaining_parent_file_count > 0
        unresolved_remainder_count = 1 if has_remaining_parent_files else 0
        parent_review_state = PARENT_PARTIALLY_MATERIALIZED if has_remaining_parent_files else PARENT_SPLIT_COMPLETE
        displayed_materialized_count = materialized_count or (0 if has_remaining_parent_files else split_count)
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
    materialized_child_count = len(materialized_candidate_ids & candidate_id_set)

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

    if materialized_child_count > 0:
        parent_review_state = PARENT_PARTIALLY_MATERIALIZED
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
        "materialized_child_count": materialized_child_count,
        "child_candidate_count": materialized_child_count,
        "remaining_candidate_count": remaining_candidate_count,
        "needs_materialization": needs_materialization,
        "parent_review_state": parent_review_state,
        "is_parent_review_container": True,
    }
