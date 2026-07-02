from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sqlalchemy.orm import Session

from app.core.time import now_utc
from app.models.media_metadata import (
    MediaFile,
    MetadataQualityDecision,
    MetadataReviewFlag,
    NormalizedMusicProfile,
)

DECISION_ORDER = {
    "approved_ready": 0,
    "review_recommended": 1,
    "review_required": 2,
    "blocked": 3,
}

BLOCKING_FLAGS = {
    "identity_collision",
    "severe_malformed_metadata",
    "unreadable_file",
    "impossible_track_ordering",
}

ERROR_FLAGS = {
    "mojibake_detected",
    "unknown_genre",
    "unmapped_genre",
    "missing_title",
    "missing_artist",
    "missing_composer",
    "missing_work_or_movement",
    "classical_metadata_incomplete",
}

WARNING_FLAGS = {
    "possible_broad_genre",
    "missing_album_artist",
    "missing_album",
    "missing_track_number",
    "missing_performer_or_ensemble",
}

UNKNOWN_FAMILY = "Unknown / Review Needed"


@dataclass(frozen=True)
class QualityDecisionResult:
    decision: str
    severity: str
    score: float
    reasons: list[str]
    blocking_flags: list[str]
    warning_flags: list[str]


def _text(value: Any) -> str:
    return str(value or "").strip()


def _has(value: Any) -> bool:
    return bool(_text(value)) and _text(value).casefold() not in {"unknown", "none", "null"}


def _flag_types(flags: list[MetadataReviewFlag]) -> set[str]:
    return {flag.flag_type for flag in flags if flag.status == "open"}


def _severity_for(decision: str) -> str:
    return {
        "approved_ready": "info",
        "review_recommended": "warning",
        "review_required": "error",
        "blocked": "critical",
    }[decision]


def _score_for(decision: str) -> float:
    return {
        "approved_ready": 100.0,
        "review_recommended": 70.0,
        "review_required": 40.0,
        "blocked": 0.0,
    }[decision]


def quality_decision_for_flags(flags: list[MetadataReviewFlag], profile: NormalizedMusicProfile) -> dict:
    result = evaluate_music_profile_quality(profile, flags)
    return {
        "decision": result.decision,
        "severity": result.severity,
        "score": result.score,
        "reasons": result.reasons,
        "blocking_flags": result.blocking_flags,
        "warning_flags": result.warning_flags,
    }


def evaluate_music_profile_quality(
    profile: NormalizedMusicProfile,
    flags: list[MetadataReviewFlag],
) -> QualityDecisionResult:
    flag_types = _flag_types(flags)
    reasons: list[str] = []
    blocking_flags = sorted(flag_types & BLOCKING_FLAGS)
    warning_flags = sorted(flag_types & WARNING_FLAGS)
    error_flags = sorted(flag_types & ERROR_FLAGS)

    has_artist = _has(profile.artist) or _has(profile.album_artist)
    has_title = _has(profile.title)
    has_genre = _has(profile.primary_genre) and profile.genre_family != UNKNOWN_FAMILY

    if blocking_flags:
        reasons.append("critical_metadata_flag_present")
    if not has_artist and not has_title:
        blocking_flags.append("empty_identity")
        reasons.append("missing_both_title_and_artist")
    if len([flag for flag in flags if flag.flag_type == "mojibake_detected" and flag.status == "open"]) >= 2:
        blocking_flags.append("severe_encoding_damage")
        reasons.append("multiple_key_fields_have_mojibake")

    if blocking_flags:
        return QualityDecisionResult(
            decision="blocked",
            severity=_severity_for("blocked"),
            score=_score_for("blocked"),
            reasons=list(dict.fromkeys(reasons)),
            blocking_flags=sorted(set(blocking_flags)),
            warning_flags=warning_flags,
        )

    if not has_title:
        reasons.append("missing_title")
    if not has_artist:
        reasons.append("missing_artist_and_album_artist")
    if not has_genre:
        reasons.append("genre_unknown_or_unmapped")
    if error_flags:
        reasons.extend(error_flags)

    if profile.genre_family == "Classical":
        composer_ready = _has(profile.composer)
        work_ready = _has(profile.work) or _has(profile.movement)
        performer_ready = any(_has(value) for value in (
            profile.artist,
            profile.album_artist,
            profile.conductor,
            profile.orchestra,
            profile.ensemble,
            profile.soloist,
        ))
        if not composer_ready:
            reasons.append("classical_missing_composer")
        if not work_ready:
            reasons.append("classical_missing_work_or_movement")
        if not performer_ready:
            warning_flags.append("missing_performer_or_ensemble")
            reasons.append("classical_missing_performer_or_ensemble")
        if not composer_ready or not work_ready:
            return QualityDecisionResult(
                decision="review_required",
                severity=_severity_for("review_required"),
                score=_score_for("review_required"),
                reasons=list(dict.fromkeys(reasons)),
                blocking_flags=error_flags,
                warning_flags=sorted(set(warning_flags)),
            )

    if reasons:
        return QualityDecisionResult(
            decision="review_required",
            severity=_severity_for("review_required"),
            score=_score_for("review_required"),
            reasons=list(dict.fromkeys(reasons)),
            blocking_flags=error_flags,
            warning_flags=sorted(set(warning_flags)),
        )

    recommended_reasons: list[str] = []
    if "possible_broad_genre" in flag_types:
        recommended_reasons.append("broad_genre_refined_by_path_evidence")
    if "missing_album_artist" in flag_types:
        recommended_reasons.append("missing_album_artist_with_usable_track_metadata")
    if "missing_album" in flag_types:
        recommended_reasons.append("missing_album")
    if "missing_performer_or_ensemble" in flag_types:
        recommended_reasons.append("classical_missing_performer_or_ensemble")
    if profile.metadata_confidence is not None and profile.metadata_confidence < 0.65:
        recommended_reasons.append("low_confidence_but_usable_metadata")

    if recommended_reasons:
        return QualityDecisionResult(
            decision="review_recommended",
            severity=_severity_for("review_recommended"),
            score=_score_for("review_recommended"),
            reasons=list(dict.fromkeys(recommended_reasons)),
            blocking_flags=[],
            warning_flags=sorted(set(warning_flags)),
        )

    return QualityDecisionResult(
        decision="approved_ready",
        severity=_severity_for("approved_ready"),
        score=_score_for("approved_ready"),
        reasons=["metadata_ready"],
        blocking_flags=[],
        warning_flags=[],
    )


def _decision_row(db: Session, media_file_id: int) -> MetadataQualityDecision | None:
    return (
        db.query(MetadataQualityDecision)
        .filter(MetadataQualityDecision.media_file_id == media_file_id)
        .one_or_none()
    )


def snapshot_or_update_quality_decision(db: Session, media_file_id: int) -> MetadataQualityDecision:
    media_file = db.get(MediaFile, media_file_id)
    if media_file is None:
        raise ValueError(f"MediaFile not found: {media_file_id}")
    profile = (
        db.query(NormalizedMusicProfile)
        .filter(NormalizedMusicProfile.media_file_id == media_file_id)
        .one_or_none()
    )
    if profile is None:
        raise ValueError(f"NormalizedMusicProfile not found for media_file_id={media_file_id}")
    flags = (
        db.query(MetadataReviewFlag)
        .filter(MetadataReviewFlag.media_file_id == media_file_id, MetadataReviewFlag.status == "open")
        .all()
    )
    result = evaluate_music_profile_quality(profile, flags)
    row = _decision_row(db, media_file_id)
    if row is None:
        row = MetadataQualityDecision(media_file_id=media_file_id)
        db.add(row)
    row.normalized_music_profile_id = profile.id
    row.batch_id = media_file.ingest_batch_id
    row.decision = result.decision
    row.severity = result.severity
    row.score = result.score
    row.reasons_json = result.reasons
    row.blocking_flags_json = result.blocking_flags
    row.warning_flags_json = result.warning_flags
    row.updated_at = now_utc()
    db.flush()
    return row


def snapshot_batch_quality_decisions(db: Session, batch_id: int) -> dict:
    media_files = db.query(MediaFile).filter(MediaFile.ingest_batch_id == batch_id).all()
    counts = {
        "total_files": 0,
        "approved_ready_count": 0,
        "review_recommended_count": 0,
        "review_required_count": 0,
        "blocked_count": 0,
        "flag_counts": {},
        "worst_decision": "approved_ready",
    }
    for media_file in media_files:
        decision = snapshot_or_update_quality_decision(db, media_file.id)
        counts["total_files"] += 1
        counts[f"{decision.decision}_count"] += 1
        if DECISION_ORDER[decision.decision] > DECISION_ORDER[counts["worst_decision"]]:
            counts["worst_decision"] = decision.decision
        flags = (
            db.query(MetadataReviewFlag)
            .filter(MetadataReviewFlag.media_file_id == media_file.id, MetadataReviewFlag.status == "open")
            .all()
        )
        for flag in flags:
            counts["flag_counts"][flag.flag_type] = counts["flag_counts"].get(flag.flag_type, 0) + 1
    db.flush()
    return counts


def _profile_dict(profile: NormalizedMusicProfile | None) -> dict | None:
    if profile is None:
        return None
    return {
        "artist": profile.artist,
        "album_artist": profile.album_artist,
        "album": profile.album,
        "title": profile.title,
        "track_number": profile.track_number,
        "disc_number": profile.disc_number,
        "year": profile.year,
        "primary_genre": profile.primary_genre,
        "genre_family": profile.genre_family,
        "composer": profile.composer,
        "conductor": profile.conductor,
        "orchestra": profile.orchestra,
        "ensemble": profile.ensemble,
        "soloist": profile.soloist,
        "work": profile.work,
        "movement": profile.movement,
        "metadata_status": profile.metadata_status,
        "metadata_confidence": profile.metadata_confidence,
        "metadata_source": profile.metadata_source,
    }


def _flag_dict(flag: MetadataReviewFlag) -> dict:
    return {
        "id": flag.id,
        "flag_type": flag.flag_type,
        "severity": flag.severity,
        "field_name": flag.field_name,
        "raw_value": flag.raw_value,
        "normalized_value": flag.normalized_value,
        "message": flag.message,
        "status": flag.status,
    }


def _decision_item(db: Session, media_file: MediaFile) -> dict:
    decision = snapshot_or_update_quality_decision(db, media_file.id)
    profile = (
        db.query(NormalizedMusicProfile)
        .filter(NormalizedMusicProfile.media_file_id == media_file.id)
        .one_or_none()
    )
    flags = (
        db.query(MetadataReviewFlag)
        .filter(MetadataReviewFlag.media_file_id == media_file.id, MetadataReviewFlag.status == "open")
        .all()
    )
    return {
        "media_file_id": media_file.id,
        "ingest_file_id": media_file.ingest_file_id,
        "file_name": media_file.file_name,
        "relative_path": media_file.relative_path,
        "decision": decision.decision,
        "severity": decision.severity,
        "score": decision.score,
        "reasons": list(decision.reasons_json or []),
        "blocking_flags": list(decision.blocking_flags_json or []),
        "warning_flags": list(decision.warning_flags_json or []),
        "profile": _profile_dict(profile),
        "review_flags": [_flag_dict(flag) for flag in flags],
    }


def get_batch_metadata_quality(db: Session, batch_id: int) -> dict:
    media_files = (
        db.query(MediaFile)
        .filter(MediaFile.ingest_batch_id == batch_id)
        .order_by(MediaFile.relative_path, MediaFile.file_name, MediaFile.id)
        .all()
    )
    counts = {
        "batch_id": batch_id,
        "total_files": 0,
        "approved_ready_count": 0,
        "review_recommended_count": 0,
        "review_required_count": 0,
        "blocked_count": 0,
        "worst_decision": "approved_ready",
        "flag_counts": {},
        "items": [],
    }
    for media_file in media_files:
        item = _decision_item(db, media_file)
        decision = item["decision"]
        counts["total_files"] += 1
        counts[f"{decision}_count"] += 1
        if DECISION_ORDER[decision] > DECISION_ORDER[counts["worst_decision"]]:
            counts["worst_decision"] = decision
        for flag in item["review_flags"]:
            flag_type = str(flag.get("flag_type") or "unknown")
            counts["flag_counts"][flag_type] = counts["flag_counts"].get(flag_type, 0) + 1
        counts["items"].append(item)
    db.flush()
    return counts


def get_metadata_quality_summary_for_batches(db: Session, batch_ids: list[int]) -> dict[int, dict]:
    return {
        batch_id: {
            key: value
            for key, value in get_batch_metadata_quality(db, batch_id).items()
            if key != "items"
        }
        for batch_id in batch_ids
    }
