from __future__ import annotations

from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

from app.models.archive import IngestBatch, IngestFile
from app.models.media_metadata import (
    CandidateMember,
    FragmentReconstructionDecision,
    MediaIdentityCandidate,
    MixedMediaFlag,
    SourceFragment,
    UniversalIngestionReviewAction,
)
from app.core.time import now_utc
from app.services.duplicate_fragment_review import refresh_resolved_canonical_review_state
from app.services.music_metadata import resolved_music_track_evidence
from app.services.universal_ingestion import snapshot_universal_ingestion_boundary

PHASE_NAME = "AA-M4D.2 — Universal Ingestion Review API + UI"
DECISION_ORDER = {
    "safe_group": 0,
    "merge_recommended": 1,
    "split_recommended": 2,
    "review_required": 3,
    "blocked_conflict": 4,
}
KNOWN_ACTION_TYPES = {
    "approve_candidate",
    "mark_review_later",
    "override_media_class",
    "override_identity",
    "merge_candidates",
    "split_candidate",
    "exclude_from_move_plan",
    "block_candidate",
    "clear_action",
}
KNOWN_MEDIA_CLASSES = {
    "music_audio",
    "audiobook_audio",
    "ebook",
    "comic",
    "movie",
    "tv_episode",
    "video_extra",
    "subtitle",
    "artwork",
    "sidecar_metadata",
    "playlist",
    "archive_file",
    "unknown",
}
ZERO_DECISION_COUNTS = {
    "safe_group": 0,
    "split_recommended": 0,
    "merge_recommended": 0,
    "review_required": 0,
    "blocked_conflict": 0,
}


def confidence_label(value: float | None) -> str:
    if value is None:
        return "Unknown"
    if value >= 0.8:
        return "High"
    if value >= 0.6:
        return "Medium"
    return "Low"


def worst_universal_decision(decisions: list[str]) -> str:
    if not decisions:
        return "safe_group"
    return max(decisions, key=lambda decision: DECISION_ORDER.get(decision, 0))


def _empty_payload(batch_id: int, analysis_status: str = "not_analyzed") -> dict[str, Any]:
    return {
        "batch_id": batch_id,
        "phase": PHASE_NAME,
        "analysis_status": analysis_status,
        "summary": {
            "source_fragment_count": 0,
            "candidate_count": 0,
            "member_count": 0,
            "mixed_media_flag_count": 0,
            "decision_counts": dict(ZERO_DECISION_COUNTS),
            "media_class_counts": {},
            "worst_decision": "safe_group",
        },
        "source_fragments": [],
        "candidates": [],
        "reconstruction_decisions": [],
        "mixed_media_flags": [],
    }


def _metadata_fields(metadata: dict | None) -> dict[str, Any]:
    metadata = metadata or {}
    fields: dict[str, Any] = {}
    if isinstance(metadata, dict):
        fields.update(metadata)
        embedded = metadata.get("embedded_metadata_fields")
        if isinstance(embedded, dict):
            fields.update(embedded)
        payload = metadata.get("embedded_metadata")
        if isinstance(payload, dict) and isinstance(payload.get("fields"), dict):
            fields.update(payload["fields"])
    return fields


def _first(fields: dict[str, Any], *names: str) -> str | None:
    for name in names:
        value = fields.get(name)
        if value not in (None, ""):
            return str(value)
    return None


def _member_role(member: CandidateMember) -> str:
    if member.role_in_candidate == "support":
        return {
            "subtitle": "subtitle",
            "artwork": "cover_art",
            "sidecar_metadata": "sidecar",
            "playlist": "sidecar",
        }.get(member.media_class, "support")
    return {
        "music_audio": "track",
        "audiobook_audio": "chapter",
        "ebook": "book_file",
        "comic": "comic_archive",
        "movie": "primary_media",
        "tv_episode": "primary_media",
        "video_extra": "video_extra",
    }.get(member.media_class, "primary_media")


def _recommended_action_for_flag(flag_type: str) -> str:
    if flag_type == "mixed_media_source":
        return "Review candidate groups before final organization."
    if flag_type in {"movie_tv_ambiguous", "ambiguous_pdf_role"}:
        return "Review the media role before final move planning."
    if flag_type in {"sidecar_without_owner", "artwork_without_owner"}:
        return "Review ownership before attaching support files."
    if flag_type in {"track_number_conflict", "disc_number_missing", "duplicate_chapter_identity"}:
        return "Review numbering before final move planning."
    if flag_type == "source_fragment_group_detected":
        return "Treat source folders as incoming fragments, not final placement."
    return "Review this warning before final organization."




def action_to_dict(row: UniversalIngestionReviewAction) -> dict[str, Any]:
    return {
        "id": row.id,
        "batch_id": row.batch_id,
        "candidate_id": row.candidate_id,
        "source_fragment_id": row.source_fragment_id,
        "media_file_id": row.media_file_id,
        "action_type": row.action_type,
        "target_media_class": row.target_media_class,
        "target_candidate_id": row.target_candidate_id,
        "override_title": row.override_title,
        "override_primary_creator": row.override_primary_creator,
        "override_year": row.override_year,
        "override_series": row.override_series,
        "override_series_index": row.override_series_index,
        "override_release_type": row.override_release_type,
        "override_genre_family": row.override_genre_family,
        "override_destination_root": row.override_destination_root,
        "decision_status": row.decision_status,
        "reason": row.reason,
        "note": row.note,
        "created_at": row.created_at,
        "updated_at": row.updated_at,
        "applied_at": row.applied_at,
        "created_by": row.created_by,
    }


def list_review_actions_for_batch(db: Session, batch_id: int, *, active_only: bool = False) -> list[UniversalIngestionReviewAction]:
    query = db.query(UniversalIngestionReviewAction).filter(UniversalIngestionReviewAction.batch_id == batch_id)
    if active_only:
        query = query.filter(UniversalIngestionReviewAction.decision_status == "active")
    return query.order_by(UniversalIngestionReviewAction.updated_at.desc()).all()


def compute_review_action_summary(db: Session, batch_id: int) -> dict[str, Any]:
    actions = list_review_actions_for_batch(db, batch_id, active_only=True)
    counts = Counter(action.action_type for action in actions)
    return {
        "active_action_count": len(actions),
        "action_counts": dict(counts),
        "approved_candidate_count": counts.get("approve_candidate", 0),
        "review_later_count": counts.get("mark_review_later", 0),
        "override_count": counts.get("override_media_class", 0) + counts.get("override_identity", 0),
        "excluded_candidate_count": counts.get("exclude_from_move_plan", 0),
        "blocked_candidate_count": counts.get("block_candidate", 0),
    }


def _require_batch(db: Session, batch_id: int) -> IngestBatch:
    batch = db.get(IngestBatch, batch_id)
    if batch is None:
        raise ValueError("Batch not found")
    return batch


def _validate_action_payload(db: Session, batch_id: int, payload: dict[str, Any]) -> None:
    _require_batch(db, batch_id)
    action_type = payload.get("action_type")
    if action_type not in KNOWN_ACTION_TYPES or action_type == "clear_action":
        raise ValueError("Unknown or unsupported action_type")
    candidate_id = payload.get("candidate_id")
    source_fragment_id = payload.get("source_fragment_id")
    media_file_id = payload.get("media_file_id")
    target_candidate_id = payload.get("target_candidate_id")
    target_media_class = payload.get("target_media_class")
    if target_media_class and target_media_class not in KNOWN_MEDIA_CLASSES:
        raise ValueError("Unknown target_media_class")
    if candidate_id is not None:
        candidate = db.get(MediaIdentityCandidate, int(candidate_id))
        if candidate is None or candidate.batch_id != batch_id:
            raise ValueError("candidate_id does not belong to this batch")
    if source_fragment_id is not None:
        fragment = db.get(SourceFragment, int(source_fragment_id))
        if fragment is None or fragment.batch_id != batch_id:
            raise ValueError("source_fragment_id does not belong to this batch")
    if media_file_id is not None:
        member = (
            db.query(CandidateMember)
            .join(MediaIdentityCandidate, CandidateMember.candidate_id == MediaIdentityCandidate.id)
            .filter(CandidateMember.media_file_id == int(media_file_id), MediaIdentityCandidate.batch_id == batch_id)
            .first()
        )
        if member is None:
            raise ValueError("media_file_id does not belong to this batch")
    if target_candidate_id is not None:
        target = db.get(MediaIdentityCandidate, int(target_candidate_id))
        if target is None or target.batch_id != batch_id:
            raise ValueError("target_candidate_id does not belong to this batch")
    if action_type in {"approve_candidate", "mark_review_later", "override_identity", "split_candidate", "exclude_from_move_plan", "block_candidate"} and candidate_id is None:
        raise ValueError(f"{action_type} requires candidate_id")
    if action_type == "override_media_class" and not target_media_class:
        raise ValueError("override_media_class requires target_media_class")
    if action_type == "merge_candidates" and (candidate_id is None or target_candidate_id is None or int(candidate_id) == int(target_candidate_id)):
        raise ValueError("merge_candidates requires a different target_candidate_id")


def _same_action_query(db: Session, batch_id: int, payload: dict[str, Any]):
    return db.query(UniversalIngestionReviewAction).filter(
        UniversalIngestionReviewAction.batch_id == batch_id,
        UniversalIngestionReviewAction.action_type == payload.get("action_type"),
        UniversalIngestionReviewAction.candidate_id == payload.get("candidate_id"),
        UniversalIngestionReviewAction.source_fragment_id == payload.get("source_fragment_id"),
        UniversalIngestionReviewAction.media_file_id == payload.get("media_file_id"),
    )


def create_or_update_review_action(db: Session, batch_id: int, payload: dict[str, Any]) -> dict[str, Any]:
    _validate_action_payload(db, batch_id, payload)
    existing = _same_action_query(db, batch_id, payload).filter(UniversalIngestionReviewAction.decision_status == "active").first()
    row = existing or UniversalIngestionReviewAction(batch_id=batch_id, action_type=payload["action_type"])
    for field in (
        "candidate_id",
        "source_fragment_id",
        "media_file_id",
        "target_media_class",
        "target_candidate_id",
        "override_title",
        "override_primary_creator",
        "override_year",
        "override_series",
        "override_series_index",
        "override_release_type",
        "override_genre_family",
        "override_destination_root",
        "reason",
        "note",
    ):
        setattr(row, field, payload.get(field))
    row.decision_status = "active"
    row.updated_at = now_utc()
    row.created_by = payload.get("created_by") or row.created_by or "local_user"
    if existing is None:
        db.add(row)
    db.commit()
    db.refresh(row)
    return action_to_dict(row)


def clear_review_action(db: Session, batch_id: int, action_id: int) -> dict[str, Any]:
    row = db.get(UniversalIngestionReviewAction, action_id)
    if row is None or row.batch_id != batch_id:
        raise ValueError("Review action not found for this batch")
    row.decision_status = "cleared"
    row.updated_at = now_utc()
    db.commit()
    db.refresh(row)
    return action_to_dict(row)

def get_batch_universal_ingestion_review(
    db: Session,
    batch_id: int,
    *,
    snapshot: bool = False,
) -> dict[str, Any]:
    batch = db.get(IngestBatch, batch_id)
    if batch is None:
        raise ValueError("Batch not found")
    if snapshot:
        refreshed_legacy_canonical = refresh_resolved_canonical_review_state(db, batch)
        if not refreshed_legacy_canonical:
            snapshot_universal_ingestion_boundary(db, batch)
        db.commit()
    if not db.query(SourceFragment.id).filter(SourceFragment.batch_id == batch_id).first():
        return _empty_payload(batch_id)

    fragments = db.query(SourceFragment).filter(SourceFragment.batch_id == batch_id).order_by(SourceFragment.relative_fragment_path).all()
    candidates = db.query(MediaIdentityCandidate).filter(MediaIdentityCandidate.batch_id == batch_id).order_by(MediaIdentityCandidate.candidate_media_type, MediaIdentityCandidate.candidate_title).all()
    candidate_ids = [candidate.id for candidate in candidates]
    members = db.query(CandidateMember).filter(CandidateMember.candidate_id.in_(candidate_ids)).order_by(CandidateMember.sort_key).all() if candidate_ids else []
    ingest_file_ids = [member.batch_file_id for member in members if member.batch_file_id]
    ingest_files = {
        ingest_file.id: ingest_file
        for ingest_file in db.query(IngestFile).filter(IngestFile.id.in_(ingest_file_ids)).all()
    } if ingest_file_ids else {}
    decisions = db.query(FragmentReconstructionDecision).filter(FragmentReconstructionDecision.batch_id == batch_id).all()
    flags = db.query(MixedMediaFlag).filter(MixedMediaFlag.batch_id == batch_id).all()
    active_actions = list_review_actions_for_batch(db, batch_id, active_only=True)

    decisions_by_candidate: dict[int, FragmentReconstructionDecision] = {}
    for decision in decisions:
        if decision.candidate_id is not None:
            decisions_by_candidate[decision.candidate_id] = decision
    actions_by_candidate: dict[int, list[dict[str, Any]]] = defaultdict(list)
    actions_by_fragment: dict[int, list[dict[str, Any]]] = defaultdict(list)
    actions_by_media_file: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for action in active_actions:
        action_payload = action_to_dict(action)
        if action.candidate_id is not None:
            actions_by_candidate[action.candidate_id].append(action_payload)
        if action.source_fragment_id is not None:
            actions_by_fragment[action.source_fragment_id].append(action_payload)
        if action.media_file_id is not None:
            actions_by_media_file[action.media_file_id].append(action_payload)
    members_by_candidate: dict[int, list[CandidateMember]] = defaultdict(list)
    for member in members:
        members_by_candidate[member.candidate_id].append(member)

    media_class_counts = Counter(member.media_class for member in members)
    decision_counts = dict(ZERO_DECISION_COUNTS)
    for decision in decisions:
        decision_counts[decision.decision] = decision_counts.get(decision.decision, 0) + 1

    source_fragments = [
        {
            "id": row.id,
            "batch_id": row.batch_id,
            "fragment_group_key": row.fragment_group_key,
            "source_root": row.source_root,
            "source_path": row.relative_fragment_path,
            "fragment_label": row.fragment_label,
            "file_count": row.file_count,
            "media_class_counts": row.media_class_counts_json or {},
            "created_at": row.created_at,
            "updated_at": row.updated_at,
            "active_actions": actions_by_fragment.get(row.id, []),
        }
        for row in fragments
    ]

    candidate_payloads = []
    for candidate in candidates:
        candidate_members = members_by_candidate.get(candidate.id, [])
        decision = decisions_by_candidate.get(candidate.id)
        source_fragment_count = len({Path(member.relative_path).parts[0] if Path(member.relative_path).parts else "." for member in candidate_members})
        member_payloads = []
        for member in candidate_members:
            ingest_file = ingest_files.get(member.batch_file_id or -1)
            fields = _metadata_fields(ingest_file.metadata_json if ingest_file else None)
            evidence = member.evidence_json or {}
            track_evidence = (
                resolved_music_track_evidence(ingest_file.metadata_json, ingest_file.file_name)
                if ingest_file and candidate.candidate_media_type == "music"
                else {}
            )
            member_payloads.append({
                "id": member.id,
                "candidate_id": member.candidate_id,
                "media_file_id": member.media_file_id,
                "ingest_file_id": member.batch_file_id,
                "relative_path": member.relative_path,
                "filename": Path(member.relative_path).name,
                "extension": ingest_file.extension if ingest_file else Path(member.relative_path).suffix,
                "media_class": member.media_class,
                "size_bytes": ingest_file.size_bytes if ingest_file else None,
                "duration_seconds": _first(fields, "duration_seconds"),
                "track_number": (
                    str(track_evidence["resolved_track"])
                    if track_evidence.get("resolved_track") is not None
                    else _first(fields, "track_number", "tracknumber")
                ),
                "disc_number": (
                    str(track_evidence["disc"])
                    if track_evidence.get("disc") is not None
                    else _first(fields, "disc_number", "discnumber")
                ),
                "season_number": evidence.get("season"),
                "episode_number": evidence.get("episode"),
                "title": _first(fields, "title"),
                "artist_or_author": _first(fields, "artist", "album_artist", "albumartist", "author", "composer"),
                "album_or_series": _first(fields, "album", "series"),
                "member_role": _member_role(member),
                "confidence": evidence.get("confidence"),
                "reason": evidence.get("fragment_group_key") or evidence.get("extension"),
                "active_actions": actions_by_media_file.get(member.media_file_id or -1, []),
            })
        candidate_payloads.append({
            "id": candidate.id,
            "batch_id": candidate.batch_id,
            "candidate_key": candidate.candidate_key,
            "candidate_media_type": candidate.candidate_media_type,
            "candidate_title": candidate.candidate_title,
            "candidate_primary_creator": candidate.candidate_primary_creator,
            "candidate_secondary_creator": candidate.candidate_secondary_creator,
            "candidate_year": candidate.candidate_year,
            "candidate_series": candidate.candidate_series,
            "candidate_series_index": candidate.candidate_series_index,
            "candidate_confidence": candidate.candidate_confidence,
            "candidate_confidence_label": confidence_label(candidate.candidate_confidence),
            "member_count": len(candidate_members),
            "source_fragment_count": source_fragment_count,
            "recommended_action": decision.recommended_action if decision else None,
            "summary_reason": (decision.reasons_json or [None])[0] if decision else None,
            "members": member_payloads,
            "active_actions": actions_by_candidate.get(candidate.id, []),
        })

    decision_payloads = [
        {
            "id": row.id,
            "batch_id": row.batch_id,
            "candidate_id": row.candidate_id,
            "source_fragment_id": None,
            "decision": row.decision,
            "severity": row.severity,
            "reason": "; ".join(row.reasons_json or []),
            "recommended_action": row.recommended_action,
            "conflict_flags": row.conflict_flags_json or [],
            "created_at": row.created_at,
        }
        for row in decisions
    ]
    flag_payloads = [
        {
            "id": row.id,
            "batch_id": row.batch_id,
            "source_fragment_id": row.source_fragment_id,
            "candidate_id": row.candidate_id,
            "flag_type": row.flag_type,
            "severity": row.severity,
            "message": row.message,
            "media_classes_involved": [item for item in (row.examples_json or []) if item in media_class_counts],
            "example_paths": row.examples_json or [],
            "recommended_action": _recommended_action_for_flag(row.flag_type),
            "created_at": row.created_at,
        }
        for row in flags
    ]

    return {
        "batch_id": batch_id,
        "phase": PHASE_NAME,
        "analysis_status": "analyzed",
        "summary": {
            "source_fragment_count": len(fragments),
            "candidate_count": len(candidates),
            "member_count": len(members),
            "mixed_media_flag_count": len(flags),
            "decision_counts": decision_counts,
            "media_class_counts": dict(media_class_counts),
            "worst_decision": worst_universal_decision([decision.decision for decision in decisions]),
            "action_summary": compute_review_action_summary(db, batch_id),
            "source_origin_count": int((batch.metadata_json or {}).get("source_origin_count") or 0),
            "resolved_source_origin_count": int((batch.metadata_json or {}).get("resolved_source_origin_count") or 0),
            "source_origins_resolved": bool((batch.metadata_json or {}).get("source_origins_resolved")),
        },
        "source_fragments": source_fragments,
        "candidates": candidate_payloads,
        "reconstruction_decisions": decision_payloads,
        "mixed_media_flags": flag_payloads,
        "review_actions": [action_to_dict(action) for action in active_actions],
    }