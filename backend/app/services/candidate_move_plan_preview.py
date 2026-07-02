from __future__ import annotations

import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

from app.models.archive import IngestBatch
from app.models.media_metadata import (
    CandidateMember,
    FragmentReconstructionDecision,
    MediaIdentityCandidate,
    MixedMediaFlag,
    SourceFragment,
    UniversalIngestionReviewAction,
)
from app.services.universal_ingestion import snapshot_universal_ingestion_boundary
from app.services.universal_review_routing import _is_source_chunk_name

MEDIA_TARGET_LIBRARY = {
    "music": "Music/Library",
    "audiobook": "Audiobooks/Library",
    "ebook": "Books/Library",
    "comic": "Comics/Library",
    "movie": "Movies/Library",
    "tv": "TV/Library",
    "artwork": "_SIDECAR_OR_ARTWORK_REVIEW",
    "subtitle": "_SIDECAR_OR_ARTWORK_REVIEW",
    "sidecar": "_SIDECAR_OR_ARTWORK_REVIEW",
    "sidecar_metadata": "_SIDECAR_OR_ARTWORK_REVIEW",
    "playlist": "_SIDECAR_OR_ARTWORK_REVIEW",
    "archive": "_REVIEW/Archives",
    "archive_file": "_REVIEW/Archives",
    "unknown": "_REVIEW/Unknown",
}


def _safe_part(value: Any, fallback: str = "Unknown") -> str:
    text = str(value or "").strip() or fallback
    text = re.sub(r'[<>:"/\\|?*]+', " ", text)
    text = re.sub(r"\s+", " ", text).strip(" .")
    return text or fallback


def _active_action_dict(row: UniversalIngestionReviewAction | None) -> dict[str, Any] | None:
    if row is None:
        return None
    return {
        "id": row.id,
        "action_type": row.action_type,
        "target_media_class": row.target_media_class,
        "target_candidate_id": row.target_candidate_id,
        "override_title": row.override_title,
        "override_primary_creator": row.override_primary_creator,
        "override_year": row.override_year,
        "reason": row.reason,
        "note": row.note,
    }


def _candidate_actions(db: Session, batch_id: int) -> dict[int, list[UniversalIngestionReviewAction]]:
    rows = (
        db.query(UniversalIngestionReviewAction)
        .filter(
            UniversalIngestionReviewAction.batch_id == batch_id,
            UniversalIngestionReviewAction.decision_status == "active",
        )
        .order_by(UniversalIngestionReviewAction.updated_at.desc())
        .all()
    )
    grouped: dict[int, list[UniversalIngestionReviewAction]] = defaultdict(list)
    for row in rows:
        if row.candidate_id is not None:
            grouped[row.candidate_id].append(row)
    return grouped


def _best_action(actions: list[UniversalIngestionReviewAction]) -> UniversalIngestionReviewAction | None:
    priority = {
        "block_candidate": 0,
        "exclude_from_move_plan": 1,
        "split_candidate": 2,
        "mark_review_later": 3,
        "override_media_class": 4,
        "override_identity": 5,
        "approve_candidate": 6,
        "merge_candidates": 7,
    }
    return sorted(actions, key=lambda row: priority.get(row.action_type, 99))[0] if actions else None


def _effective_identity(candidate: MediaIdentityCandidate, actions: list[UniversalIngestionReviewAction]) -> tuple[str | None, str | None, str | None, str]:
    title = candidate.candidate_title
    creator = candidate.candidate_primary_creator
    year = candidate.candidate_year
    media_type = candidate.candidate_media_type or "unknown"
    for action in actions:
        if action.action_type == "override_identity":
            title = action.override_title or title
            creator = action.override_primary_creator or creator
            year = action.override_year or year
        elif action.action_type == "override_media_class" and action.target_media_class:
            media_type = _media_type_from_class(action.target_media_class)
    return title, creator, year, media_type


def _media_type_from_class(media_class: str) -> str:
    mapping = {
        "music_audio": "music",
        "audiobook_audio": "audiobook",
        "ebook": "ebook",
        "comic": "comic",
        "movie": "movie",
        "tv_episode": "tv",
        "video_extra": "movie",
        "subtitle": "subtitle",
        "artwork": "artwork",
        "sidecar_metadata": "sidecar",
        "playlist": "playlist",
        "archive_file": "archive",
        "unknown": "unknown",
    }
    return mapping.get(media_class, media_class)


def _destination(media_type: str, title: str | None, creator: str | None, year: str | None, key: str, weak_identity: bool) -> tuple[str, str]:
    if weak_identity:
        weak = _safe_part(title or creator or key, "Weak Identity")
        return "_REVIEW/Weak Identity", f"_REVIEW/Weak Identity/{weak}/"
    library = MEDIA_TARGET_LIBRARY.get(media_type, "_REVIEW/Unknown")
    title_part = _safe_part(title or key, "Unknown Title")
    creator_part = _safe_part(creator, "Unknown Creator")
    year_part = f" ({_safe_part(year, '')})" if year else ""
    if media_type == "music":
        return library, f"{library}/{creator_part}/{title_part}{year_part}/"
    if media_type == "audiobook":
        return library, f"{library}/{creator_part}/{title_part}/"
    if media_type == "ebook":
        return library, f"{library}/{creator_part}/{title_part}/"
    if media_type == "comic":
        return library, f"{library}/{title_part}/"
    if media_type == "movie":
        return library, f"{library}/{title_part}{year_part}/"
    if media_type == "tv":
        return library, f"{library}/{title_part}/Season XX/"
    if media_type in {"artwork", "subtitle", "sidecar", "sidecar_metadata", "playlist"}:
        return library, f"{library}/{title_part}/"
    if media_type in {"archive", "archive_file"}:
        return "_REVIEW/Archives", f"_REVIEW/Archives/{title_part}/"
    return "_REVIEW/Unknown", f"_REVIEW/Unknown/{title_part}/"


def _empty(batch_id: int) -> dict[str, Any]:
    return {
        "batch_id": batch_id,
        "status": "not_analyzed",
        "summary": {
            "candidate_count": 0,
            "source_fragment_count": 0,
            "member_count": 0,
            "media_class_counts": {},
            "decision_counts": {},
            "active_action_count": 0,
            "mixed_media": False,
            "music_only_fragmented": False,
            "blocked_conflict_count": 0,
            "review_required_count": 0,
        },
        "preview_groups": [],
        "global_warnings": ["universal_analysis_missing"],
        "next_actions": ["Run preview analysis"],
    }


def build_candidate_move_plan_preview(db: Session, batch_id: int, *, snapshot: bool = False) -> dict[str, Any]:
    """Return a preview-only candidate move plan. No filesystem writes."""
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
            return _empty(batch_id)
    if not has_analysis:
        return _empty(batch_id)

    fragments = db.query(SourceFragment).filter(SourceFragment.batch_id == batch_id).all()
    candidates = db.query(MediaIdentityCandidate).filter(MediaIdentityCandidate.batch_id == batch_id).order_by(MediaIdentityCandidate.id).all()
    decisions = db.query(FragmentReconstructionDecision).filter(FragmentReconstructionDecision.batch_id == batch_id).all()
    flags = db.query(MixedMediaFlag).filter(MixedMediaFlag.batch_id == batch_id).all()
    actions_by_candidate = _candidate_actions(db, batch_id)
    candidate_ids = [candidate.id for candidate in candidates]
    members = db.query(CandidateMember).filter(CandidateMember.candidate_id.in_(candidate_ids)).all() if candidate_ids else []
    members_by_candidate: dict[int, list[CandidateMember]] = defaultdict(list)
    for member in members:
        members_by_candidate[member.candidate_id].append(member)
    decision_by_candidate = {row.candidate_id: row for row in decisions if row.candidate_id is not None}
    decision_counts = Counter(row.decision for row in decisions)
    media_class_counts = Counter(candidate.candidate_media_type or "unknown" for candidate in candidates)
    media_types = set(media_class_counts)
    mixed_media = len(media_types - {"music"}) > 0 or len(media_types) > 1
    source_fragment_group_count = len([flag for flag in flags if flag.flag_type == "source_fragment_group_detected"])
    music_only_fragmented = media_types == {"music"} and source_fragment_group_count > 0

    preview_groups: list[dict[str, Any]] = []
    global_warnings: list[str] = []
    if mixed_media:
        global_warnings.append("mixed_media")
    if music_only_fragmented:
        global_warnings.append("music_only_fragmented")
    if any(row.decision == "blocked_conflict" for row in decisions):
        global_warnings.append("blocked_conflict")

    for candidate in candidates:
        actions = actions_by_candidate.get(candidate.id, [])
        best_action = _best_action(actions)
        title, creator, year, media_type = _effective_identity(candidate, actions)
        decision = decision_by_candidate.get(candidate.id)
        candidate_members = members_by_candidate.get(candidate.id, [])
        source_fragment_names = sorted({Path(member.relative_path).parts[0] if Path(member.relative_path).parts else "." for member in candidate_members})
        weak_identity = _is_source_chunk_name(title) or _is_source_chunk_name(creator) or _is_source_chunk_name(candidate.candidate_key)
        target_library, destination_preview = _destination(media_type, title, creator, year, candidate.candidate_key, weak_identity)
        warnings: list[str] = []
        requires_review = False
        blocked = False
        if weak_identity:
            warnings.append("source_chunk_identity_risk")
            requires_review = True
        if decision and decision.decision in {"review_required", "split_recommended"}:
            requires_review = True
        if decision and decision.decision == "blocked_conflict":
            blocked = True
        for action in actions:
            if action.action_type == "mark_review_later":
                requires_review = True
                warnings.append("review_later")
            elif action.action_type == "exclude_from_move_plan":
                target_library = "_EXCLUDED_FROM_MOVE_PLAN"
                destination_preview = "_EXCLUDED_FROM_MOVE_PLAN"
                warnings.append("excluded_from_move_plan")
            elif action.action_type == "split_candidate":
                requires_review = True
                warnings.append("split_required")
            elif action.action_type == "block_candidate":
                blocked = True
                warnings.append("blocked_by_user")
            elif action.action_type == "merge_candidates":
                warnings.append("merge_preview_not_applied")
        if best_action and best_action.action_type == "approve_candidate" and not blocked and "source_chunk_identity_risk" not in warnings:
            requires_review = False
        preview_groups.append({
            "candidate_id": candidate.id,
            "candidate_media_type": media_type,
            "candidate_title": title,
            "candidate_primary_creator": creator,
            "candidate_year": year,
            "confidence": candidate.candidate_confidence and f"{candidate.candidate_confidence:.2f}",
            "member_count": len(candidate_members),
            "source_fragment_count": len(source_fragment_names),
            "active_action": _active_action_dict(best_action),
            "decision": decision.decision if decision else None,
            "recommended_action": decision.recommended_action if decision else None,
            "target_library": target_library,
            "destination_preview": destination_preview,
            "source_fragment_names": source_fragment_names,
            "warnings": sorted(set(warnings)),
            "blocked": blocked,
            "requires_review": requires_review,
        })

    blocked_count = sum(1 for group in preview_groups if group["blocked"])
    review_count = sum(1 for group in preview_groups if group["requires_review"])
    if blocked_count:
        status = "blocked_conflict"
    elif review_count or mixed_media:
        status = "review_required"
    else:
        status = "ready"
    next_actions = []
    if status == "blocked_conflict":
        next_actions.append("Resolve blocked candidate conflicts before final move planning")
    if mixed_media:
        next_actions.append("Split or approve candidate groups before using media-specific editors")
    if music_only_fragmented:
        next_actions.append("Review reconstructed music groups before opening discography editor")
    if not next_actions:
        next_actions.append("Preview ready for media-specific review")

    return {
        "batch_id": batch_id,
        "status": status,
        "summary": {
            "candidate_count": len(candidates),
            "source_fragment_count": len(fragments),
            "member_count": len(members),
            "media_class_counts": dict(media_class_counts),
            "decision_counts": dict(decision_counts),
            "active_action_count": sum(len(items) for items in actions_by_candidate.values()),
            "mixed_media": mixed_media,
            "music_only_fragmented": music_only_fragmented,
            "blocked_conflict_count": decision_counts.get("blocked_conflict", 0) + len([group for group in preview_groups if group["blocked"]]),
            "review_required_count": decision_counts.get("review_required", 0) + len([group for group in preview_groups if group["requires_review"]]),
        },
        "preview_groups": preview_groups,
        "global_warnings": sorted(set(global_warnings)),
        "next_actions": next_actions,
    }