from __future__ import annotations

import re
from typing import Any

from sqlalchemy.orm import Session

from app.models.archive import IngestBatch
from app.models.media_metadata import (
    FragmentReconstructionDecision,
    MediaIdentityCandidate,
    MixedMediaFlag,
    SourceFragment,
)
from app.services.universal_ingestion import snapshot_universal_ingestion_boundary

ROUTING_DECISIONS = {
    "music_editor_allowed",
    "universal_review_required",
    "universal_review_recommended",
    "blocked_conflict",
    "not_analyzed",
}
ROUTING_REASON_CODES = {
    "mixed_media_detected",
    "non_music_candidate_present",
    "source_fragment_group_detected",
    "reconstruction_review_required",
    "candidate_media_class_uncertain",
    "candidate_media_class_not_music",
    "book_or_ebook_in_music_batch",
    "audiobook_in_music_batch",
    "movie_or_tv_in_music_batch",
    "source_folder_name_used_as_identity",
    "weak_discography_identity",
    "blocked_conflict_present",
    "universal_analysis_missing",
    "no_blocking_issues",
}

SOURCE_CHUNK_PATTERNS = [
    re.compile(r"^drive-download-", re.IGNORECASE),
    re.compile(r"^googledrive-\d+", re.IGNORECASE),
    re.compile(r"^part-\d{2,}", re.IGNORECASE),
    re.compile(r"^chunk-\d+", re.IGNORECASE),
    re.compile(r"-\d{3}$"),
]
REQUIRED_REASONS = {
    "audiobook_in_music_batch",
    "book_or_ebook_in_music_batch",
    "movie_or_tv_in_music_batch",
    "non_music_candidate_present",
    "mixed_media_detected",
    "blocked_conflict_present",
}
RECOMMENDED_REASONS = {
    "source_fragment_group_detected",
    "reconstruction_review_required",
    "source_folder_name_used_as_identity",
    "weak_discography_identity",
}
BLOCKING_FLAG_TYPES = {"mixed_media_source", "candidate_media_type_conflict"}


def _is_source_chunk_name(value: str | None) -> bool:
    if not value:
        return False
    return any(pattern.search(value) for pattern in SOURCE_CHUNK_PATTERNS)


def _add_reason(reasons: list[str], reason: str) -> None:
    if reason not in reasons:
        reasons.append(reason)


def _routing_result(
    batch_id: int,
    decision: str,
    reasons: list[str],
    *,
    allowed_editors: list[str],
    blocked_editors: list[str],
    has_analysis: bool,
    candidates: list[MediaIdentityCandidate] | None = None,
    flags: list[MixedMediaFlag] | None = None,
    decisions: list[FragmentReconstructionDecision] | None = None,
) -> dict[str, Any]:
    candidates = candidates or []
    flags = flags or []
    decisions = decisions or []
    media_types = {candidate.candidate_media_type for candidate in candidates if candidate.candidate_media_type}
    media_class_counts: dict[str, int] = {}
    chunk_identity_candidates = [
        candidate for candidate in candidates
        if _candidate_has_chunk_identity(candidate)
    ]
    for candidate in candidates:
        media_type = candidate.candidate_media_type or "unknown"
        media_class_counts[media_type] = media_class_counts.get(media_type, 0) + 1
    return {
        "batch_id": batch_id,
        "decision": decision,
        "allowed_editors": allowed_editors,
        "blocked_editors": blocked_editors,
        "reasons": reasons,
        "universal_ingestion_available": has_analysis,
        "requires_snapshot": not has_analysis,
        "summary": {
            "candidate_count": len(candidates),
            "media_types": sorted(media_types),
            "media_class_counts": media_class_counts,
            "mixed_media_flag_count": len([flag for flag in flags if flag.flag_type in BLOCKING_FLAG_TYPES]),
            "source_fragment_group_count": len([flag for flag in flags if flag.flag_type == "source_fragment_group_detected"]),
            "reconstruction_decision_count": len(decisions),
            "blocked_conflict_count": len([row for row in decisions if row.decision == "blocked_conflict"]),
            "review_required_count": len([row for row in decisions if row.decision == "review_required"]),
            "chunk_identity_candidate_count": len(chunk_identity_candidates),
        },
        "candidate_route_summaries": [
            {
                "candidate_id": candidate.id,
                "candidate_title": candidate.candidate_title,
                "candidate_media_type": candidate.candidate_media_type,
                "candidate_key": candidate.candidate_key,
                "chunk_identity_risk": _candidate_has_chunk_identity(candidate),
            }
            for candidate in candidates
        ],
    }


def _candidate_has_chunk_identity(candidate: MediaIdentityCandidate) -> bool:
    return (
        _is_source_chunk_name(candidate.candidate_primary_creator)
        or _is_source_chunk_name(candidate.candidate_title)
        or _is_source_chunk_name(candidate.candidate_key)
    )


def get_batch_routing_decision(
    db: Session,
    batch_id: int,
    *,
    target_editor: str | None = None,
    snapshot: bool = False,
) -> dict[str, Any]:
    batch = db.get(IngestBatch, batch_id)
    if batch is None:
        raise ValueError("Batch not found")
    has_analysis = db.query(SourceFragment.id).filter(SourceFragment.batch_id == batch_id).first() is not None
    if not has_analysis:
        if snapshot:
            snapshot_universal_ingestion_boundary(db, batch)
            db.commit()
            has_analysis = db.query(SourceFragment.id).filter(SourceFragment.batch_id == batch_id).first() is not None
        else:
            return _routing_result(
                batch_id,
                "not_analyzed",
                ["universal_analysis_missing"],
                allowed_editors=[target_editor] if target_editor else ["music_discography"],
                blocked_editors=[],
                has_analysis=False,
            )

    candidates = db.query(MediaIdentityCandidate).filter(MediaIdentityCandidate.batch_id == batch_id).all()
    flags = db.query(MixedMediaFlag).filter(MixedMediaFlag.batch_id == batch_id).all()
    decisions = db.query(FragmentReconstructionDecision).filter(FragmentReconstructionDecision.batch_id == batch_id).all()
    db.query(SourceFragment).filter(SourceFragment.batch_id == batch_id).all()

    reasons: list[str] = []
    if any(decision.decision == "blocked_conflict" for decision in decisions):
        _add_reason(reasons, "blocked_conflict_present")
        return _routing_result(
            batch_id,
            "blocked_conflict",
            reasons,
            allowed_editors=["universal"],
            blocked_editors=["music_discography"],
            has_analysis=True,
            candidates=candidates,
            flags=flags,
            decisions=decisions,
        )

    media_types = {candidate.candidate_media_type for candidate in candidates}
    non_music = media_types - {"music"}
    if "audiobook" in non_music:
        _add_reason(reasons, "audiobook_in_music_batch")
    if "ebook" in non_music or "comic" in non_music:
        _add_reason(reasons, "book_or_ebook_in_music_batch")
    if "movie" in non_music or "tv" in non_music:
        _add_reason(reasons, "movie_or_tv_in_music_batch")
    if non_music:
        _add_reason(reasons, "non_music_candidate_present")
        _add_reason(reasons, "mixed_media_detected")

    has_blocking_flags = any(
        flag.flag_type in BLOCKING_FLAG_TYPES and flag.severity in {"review", "error"}
        for flag in flags
    )
    if has_blocking_flags:
        _add_reason(reasons, "mixed_media_detected")

    if any(flag.flag_type == "source_fragment_group_detected" for flag in flags):
        _add_reason(reasons, "source_fragment_group_detected")

    if any(decision.decision == "review_required" for decision in decisions):
        _add_reason(reasons, "reconstruction_review_required")

    if any(_candidate_has_chunk_identity(candidate) for candidate in candidates):
        _add_reason(reasons, "source_folder_name_used_as_identity")
        if "non_music_candidate_present" not in reasons:
            _add_reason(reasons, "weak_discography_identity")

    if any(reason in REQUIRED_REASONS for reason in reasons):
        decision = "universal_review_required"
        allowed_editors = ["universal"]
        blocked_editors = ["music_discography"]
    elif any(reason in RECOMMENDED_REASONS for reason in reasons):
        decision = "universal_review_recommended"
        allowed_editors = ["music_discography", "universal"]
        blocked_editors = []
    else:
        decision = "music_editor_allowed"
        reasons = reasons or ["no_blocking_issues"]
        allowed_editors = ["music_discography", "universal"]
        blocked_editors = []

    return _routing_result(
        batch_id,
        decision,
        reasons,
        allowed_editors=allowed_editors,
        blocked_editors=blocked_editors,
        has_analysis=True,
        candidates=candidates,
        flags=flags,
        decisions=decisions,
    )