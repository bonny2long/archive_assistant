from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

from app.models.archive import IngestBatch, IngestFile
from app.models.media_metadata import (
    FragmentReconstructionDecision,
    MediaIdentityCandidate,
    MixedMediaFlag,
    SourceFragment,
    UniversalIngestionReviewAction,
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
    "multiple_candidate_groups",
    "multiple_embedded_album_values",
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
    re.compile(r"^googledrive[-_\s]*\d+", re.IGNORECASE),
    re.compile(r"^google-drive[-_\s]*\d+", re.IGNORECASE),
    re.compile(r"^part[-_\s]*\d{2,}$", re.IGNORECASE),
    re.compile(r"^chunk[-_\s]*\d+$", re.IGNORECASE),
    re.compile(r"^source[-_\s]*fragment[-_\s]*\d*$", re.IGNORECASE),
    re.compile(r"^fragment[-_\s]*\d+$", re.IGNORECASE),
]
REQUIRED_REASONS = {
    "audiobook_in_music_batch",
    "book_or_ebook_in_music_batch",
    "movie_or_tv_in_music_batch",
    "non_music_candidate_present",
    "mixed_media_detected",
    "multiple_candidate_groups",
    "multiple_embedded_album_values",
    "source_fragment_group_detected",
    "source_folder_name_used_as_identity",
    "blocked_conflict_present",
}
RECOMMENDED_REASONS = {
    "reconstruction_review_required",
    "weak_discography_identity",
}
BLOCKING_FLAG_TYPES = {"mixed_media_source", "candidate_media_type_conflict"}
UNKNOWN_VALUES = {"", "unknown", "unknown album", "unknown artist", "none", "n/a"}


def _last_path_segment(value: str) -> str:
    return value.replace("\\", "/").split("/")[-1].strip()


def _source_chunk_segment(value: str | None) -> str | None:
    if not value:
        return None
    segment = _last_path_segment(str(value).strip())
    if not segment:
        return None
    return segment if any(pattern.search(segment) for pattern in SOURCE_CHUNK_PATTERNS) else None


def _is_source_chunk_name(value: str | None) -> bool:
    return _source_chunk_segment(value) is not None


def _contains_source_chunk_segment(value: str | None) -> bool:
    if not value:
        return False
    for segment in str(value).replace("\\", "/").split("/"):
        if _is_source_chunk_name(segment):
            return True
    return False


def _metadata_sources(metadata: dict[str, Any] | None) -> list[dict[str, Any]]:
    metadata = metadata or {}
    sources: list[dict[str, Any]] = [metadata]
    embedded_fields = metadata.get("embedded_metadata_fields")
    if isinstance(embedded_fields, dict):
        sources.append(embedded_fields)
    embedded = metadata.get("embedded_metadata")
    if isinstance(embedded, dict) and isinstance(embedded.get("fields"), dict):
        sources.append(embedded["fields"])
    return sources


def _field(metadata: dict[str, Any] | None, *names: str) -> str | None:
    for source in _metadata_sources(metadata):
        for name in names:
            value = source.get(name)
            if value is not None and str(value).strip():
                return str(value).strip()
    return None


def _normalized_identity(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = re.sub(r"\s+", " ", str(value).strip().casefold())
    return None if normalized in UNKNOWN_VALUES else normalized


def _embedded_album_value_count(db: Session, batch_id: int) -> int:
    values: set[str] = set()
    for ingest_file in db.query(IngestFile).filter(IngestFile.batch_id == batch_id).all():
        value = _normalized_identity(_field(ingest_file.metadata_json, "album", "release"))
        if value:
            values.add(value)
    return len(values)


def _batch_has_source_identity(batch: IngestBatch) -> bool:
    metadata = batch.metadata_json or {}
    suggested = batch.suggested_metadata or {}
    values = [
        metadata.get("artist"),
        metadata.get("albumartist"),
        metadata.get("album_artist"),
        metadata.get("album"),
        metadata.get("title"),
        suggested.get("artist"),
        suggested.get("albumartist"),
        suggested.get("album_artist"),
        suggested.get("album"),
        batch.suggested_destination,
    ]
    return any(_contains_source_chunk_segment(str(value)) for value in values if value)


def _add_reason(reasons: list[str], reason: str) -> None:
    if reason not in reasons:
        reasons.append(reason)


def _candidate_has_chunk_identity(candidate: MediaIdentityCandidate) -> bool:
    return (
        _is_source_chunk_name(candidate.candidate_primary_creator)
        or _is_source_chunk_name(candidate.candidate_title)
        or _is_source_chunk_name(candidate.candidate_key)
    )


def _single_music_candidate_is_approved(
    db: Session,
    batch_id: int,
    candidates: list[MediaIdentityCandidate],
) -> bool:
    if len(candidates) != 1 or candidates[0].candidate_media_type != "music":
        return False
    candidate_id = candidates[0].id
    return db.query(UniversalIngestionReviewAction.id).filter(
        UniversalIngestionReviewAction.batch_id == batch_id,
        UniversalIngestionReviewAction.candidate_id == candidate_id,
        UniversalIngestionReviewAction.action_type == "approve_candidate",
        UniversalIngestionReviewAction.decision_status != "cleared",
    ).first() is not None


def _confirmed_materialized_music_child(
    batch: IngestBatch,
    candidates: list[MediaIdentityCandidate],
) -> bool:
    """Identify a reviewed child whose source-fragment work is already complete.

    Materialization preserves the parent source-fragment evidence on the child,
    so the presence of fragments alone must not force the child back through the
    universal review route after its scoped metadata has been confirmed.
    """
    metadata = batch.metadata_json or {}
    if batch.detected_type != "music_album" or len(candidates) != 1:
        return False
    if candidates[0].candidate_media_type != "music":
        return False
    if not batch.metadata_confirmed or not metadata.get("review_confirmed"):
        return False
    return bool(
        metadata.get("source_parent_batch_id")
        or metadata.get("split_from_batch_id")
    )

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
    source_fragment_count: int = 0,
    embedded_album_value_count: int = 0,
    source_identity_risk: bool = False,
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
            "source_fragment_count": source_fragment_count,
            "reconstruction_decision_count": len(decisions),
            "blocked_conflict_count": len([row for row in decisions if row.decision == "blocked_conflict"]),
            "review_required_count": len([row for row in decisions if row.decision == "review_required"]),
            "chunk_identity_candidate_count": len(chunk_identity_candidates),
            "embedded_album_value_count": embedded_album_value_count,
            "source_identity_risk": source_identity_risk or bool(chunk_identity_candidates),
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
    source_identity_risk = _batch_has_source_identity(batch)
    embedded_album_value_count = _embedded_album_value_count(db, batch_id)
    has_analysis = db.query(SourceFragment.id).filter(SourceFragment.batch_id == batch_id).first() is not None
    if not has_analysis:
        if snapshot:
            snapshot_universal_ingestion_boundary(db, batch)
            db.commit()
            has_analysis = db.query(SourceFragment.id).filter(SourceFragment.batch_id == batch_id).first() is not None
        elif source_identity_risk or embedded_album_value_count > 1:
            reasons = ["source_folder_name_used_as_identity"] if source_identity_risk else ["multiple_embedded_album_values"]
            return _routing_result(
                batch_id,
                "universal_review_required",
                reasons,
                allowed_editors=["universal"],
                blocked_editors=[target_editor or "music_album", "music_discography"],
                has_analysis=False,
                embedded_album_value_count=embedded_album_value_count,
                source_identity_risk=source_identity_risk,
            )
        else:
            return _routing_result(
                batch_id,
                "not_analyzed",
                ["universal_analysis_missing"],
                allowed_editors=[target_editor] if target_editor else ["music_discography"],
                blocked_editors=[],
                has_analysis=False,
                embedded_album_value_count=embedded_album_value_count,
                source_identity_risk=source_identity_risk,
            )

    candidates = db.query(MediaIdentityCandidate).filter(MediaIdentityCandidate.batch_id == batch_id).all()
    flags = db.query(MixedMediaFlag).filter(MixedMediaFlag.batch_id == batch_id).all()
    decisions = db.query(FragmentReconstructionDecision).filter(FragmentReconstructionDecision.batch_id == batch_id).all()
    source_fragments = db.query(SourceFragment).filter(SourceFragment.batch_id == batch_id).all()
    source_fragment_count = len(source_fragments)

    reasons: list[str] = []
    if any(decision.decision == "blocked_conflict" for decision in decisions):
        _add_reason(reasons, "blocked_conflict_present")
        return _routing_result(
            batch_id,
            "blocked_conflict",
            reasons,
            allowed_editors=["universal"],
            blocked_editors=["music_album", "music_discography"],
            has_analysis=True,
            candidates=candidates,
            flags=flags,
            decisions=decisions,
            source_fragment_count=source_fragment_count,
            embedded_album_value_count=embedded_album_value_count,
            source_identity_risk=source_identity_risk,
        )

    if len(candidates) > 1:
        _add_reason(reasons, "multiple_candidate_groups")

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

    if source_fragment_count > 0 or any(flag.flag_type == "source_fragment_group_detected" for flag in flags):
        _add_reason(reasons, "source_fragment_group_detected")

    if embedded_album_value_count > 1:
        _add_reason(reasons, "multiple_embedded_album_values")

    if any(decision.decision == "review_required" for decision in decisions):
        _add_reason(reasons, "reconstruction_review_required")

    if source_identity_risk or any(_candidate_has_chunk_identity(candidate) for candidate in candidates):
        _add_reason(reasons, "source_folder_name_used_as_identity")
        if "non_music_candidate_present" not in reasons:
            _add_reason(reasons, "weak_discography_identity")

    if _confirmed_materialized_music_child(batch, candidates):
        # A confirmed child owns scoped files and keeps source fragments only as
        # evidence. Do not make the operator repeat parent reconstruction review.
        reasons = [
            reason
            for reason in reasons
            if reason not in {
                "source_fragment_group_detected",
                "reconstruction_review_required",
            }
        ]

    required_reasons = {reason for reason in reasons if reason in REQUIRED_REASONS}
    if _single_music_candidate_is_approved(db, batch_id, candidates):
        # One reconstructed album has already passed the operator decision.
        # Its source fragments do not require creating another child batch.
        required_reasons.discard("source_fragment_group_detected")

    if required_reasons:
        decision = "universal_review_required"
        allowed_editors = ["universal"]
        blocked_editors = ["music_album", "music_discography"]
    elif any(reason in RECOMMENDED_REASONS for reason in reasons):
        decision = "universal_review_recommended"
        allowed_editors = ["music_album", "music_discography", "universal"]
        blocked_editors = []
    else:
        decision = "music_editor_allowed"
        reasons = reasons or ["no_blocking_issues"]
        allowed_editors = ["music_album", "music_discography", "universal"]
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
        source_fragment_count=source_fragment_count,
        embedded_album_value_count=embedded_album_value_count,
        source_identity_risk=source_identity_risk,
    )
