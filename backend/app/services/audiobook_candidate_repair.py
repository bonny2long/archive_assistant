from __future__ import annotations

from typing import Any

from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.core.time import now_utc
from app.models.archive import IngestBatch, IngestFile
from app.models.media_metadata import (
    CandidateMember,
    MediaIdentityCandidate,
    MixedMediaFlag,
    UniversalIngestionReviewAction,
)
from app.services.universal_ingestion import snapshot_universal_ingestion_boundary

STALE_AUDIOBOOK_GROUPING_FLAGS = {
    "multiple_candidate_groups",
    "multiple_embedded_album_values",
    "audiobook_in_music_batch",
    "non_music_candidate_present",
    "mixed_media_detected",
    "artwork_without_owner",
    "split_release_candidate",
}


def _candidate_snapshot(db: Session, candidate: MediaIdentityCandidate) -> dict[str, Any]:
    members = db.query(CandidateMember).filter(CandidateMember.candidate_id == candidate.id).all()
    primary_count = len([member for member in members if member.role_in_candidate == "primary"])
    support_count = len(members) - primary_count
    return {
        "candidate_id": candidate.id,
        "candidate_key": candidate.candidate_key,
        "media_type": candidate.candidate_media_type,
        "title": candidate.candidate_title,
        "primary_creator": candidate.candidate_primary_creator,
        "primary_member_count": primary_count,
        "support_member_count": support_count,
        "identity_evidence": candidate.identity_evidence_json or {},
    }


def repair_audiobook_candidate_grouping(db: Session, batch_id: int) -> dict[str, Any]:
    """Rebuild one audiobook's candidate snapshot without touching file ownership."""
    batch = db.get(IngestBatch, batch_id)
    if batch is None:
        raise ValueError("Batch not found")
    if batch.detected_type != "audiobook":
        raise ValueError("Audiobook grouping repair requires an audiobook batch")

    attached_files = (
        db.query(IngestFile)
        .filter(IngestFile.batch_id == batch.id)
        .order_by(IngestFile.id)
        .all()
    )
    before_owners = {item.id: item.batch_id for item in attached_files}
    primary_file_count = len([item for item in attached_files if item.detected_role == "audiobook_audio"])
    support_file_count = len(attached_files) - primary_file_count
    if primary_file_count == 0:
        raise ValueError("Audiobook grouping repair requires attached audiobook audio files")

    old_candidates = (
        db.query(MediaIdentityCandidate)
        .filter(MediaIdentityCandidate.batch_id == batch.id)
        .order_by(MediaIdentityCandidate.id)
        .all()
    )
    old_candidate_ids = [candidate.id for candidate in old_candidates]
    old_candidate_snapshot = [_candidate_snapshot(db, candidate) for candidate in old_candidates]

    stale_actions = (
        db.query(UniversalIngestionReviewAction)
        .filter(
            UniversalIngestionReviewAction.batch_id == batch.id,
            UniversalIngestionReviewAction.decision_status != "cleared",
            or_(
                UniversalIngestionReviewAction.candidate_id.isnot(None),
                UniversalIngestionReviewAction.target_candidate_id.isnot(None),
                UniversalIngestionReviewAction.source_fragment_id.isnot(None),
            ),
        )
        .all()
    )
    archived_action_ids: list[int] = []
    for action in stale_actions:
        prior_candidate_id = action.candidate_id
        prior_target_id = action.target_candidate_id
        audit_note = (
            "Archived by audiobook grouping repair; "
            f"previous candidate_id={prior_candidate_id}, target_candidate_id={prior_target_id}."
        )
        action.note = f"{action.note} | {audit_note}" if action.note else audit_note
        action.decision_status = "cleared"
        action.candidate_id = None
        action.target_candidate_id = None
        action.source_fragment_id = None
        action.updated_at = now_utc()
        archived_action_ids.append(action.id)
    db.flush()
    # The snapshot uses bulk deletes; remove loaded candidate identities so SQLite
    # cannot reuse a primary key while the old object remains in this Session.
    for candidate in old_candidates:
        db.expunge(candidate)

    snapshot = snapshot_universal_ingestion_boundary(db, batch)
    candidates = (
        db.query(MediaIdentityCandidate)
        .filter(MediaIdentityCandidate.batch_id == batch.id)
        .order_by(MediaIdentityCandidate.id)
        .all()
    )
    if len(candidates) != 1 or candidates[0].candidate_media_type != "audiobook":
        raise ValueError(
            "Attached file evidence does not prove one coherent audiobook; grouping repair was not applied"
        )
    candidate_payload = _candidate_snapshot(db, candidates[0])
    if candidate_payload["primary_member_count"] != primary_file_count:
        raise ValueError("Audiobook candidate does not own every attached primary audio file")
    if candidate_payload["support_member_count"] > support_file_count:
        raise ValueError("Audiobook support-file ownership is inconsistent")

    remaining_flags = {
        flag_type
        for (flag_type,) in (
            db.query(MixedMediaFlag.flag_type)
            .filter(MixedMediaFlag.batch_id == batch.id)
            .all()
        )
    }
    stale_remaining = sorted(remaining_flags & STALE_AUDIOBOOK_GROUPING_FLAGS)
    if stale_remaining:
        raise ValueError(f"Stale audiobook grouping flags remain: {', '.join(stale_remaining)}")

    after_owners = {
        item.id: item.batch_id
        for item in db.query(IngestFile).filter(IngestFile.id.in_(before_owners)).all()
    }
    if after_owners != before_owners:
        raise ValueError("Audiobook grouping repair changed file ownership")

    identity = candidate_payload.get("identity_evidence") or {}
    identity_values = identity.get("identity") if isinstance(identity, dict) else {}
    disc_count = int(identity_values.get("disc_count") or 0) if isinstance(identity_values, dict) else 0
    repaired_at = now_utc()
    metadata = dict(batch.metadata_json or {})
    audit = list(metadata.get("audiobook_candidate_repair_audit") or [])
    audit_entry = {
        "repaired_at": repaired_at.isoformat(),
        "operation": "single_book_multidisc_candidate_rebuild",
        "previous_candidate_ids": old_candidate_ids,
        "previous_candidates": old_candidate_snapshot,
        "new_candidate_id": candidates[0].id,
        "archived_action_ids": archived_action_ids,
        "attached_file_count": len(attached_files),
        "primary_file_count": primary_file_count,
        "support_file_count": support_file_count,
        "disc_count": disc_count,
        "file_ownership_preserved": True,
    }
    audit.append(audit_entry)
    metadata.update({
        "candidate_group_count": 1,
        "active_parent_file_count": len(attached_files),
        "remaining_primary_file_count": primary_file_count,
        "remaining_support_file_count": support_file_count,
        "parent_has_remaining_files": True,
        "parent_is_drained": False,
        "audiobook_candidate_repair_audit": audit,
    })
    batch.metadata_json = metadata
    batch.updated_at = repaired_at
    db.commit()

    return {
        "batch_id": batch.id,
        "detected_type": batch.detected_type,
        "previous_candidate_count": len(old_candidates),
        "candidate_count": 1,
        "attached_file_count": len(attached_files),
        "primary_file_count": primary_file_count,
        "support_file_count": support_file_count,
        "disc_count": disc_count,
        "archived_action_count": len(archived_action_ids),
        "file_ownership_preserved": True,
        "candidate": candidate_payload,
        "snapshot": snapshot,
        "audit": audit_entry,
        "message": "Audiobook grouping rebuilt as one multi-disc book.",
    }