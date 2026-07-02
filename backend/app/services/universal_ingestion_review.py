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
)
from app.services.universal_ingestion import snapshot_universal_ingestion_boundary

PHASE_NAME = "AA-M4D.2 — Universal Ingestion Review API + UI"
DECISION_ORDER = {
    "safe_group": 0,
    "merge_recommended": 1,
    "split_recommended": 2,
    "review_required": 3,
    "blocked_conflict": 4,
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

    decisions_by_candidate: dict[int, FragmentReconstructionDecision] = {}
    for decision in decisions:
        if decision.candidate_id is not None:
            decisions_by_candidate[decision.candidate_id] = decision
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
                "track_number": _first(fields, "track_number", "tracknumber"),
                "disc_number": _first(fields, "disc_number", "discnumber"),
                "season_number": evidence.get("season"),
                "episode_number": evidence.get("episode"),
                "title": _first(fields, "title"),
                "artist_or_author": _first(fields, "artist", "album_artist", "albumartist", "author", "composer"),
                "album_or_series": _first(fields, "album", "series"),
                "member_role": _member_role(member),
                "confidence": evidence.get("confidence"),
                "reason": evidence.get("fragment_group_key") or evidence.get("extension"),
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
        },
        "source_fragments": source_fragments,
        "candidates": candidate_payloads,
        "reconstruction_decisions": decision_payloads,
        "mixed_media_flags": flag_payloads,
    }