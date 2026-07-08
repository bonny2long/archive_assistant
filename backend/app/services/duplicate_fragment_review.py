from __future__ import annotations

import re
from collections import defaultdict
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session, selectinload

from app.models.archive import IngestBatch, IngestFile
from app.services.parent_candidate_materialization import build_parent_candidate_summary

DUPLICATE_STATE_NONE = "none"
DUPLICATE_STATE_POSSIBLE_DUPLICATE = "possible_duplicate"
DUPLICATE_STATE_POSSIBLE_FRAGMENT = "possible_fragment"
DUPLICATE_STATE_POSSIBLE_EDITION_CONFLICT = "possible_edition_conflict"
DUPLICATE_REVIEWED_STATES = {
    "reviewed_keep_separate",
    "reviewed_merge_required",
    "reviewed_duplicate",
    "reviewed_blocked",
}
BLOCKING_DUPLICATE_STATES = {
    DUPLICATE_STATE_POSSIBLE_DUPLICATE,
    DUPLICATE_STATE_POSSIBLE_FRAGMENT,
    DUPLICATE_STATE_POSSIBLE_EDITION_CONFLICT,
    "reviewed_merge_required",
    "reviewed_duplicate",
    "reviewed_blocked",
}
REVIEWABLE_BATCH_STATUSES = {
    "pending_review",
    "needs_metadata_review",
    "metadata_recovery",
    "approved",
}
EDITION_TOKENS = {
    "anniversary",
    "clean",
    "deluxe",
    "director",
    "directors",
    "edition",
    "explicit",
    "extended",
    "final",
    "remaster",
    "remastered",
    "remix",
    "theatrical",
    "version",
}


def normalize_identity_value(value: Any) -> str:
    if value is None:
        return ""
    text = str(value).strip().casefold()
    text = text.replace("'", "").replace("\u2019", "").replace("\u2018", "")
    text = re.sub(r"[\"\u201c\u201d]", "", text)
    text = re.sub(r"[\\/_:;,.!?]+", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def year_value(metadata: dict[str, Any]) -> str:
    for key in ("year", "date", "released", "release_year"):
        value = metadata.get(key)
        if value:
            match = re.search(r"\d{4}", str(value))
            if match:
                return match.group(0)
    return ""


def _media_type(batch: IngestBatch, metadata: dict[str, Any]) -> str:
    detected = batch.detected_type or metadata.get("type") or metadata.get("review_type") or "unknown"
    if detected == "music_discography":
        return "music_discography"
    if detected in {"video_movie", "movie"}:
        return "movie"
    if detected in {"video_tv_show", "tv_show"}:
        return "tv"
    if detected in {"book", "ebook", "comic"}:
        return str(metadata.get("type") or detected)
    return detected


def _identity_parts(batch: IngestBatch, metadata: dict[str, Any]) -> tuple[str, str, str, str, str]:
    media_type = _media_type(batch, metadata)
    if media_type == "music_album":
        creator = metadata.get("artist") or metadata.get("albumartist") or metadata.get("album_artist")
        title = metadata.get("album") or metadata.get("title")
        edition = metadata.get("edition") or metadata.get("release_type")
        return media_type, normalize_identity_value(creator), normalize_identity_value(title), year_value(metadata), normalize_identity_value(edition)
    if media_type == "audiobook":
        creator = metadata.get("author") or metadata.get("artist") or metadata.get("albumartist")
        title = metadata.get("title") or metadata.get("album")
        edition = metadata.get("series_index") or metadata.get("edition")
        return media_type, normalize_identity_value(creator), normalize_identity_value(title), year_value(metadata), normalize_identity_value(edition)
    if media_type in {"book", "ebook", "comic"}:
        creator = metadata.get("author") or metadata.get("artist")
        title = metadata.get("title") or metadata.get("series") or metadata.get("album")
        edition = metadata.get("series_index") or metadata.get("edition") or metadata.get("issue") or metadata.get("volume")
        return media_type, normalize_identity_value(creator), normalize_identity_value(title), year_value(metadata), normalize_identity_value(edition)
    if media_type == "movie":
        title = metadata.get("title") or metadata.get("movie_title")
        edition = metadata.get("edition") or metadata.get("source") or metadata.get("resolution")
        return media_type, "", normalize_identity_value(title), year_value(metadata), normalize_identity_value(edition)
    if media_type == "tv":
        title = metadata.get("show_title") or metadata.get("title")
        season = metadata.get("season_number") or metadata.get("season") or ""
        episode = metadata.get("episode_number") or metadata.get("episode") or ""
        episode_title = metadata.get("episode_title") or ""
        edition = f"s{season}:e{episode}:{episode_title}"
        return media_type, "", normalize_identity_value(title), year_value(metadata), normalize_identity_value(edition)
    title = metadata.get("title") or metadata.get("name") or metadata.get("album")
    creator = metadata.get("artist") or metadata.get("author") or metadata.get("albumartist")
    return media_type, normalize_identity_value(creator), normalize_identity_value(title), year_value(metadata), ""


def canonical_identity_key(batch: IngestBatch) -> str | None:
    metadata = batch.metadata_json or {}
    media_type, creator, title, year, edition = _identity_parts(batch, metadata)
    if media_type in {"unknown_type", "unsupported_file", "music_discography"}:
        return None
    if not title:
        return None
    if media_type in {"music_album", "audiobook", "book", "ebook", "comic"} and not creator:
        return None
    base_parts = [media_type, creator, title, year]
    if media_type == "tv" and edition:
        base_parts.append(edition)
    return ":".join(base_parts)


def _display_title(batch: IngestBatch, metadata: dict[str, Any]) -> str:
    return str(metadata.get("album") or metadata.get("title") or metadata.get("show_title") or metadata.get("name") or Path(batch.source_path).name)


def _display_creator(metadata: dict[str, Any]) -> str | None:
    value = metadata.get("artist") or metadata.get("albumartist") or metadata.get("album_artist") or metadata.get("author")
    return str(value) if value else None


def _item_count(batch: IngestBatch, metadata: dict[str, Any]) -> int:
    for key in ("track_count", "audiobook_file_count", "book_file_count", "video_file_count", "episode_count", "file_count"):
        value = metadata.get(key)
        if isinstance(value, int) and value > 0:
            return value
        if isinstance(value, str) and value.isdigit() and int(value) > 0:
            return int(value)
    return len(batch.files or [])


def _has_edition_signal(batch: IngestBatch, metadata: dict[str, Any]) -> bool:
    values = [
        metadata.get("edition"),
        metadata.get("release_type"),
        metadata.get("source"),
        metadata.get("resolution"),
        metadata.get("title"),
        metadata.get("album"),
        Path(batch.source_path).name,
    ]
    tokens = set()
    for value in values:
        tokens.update(normalize_identity_value(value).split())
    return bool(tokens & EDITION_TOKENS)


def _destination_key(batch: IngestBatch) -> str | None:
    if not batch.suggested_destination:
        return None
    return normalize_identity_value(str(batch.suggested_destination).replace("\\", "/"))


def _has_missing_file_ownership(batch: IngestBatch) -> bool:
    metadata = batch.metadata_json or {}
    return _item_count(batch, metadata) > 0 and len(batch.files or []) == 0

def _batch_row(batch: IngestBatch) -> dict[str, Any]:
    metadata = batch.metadata_json or {}
    item_count = _item_count(batch, metadata)
    file_count = len(batch.files or [])
    missing_files = item_count > 0 and file_count == 0
    return {
        "batch_id": batch.id,
        "title": _display_title(batch, metadata),
        "creator": _display_creator(metadata),
        "year": year_value(metadata) or None,
        "item_count": item_count,
        "file_count": file_count,
        "file_ownership_status": "missing_files" if missing_files else "verified",
        "file_ownership_warning": "Batch has media item metadata but no attached scoped files." if missing_files else None,
        "suggested_destination": batch.suggested_destination,
        "source_path": batch.source_path,
        "status": batch.status,
        "detected_type": batch.detected_type,
    }


def _review_type_for(batches: list[IngestBatch], *, same_destination: bool) -> str:
    counts = {_item_count(batch, batch.metadata_json or {}) for batch in batches}
    if len(counts) > 1:
        return DUPLICATE_STATE_POSSIBLE_FRAGMENT
    if any(_has_edition_signal(batch, batch.metadata_json or {}) for batch in batches):
        return DUPLICATE_STATE_POSSIBLE_EDITION_CONFLICT
    return DUPLICATE_STATE_POSSIBLE_DUPLICATE if same_destination or len(batches) > 1 else DUPLICATE_STATE_NONE


def _cluster_reason(review_type: str, same_destination: bool) -> str:
    if same_destination and review_type == DUPLICATE_STATE_POSSIBLE_FRAGMENT:
        return "Multiple pending batches share the same destination preview path with different item counts."
    if same_destination:
        return "Multiple pending batches share the same destination preview path."
    if review_type == DUPLICATE_STATE_POSSIBLE_FRAGMENT:
        return "Multiple pending batches share identity with different item counts."
    if review_type == DUPLICATE_STATE_POSSIBLE_EDITION_CONFLICT:
        return "Similar pending batches may be separate editions and need review."
    return "Multiple pending batches share the same media identity."


def _cluster_for(cluster_id: str, batches: list[IngestBatch], *, same_destination: bool) -> dict[str, Any]:
    metadata = batches[0].metadata_json or {}
    review_type = _review_type_for(batches, same_destination=same_destination)
    rows = [_batch_row(batch) for batch in sorted(batches, key=lambda item: item.id)]
    return {
        "cluster_id": cluster_id,
        "review_type": review_type,
        "media_type": _media_type(batches[0], metadata),
        "confidence": "high" if same_destination else "medium",
        "reason": _cluster_reason(review_type, same_destination),
        "has_file_ownership_warnings": any(row["file_ownership_status"] == "missing_files" for row in rows),
        "batches": rows,
    }


def _load_reviewable_batches(db: Session) -> list[IngestBatch]:
    batches = (
        db.query(IngestBatch)
        .options(selectinload(IngestBatch.files))
        .filter(IngestBatch.status.in_(REVIEWABLE_BATCH_STATUSES))
        .all()
    )
    return [
        batch for batch in batches
        if not build_parent_candidate_summary(db, batch)["is_parent_review_container"]
    ]


def build_duplicate_fragment_review(db: Session, batch_id: int | None = None) -> dict[str, Any]:
    batches = [
        batch for batch in _load_reviewable_batches(db)
        if _item_count(batch, batch.metadata_json or {}) > 0 or batch.suggested_destination
    ]
    by_id = {batch.id: batch for batch in batches}
    by_identity: dict[str, list[int]] = defaultdict(list)
    by_destination: dict[str, list[int]] = defaultdict(list)
    for batch in batches:
        identity = canonical_identity_key(batch)
        if identity:
            by_identity[identity].append(batch.id)
        destination = _destination_key(batch)
        if destination:
            by_destination[destination].append(batch.id)

    parent: dict[int, int] = {batch.id: batch.id for batch in batches}

    def find(batch_id_value: int) -> int:
        root = parent[batch_id_value]
        while root != parent[root]:
            root = parent[root]
        while batch_id_value != root:
            next_id = parent[batch_id_value]
            parent[batch_id_value] = root
            batch_id_value = next_id
        return root

    def union(ids: list[int]) -> None:
        if len(ids) <= 1:
            return
        first = find(ids[0])
        for item in ids[1:]:
            parent[find(item)] = first

    for grouped_ids in by_destination.values():
        if len(grouped_ids) > 1:
            union(grouped_ids)
    for grouped_ids in by_identity.values():
        if len(grouped_ids) > 1:
            union(grouped_ids)

    component_ids: dict[int, set[int]] = defaultdict(set)
    for item in parent:
        component_ids[find(item)].add(item)

    clusters: list[dict[str, Any]] = []
    for ids in component_ids.values():
        if len(ids) <= 1:
            continue
        identity_keys = [key for key, grouped in by_identity.items() if len(ids.intersection(grouped)) > 1]
        destination_keys = [key for key, grouped in by_destination.items() if len(ids.intersection(grouped)) > 1]
        cluster_id = sorted(identity_keys)[0] if identity_keys else f"destination:{sorted(destination_keys)[0]}"
        grouped_batches = [by_id[item] for item in sorted(ids)]
        clusters.append(_cluster_for(cluster_id, grouped_batches, same_destination=bool(destination_keys)))

    if batch_id is not None:
        clusters = [
            cluster for cluster in clusters
            if any(row["batch_id"] == batch_id for row in cluster["batches"])
        ]
    return {"clusters": sorted(clusters, key=lambda item: item["cluster_id"])}


def duplicate_fragment_summary_for_batch(db: Session, batch: IngestBatch) -> dict[str, Any]:
    metadata = batch.metadata_json or {}
    reviewed_state = metadata.get("duplicate_fragment_review_state")
    if reviewed_state in DUPLICATE_REVIEWED_STATES and reviewed_state == "reviewed_keep_separate" and not _has_missing_file_ownership(batch):
        return {
            "possible_duplicate_group_id": None,
            "possible_duplicate_count": 0,
            "possible_fragment_group_id": None,
            "possible_fragment_count": 0,
            "duplicate_fragment_review_state": reviewed_state,
            "requires_duplicate_review": False,
        }

    clusters = build_duplicate_fragment_review(db, batch.id)["clusters"] if db is not None else []
    if not clusters:
        return {
            "possible_duplicate_group_id": None,
            "possible_duplicate_count": 0,
            "possible_fragment_group_id": None,
            "possible_fragment_count": 0,
            "duplicate_fragment_review_state": reviewed_state or DUPLICATE_STATE_NONE,
            "requires_duplicate_review": reviewed_state in BLOCKING_DUPLICATE_STATES,
        }

    state_order = {
        DUPLICATE_STATE_POSSIBLE_FRAGMENT: 0,
        DUPLICATE_STATE_POSSIBLE_DUPLICATE: 1,
        DUPLICATE_STATE_POSSIBLE_EDITION_CONFLICT: 2,
    }
    cluster = sorted(clusters, key=lambda item: state_order.get(item["review_type"], 99))[0]
    review_type = str(cluster["review_type"])
    count = len(cluster["batches"])
    return {
        "possible_duplicate_group_id": cluster["cluster_id"] if review_type != DUPLICATE_STATE_POSSIBLE_FRAGMENT else None,
        "possible_duplicate_count": count if review_type != DUPLICATE_STATE_POSSIBLE_FRAGMENT else 0,
        "possible_fragment_group_id": cluster["cluster_id"] if review_type == DUPLICATE_STATE_POSSIBLE_FRAGMENT else None,
        "possible_fragment_count": count if review_type == DUPLICATE_STATE_POSSIBLE_FRAGMENT else 0,
        "duplicate_fragment_review_state": review_type,
        "requires_duplicate_review": review_type in BLOCKING_DUPLICATE_STATES,
    }