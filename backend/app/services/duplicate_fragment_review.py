from __future__ import annotations

import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session, selectinload

from app.core.config import settings
from app.core.time import now_utc
from app.models.archive import IngestBatch, IngestFile
from app.services.parent_candidate_materialization import build_parent_candidate_summary

DUPLICATE_STATE_NONE = "none"
DUPLICATE_STATE_POSSIBLE_DUPLICATE = "possible_duplicate"
DUPLICATE_STATE_POSSIBLE_FRAGMENT = "possible_fragment"
DUPLICATE_STATE_POSSIBLE_EDITION_CONFLICT = "possible_edition_conflict"
DUPLICATE_REVIEWED_STATES = {
    "reviewed_keep_separate",
    "reviewed_merged",
    "reviewed_merge_required",
    "reviewed_duplicate",
    "reviewed_blocked",
    "reviewed_later",
}
BLOCKING_DUPLICATE_STATES = {
    DUPLICATE_STATE_POSSIBLE_DUPLICATE,
    DUPLICATE_STATE_POSSIBLE_FRAGMENT,
    DUPLICATE_STATE_POSSIBLE_EDITION_CONFLICT,
    "reviewed_merge_required",
    "reviewed_duplicate",
    "reviewed_blocked",
    "reviewed_later",
}
REVIEWABLE_BATCH_STATUSES = {
    "pending_review",
    "needs_metadata_review",
    "metadata_recovery",
    "approved",
}
DUPLICATE_RESOLUTION_ACTIONS = {
    "keep_separate",
    "merge_into_one_batch",
    "mark_duplicate",
    "review_later",
    "block_move",
}
AUDIO_ROLE_VALUES = {"audio", "audio_track", "music_audio", "music_track", "discography_track"}
AUDIO_EXTENSIONS = {".mp3", ".flac", ".m4a", ".aac", ".wav", ".ogg", ".opus", ".wma", ".aiff", ".alac"}
MERGE_FORMAT_EXTENSIONS = {".flac": "FLAC", ".mp3": "MP3"}
_SAFE_PART_PATTERN = re.compile(r'[<>:"/\\|?*]+')


class DuplicateFragmentResolutionError(ValueError):
    pass

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

def _file_formats(batch: IngestBatch) -> list[str]:
    files = batch.files or []
    audio_formats = sorted({(_music_file_format(file) or _file_extension(file).lstrip(".").upper()) for file in files if _is_music_audio_file(file)})
    if audio_formats:
        return audio_formats
    return sorted({(file.extension or "").lower().lstrip(".") for file in files if file.extension})

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
        "file_formats": _file_formats(batch),
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
    file_formats = sorted({file_format for row in rows for file_format in row.get("file_formats", [])})
    return {
        "cluster_id": cluster_id,
        "review_type": review_type,
        "media_type": _media_type(batches[0], metadata),
        "confidence": "high" if same_destination else "medium",
        "reason": _cluster_reason(review_type, same_destination),
        "has_file_ownership_warnings": any(row["file_ownership_status"] == "missing_files" for row in rows),
        "mixed_file_formats": len(file_formats) > 1,
        "file_formats": file_formats,
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
    if _destination_sync_problem(batch):
        return {
            "possible_duplicate_group_id": None,
            "possible_duplicate_count": 0,
            "possible_fragment_group_id": None,
            "possible_fragment_count": 0,
            "duplicate_fragment_review_state": "reviewed_merge_required",
            "requires_duplicate_review": True,
        }
    if reviewed_state in {"reviewed_keep_separate", "reviewed_merged"} and not _has_missing_file_ownership(batch):
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

def _append_resolution_audit(batch: IngestBatch, record: dict[str, Any]) -> None:
    metadata = dict(batch.metadata_json or {})
    audit = list(metadata.get("duplicate_fragment_resolution_audit") or [])
    audit.append(record)
    metadata["duplicate_fragment_resolution_audit"] = audit
    metadata["duplicate_fragment_review_state"] = record["resolution_state"]
    metadata["duplicate_fragment_resolution_action"] = record["action"]
    metadata["duplicate_fragment_resolution_at"] = record["resolved_at"]
    batch.metadata_json = metadata
    batch.updated_at = now_utc()


def _resolution_record(action: str, cluster: dict[str, Any], **extra: Any) -> dict[str, Any]:
    return {
        "action": action,
        "cluster_id": cluster["cluster_id"],
        "review_type": cluster["review_type"],
        "source_batch_ids": [row["batch_id"] for row in cluster["batches"]],
        "source_paths": [row.get("source_path") for row in cluster["batches"]],
        "resolved_at": now_utc().isoformat(),
        **extra,
    }


def _load_cluster_batches(db: Session, cluster: dict[str, Any]) -> list[IngestBatch]:
    ids = [row["batch_id"] for row in cluster["batches"]]
    batches = (
        db.query(IngestBatch)
        .options(selectinload(IngestBatch.files))
        .filter(IngestBatch.id.in_(ids))
        .all()
    )
    by_id = {batch.id: batch for batch in batches}
    return [by_id[item] for item in ids if item in by_id]


def _canonical_batch(batches: list[IngestBatch], canonical_batch_id: int | None) -> IngestBatch:
    if canonical_batch_id is not None:
        for batch in batches:
            if batch.id == canonical_batch_id:
                return batch
        raise DuplicateFragmentResolutionError("Canonical batch is not part of this duplicate/fragment group.")
    return max(batches, key=lambda item: (len(item.files or []), -item.id))


def _normalized_destination(value: str | None) -> str:
    return normalize_identity_value(str(value or "").replace("\\", "/"))


def _safe_path_part(value: object, fallback: str = "Unknown") -> str:
    text = str(value or "").strip()
    if not text:
        text = fallback
    text = _SAFE_PART_PATTERN.sub(" ", text)
    text = re.sub(r"\s+", " ", text).strip(" .")
    return text or fallback


def _file_extension(ingest_file: IngestFile) -> str:
    value = ingest_file.extension or Path(ingest_file.file_name or ingest_file.file_path).suffix
    return str(value or "").lower()


def _is_music_audio_file(ingest_file: IngestFile) -> bool:
    return _file_extension(ingest_file) in AUDIO_EXTENSIONS or (ingest_file.detected_role or "") in AUDIO_ROLE_VALUES


def _music_file_format(ingest_file: IngestFile) -> str | None:
    return MERGE_FORMAT_EXTENSIONS.get(_file_extension(ingest_file))


def _first_text(*values: object, fallback: str = "") -> str:
    for value in values:
        text = str(value or "").strip()
        if text:
            return text
    return fallback


def _music_destination_for_format(canonical: IngestBatch, audio_files: list[IngestFile], format_bucket: str) -> str:
    metadata = canonical.metadata_json or {}
    first_meta = audio_files[0].metadata_json or {} if audio_files else {}
    artist = _safe_path_part(
        _first_text(
            metadata.get("artist"),
            metadata.get("albumartist"),
            metadata.get("album_artist"),
            first_meta.get("artist"),
            first_meta.get("albumartist"),
            fallback="Unknown Artist",
        ),
        "Unknown Artist",
    )
    album = _safe_path_part(
        _first_text(
            metadata.get("album"),
            metadata.get("title"),
            first_meta.get("album"),
            fallback=Path(canonical.source_path or "").name or "Unknown Album",
        ),
        "Unknown Album",
    )
    year = _safe_path_part(year_value(metadata) or year_value(first_meta), "").strip()
    album_folder = f"{year} - {album}" if year else album
    root = settings.music_flac_dir if format_bucket == "FLAC" else settings.music_mp3_dir
    return str(Path(root) / artist / album_folder)


def _validate_music_destination(format_bucket: str, destination: str) -> None:
    normalized = destination.replace("\\", "/")
    expected = f"Music/Library/{format_bucket}"
    if expected not in normalized:
        raise DuplicateFragmentResolutionError("Destination does not match file format. Rebuild required before move.")


def _destination_sync_error(batch: IngestBatch, format_bucket: str) -> str | None:
    expected = f"Music/Library/{format_bucket}"
    metadata = batch.metadata_json or {}
    destinations = {
        "batch.suggested_destination": batch.suggested_destination,
        "metadata_json.suggested_destination": metadata.get("suggested_destination"),
        "suggested_metadata.suggested_destination": (batch.suggested_metadata or {}).get("suggested_destination"),
    }
    normalized_values = {
        key: str(value or "").replace("\\", "/")
        for key, value in destinations.items()
    }
    missing = [key for key, value in normalized_values.items() if not value]
    if missing:
        return f"Missing destination sync field(s): {', '.join(missing)}."
    unique_values = set(normalized_values.values())
    if len(unique_values) != 1:
        return "Canonical batch destination fields are not synchronized."
    destination = next(iter(unique_values))
    if expected not in destination:
        return "Destination does not match file format. Rebuild required before move."
    return None


def _destination_sync_problem(batch: IngestBatch) -> str | None:
    if not (batch.detected_type or "").startswith("music"):
        return None
    metadata = batch.metadata_json or {}
    audit = metadata.get("duplicate_fragment_resolution_audit") or []
    has_merge_audit = any(isinstance(item, dict) and item.get("action") == "merge_into_one_batch" for item in audit)
    if metadata.get("duplicate_fragment_review_state") != "reviewed_merged" and not has_merge_audit:
        return None
    format_bucket = str(metadata.get("format") or "").upper().strip()
    if format_bucket not in {"FLAC", "MP3"}:
        return None
    return _destination_sync_error(batch, format_bucket)

def batch_has_destination_sync_problem(batch: IngestBatch) -> bool:
    return _destination_sync_problem(batch) is not None


def _plan_music_merge_rebuild(canonical: IngestBatch, batches: list[IngestBatch]) -> tuple[str | None, str | None]:
    if not (canonical.detected_type or "").startswith("music"):
        return None, None
    audio_files = [ingest_file for batch in batches for ingest_file in (batch.files or []) if _is_music_audio_file(ingest_file)]
    if not audio_files:
        raise DuplicateFragmentResolutionError("Music merge requires attached scoped audio files.")
    raw_formats = {_music_file_format(ingest_file) for ingest_file in audio_files}
    if any(value is None for value in raw_formats):
        raise DuplicateFragmentResolutionError("Unsupported audio formats require format review before merge.")
    formats = sorted(str(value) for value in raw_formats)
    if len(formats) != 1:
        raise DuplicateFragmentResolutionError("Mixed audio formats require format review before merge.")
    format_bucket = formats[0]
    destination = _music_destination_for_format(canonical, audio_files, format_bucket)
    _validate_music_destination(format_bucket, destination)
    return format_bucket, destination


def _rebuild_canonical_metadata(
    canonical: IngestBatch,
    source_batches: list[IngestBatch],
    action: str,
    *,
    rebuilt_format: str | None = None,
    rebuilt_destination: str | None = None,
) -> None:
    files = sorted(canonical.files or [], key=lambda item: item.id)
    audio_files = [ingest_file for ingest_file in files if _is_music_audio_file(ingest_file)]
    metadata = dict(canonical.metadata_json or {})
    metadata["file_count"] = len(files)
    if (canonical.detected_type or "").startswith("music"):
        for ingest_file in audio_files:
            ingest_file.detected_role = "music_track"
        metadata["track_count"] = len(audio_files)
        tracks = []
        discs = set()
        for index, ingest_file in enumerate(audio_files, start=1):
            file_metadata = ingest_file.metadata_json or {}
            disc = str(file_metadata.get("discnumber") or file_metadata.get("disc_number") or "1").split("/")[0]
            discs.add(disc)
            tracks.append({
                "title": file_metadata.get("title") or Path(ingest_file.file_name).stem,
                "track_number": file_metadata.get("tracknumber") or file_metadata.get("track_number") or str(index),
                "disc_number": file_metadata.get("discnumber") or file_metadata.get("disc_number") or "1",
                "file_name": ingest_file.file_name,
                "file_id": ingest_file.id,
            })
        metadata["tracks"] = tracks
        metadata["disc_count"] = max(1, len(discs))
        if rebuilt_format is None or rebuilt_destination is None:
            rebuilt_format, rebuilt_destination = _plan_music_merge_rebuild(canonical, [canonical])
        destination_text = str(rebuilt_destination)
        metadata["format"] = rebuilt_format
        metadata["suggested_destination"] = destination_text
        canonical.suggested_destination = destination_text
        suggested = dict(canonical.suggested_metadata or {})
        suggested["format"] = rebuilt_format
        suggested["suggested_destination"] = destination_text
        canonical.suggested_metadata = suggested
        _validate_music_destination(rebuilt_format, destination_text)
    warnings = list(metadata.get("metadata_warnings") or [])
    warnings.append(f"duplicate_fragment_resolution_{action}")
    metadata["metadata_warnings"] = list(dict.fromkeys(warnings))
    metadata["merged_batch_ids"] = sorted({*(metadata.get("merged_batch_ids") or []), *[batch.id for batch in source_batches]})
    canonical.metadata_json = metadata
    sync_problem = _destination_sync_error(canonical, str(rebuilt_format))
    if sync_problem:
        raise DuplicateFragmentResolutionError(sync_problem)
    canonical.status = "pending_review"
    canonical.approved_at = None
    canonical.approved_by = None
    canonical.updated_at = now_utc()

def resolve_duplicate_fragment_group(
    db: Session,
    batch_id: int,
    action: str,
    *,
    canonical_batch_id: int | None = None,
    duplicate_batch_ids: list[int] | None = None,
    confirm_distinct_destinations: bool = False,
) -> dict[str, Any]:
    if action not in DUPLICATE_RESOLUTION_ACTIONS:
        raise DuplicateFragmentResolutionError("Unsupported duplicate/fragment resolution action.")
    review = build_duplicate_fragment_review(db, batch_id)
    clusters = review["clusters"]
    if not clusters:
        raise DuplicateFragmentResolutionError("No active duplicate/fragment group found for this batch.")
    cluster = clusters[0]
    if cluster.get("has_file_ownership_warnings"):
        raise DuplicateFragmentResolutionError("Cannot resolve this group until every batch has verified scoped files.")

    batches = _load_cluster_batches(db, cluster)
    if len(batches) < 2:
        raise DuplicateFragmentResolutionError("Duplicate/fragment resolution requires at least two batches.")

    canonical = _canonical_batch(batches, canonical_batch_id)
    collapsed_ids: list[int] = []
    blocked_ids: list[int] = []
    message = "Resolution recorded."

    if action == "keep_separate":
        destinations = [_normalized_destination(batch.suggested_destination) for batch in batches]
        duplicate_destinations = [dest for dest, count in Counter(destinations).items() if dest and count > 1]
        if duplicate_destinations or not confirm_distinct_destinations:
            raise DuplicateFragmentResolutionError("Keep separate requires distinct destination previews before resolution.")
        record = _resolution_record(action, cluster, resolution_state="reviewed_keep_separate")
        for batch in batches:
            _append_resolution_audit(batch, record)
            batch.status = "pending_review"
        message = "Group marked as separate reviewed batches."

    elif action == "merge_into_one_batch":
        rebuilt_format, rebuilt_destination = _plan_music_merge_rebuild(canonical, batches)
        source_batches = [batch for batch in batches if batch.id != canonical.id]
        collapsed_ids = [batch.id for batch in source_batches]
        record = _resolution_record(
            action,
            cluster,
            resolution_state="reviewed_merged",
            canonical_batch_id=canonical.id,
            collapsed_batch_ids=collapsed_ids,
        )
        for source in source_batches:
            for ingest_file in list(source.files or []):
                ingest_file.batch_id = canonical.id
            source_metadata = dict(source.metadata_json or {})
            source_metadata["merged_into_batch_id"] = canonical.id
            source_metadata["collapsed_by_duplicate_fragment_resolution"] = True
            source.metadata_json = source_metadata
            source.status = "merged"
            _append_resolution_audit(source, record)
        db.flush()
        db.refresh(canonical)
        _rebuild_canonical_metadata(
            canonical,
            source_batches,
            action,
            rebuilt_format=rebuilt_format,
            rebuilt_destination=rebuilt_destination,
        )
        _append_resolution_audit(canonical, record)
        message = f"Merged {len(source_batches)} fragment batch(es) into batch {canonical.id}."

    elif action == "mark_duplicate":
        duplicate_ids = set(duplicate_batch_ids or [batch.id for batch in batches if batch.id != canonical.id])
        if canonical.id in duplicate_ids:
            raise DuplicateFragmentResolutionError("Canonical batch cannot be marked duplicate.")
        record = _resolution_record(
            action,
            cluster,
            resolution_state="reviewed_duplicate",
            canonical_batch_id=canonical.id,
            duplicate_batch_ids=sorted(duplicate_ids),
        )
        canonical_record = {**record, "resolution_state": "reviewed_keep_separate"}
        _append_resolution_audit(canonical, canonical_record)
        for batch in batches:
            if batch.id not in duplicate_ids:
                continue
            metadata = dict(batch.metadata_json or {})
            metadata["blocked_from_move"] = True
            metadata["duplicate_of_batch_id"] = canonical.id
            batch.metadata_json = metadata
            batch.status = "duplicate_review"
            _append_resolution_audit(batch, record)
            blocked_ids.append(batch.id)
        message = f"Marked {len(blocked_ids)} duplicate batch(es) as blocked from move."

    elif action in {"review_later", "block_move"}:
        state = "reviewed_later" if action == "review_later" else "reviewed_blocked"
        record = _resolution_record(action, cluster, resolution_state=state)
        for batch in batches:
            metadata = dict(batch.metadata_json or {})
            metadata["blocked_from_move"] = True
            batch.metadata_json = metadata
            batch.status = "needs_metadata_review"
            _append_resolution_audit(batch, record)
            blocked_ids.append(batch.id)
        message = "Group remains blocked from move approval."

    db.commit()
    return {
        "cluster_id": cluster["cluster_id"],
        "action": action,
        "canonical_batch_id": canonical.id if action in {"merge_into_one_batch", "mark_duplicate"} else None,
        "resolved_batch_ids": [batch.id for batch in batches],
        "collapsed_batch_ids": collapsed_ids,
        "blocked_batch_ids": blocked_ids,
        "message": message,
    }
