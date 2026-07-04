from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.models.archive import IngestBatch
from app.models.media_metadata import MediaIdentityCandidate, UniversalIngestionReviewAction


PARENT_REVIEW_IN_PROGRESS = "review_in_progress"
PARENT_CANDIDATES_APPROVED_WAITING_MATERIALIZATION = "candidates_approved_waiting_materialization"
PARENT_SPLIT_COMPLETE = "split_complete"

MATERIALIZATION_DECISION_ACTIONS = {
    "approve_candidate",
    "exclude_from_move_plan",
}


def empty_parent_candidate_summary() -> dict[str, Any]:
    return {
        "candidate_group_count": 0,
        "approved_candidate_count": 0,
        "excluded_candidate_count": 0,
        "remaining_candidate_count": 0,
        "needs_materialization": False,
        "parent_review_state": None,
        "is_parent_review_container": False,
    }


def build_parent_candidate_summary(db: Session | None, batch: IngestBatch) -> dict[str, Any]:
    """Derive review-container state from candidates and active audit actions."""
    if db is None:
        return empty_parent_candidate_summary()

    candidate_ids = [
        candidate_id
        for (candidate_id,) in db.query(MediaIdentityCandidate.id)
        .filter(MediaIdentityCandidate.batch_id == batch.id)
        .all()
    ]
    candidate_group_count = len(candidate_ids)
    if candidate_group_count <= 1:
        return empty_parent_candidate_summary() | {
            "candidate_group_count": candidate_group_count,
            "remaining_candidate_count": candidate_group_count,
        }

    candidate_id_set = set(candidate_ids)
    latest_materialization_decision: dict[int, str] = {}
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
            latest_materialization_decision[action.candidate_id] = action.action_type

    approved_candidate_count = sum(
        1 for action_type in latest_materialization_decision.values() if action_type == "approve_candidate"
    )
    excluded_candidate_count = sum(
        1 for action_type in latest_materialization_decision.values() if action_type == "exclude_from_move_plan"
    )
    remaining_candidate_count = max(
        0,
        candidate_group_count - approved_candidate_count - excluded_candidate_count,
    )

    if batch.status == PARENT_SPLIT_COMPLETE:
        parent_review_state = PARENT_SPLIT_COMPLETE
    elif approved_candidate_count > 0 and remaining_candidate_count == 0:
        parent_review_state = PARENT_CANDIDATES_APPROVED_WAITING_MATERIALIZATION
    else:
        parent_review_state = PARENT_REVIEW_IN_PROGRESS

    needs_materialization = parent_review_state == PARENT_CANDIDATES_APPROVED_WAITING_MATERIALIZATION

    return {
        "candidate_group_count": candidate_group_count,
        "approved_candidate_count": approved_candidate_count,
        "excluded_candidate_count": excluded_candidate_count,
        "remaining_candidate_count": remaining_candidate_count,
        "needs_materialization": needs_materialization,
        "parent_review_state": parent_review_state,
        "is_parent_review_container": True,
    }
