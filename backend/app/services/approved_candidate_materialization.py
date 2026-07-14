from __future__ import annotations

from pathlib import Path
from typing import Any

from sqlalchemy import or_
from sqlalchemy.orm import Session, selectinload

from app.core.config import settings
from app.core.time import now_utc
from app.models.archive import IngestBatch, IngestFile
from app.models.media_metadata import CandidateMember, MediaIdentityCandidate, UniversalIngestionReviewAction
from app.services.batch_split import (
    _album_from_candidate_and_files,
    _build_album_batch_metadata,
    _library_album_destination,
    _partition_child_files,
    _suggested_metadata as _music_suggested_metadata,
)
from app.services.audiobook_metadata import (
    audiobook_destination,
    build_audiobook_file_metadata,
    build_audiobook_metadata,
)
from app.services.book_metadata import build_book_item_destination
from app.services.destination_authority import rebuild_music_batch_destination_from_attached_files
from app.services.metadata_candidates import METADATA_ASSIST_VERSION
from app.services.parent_candidate_materialization import (
    PARENT_CONTAINER_DRAINED,
    PARENT_REVIEW_IN_PROGRESS,
    PARENT_SPLIT_COMPLETE,
    build_parent_candidate_summary,
    get_parent_file_inventory,
    get_child_batch_count,
    get_parent_container_display_state,
)
from app.services.review_state import build_review_state
from app.services.title_display import clean_display_title, destination_title

CLOSED_PARENT_STATUSES = {"moved", "move_failed", "merged"}
GENERIC_AUDIO_EXTENSIONS = {".mp3", ".flac", ".m4a", ".aac", ".wav", ".ogg", ".opus", ".wma", ".aiff", ".alac"}
BOOK_EXTENSIONS = {".epub", ".pdf", ".mobi", ".azw", ".azw3"}
ARTWORK_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}


class MaterializationError(ValueError):
    pass


def _active_candidate_decisions(db: Session, batch_id: int, candidate_ids: set[int] | None = None) -> dict[int, str]:
    decisions: dict[int, str] = {}
    actions = (
        db.query(UniversalIngestionReviewAction)
        .filter(
            UniversalIngestionReviewAction.batch_id == batch_id,
            UniversalIngestionReviewAction.candidate_id.isnot(None),
            UniversalIngestionReviewAction.action_type.in_({"approve_candidate", "exclude_from_move_plan", "mark_review_later", "block_candidate"}),
            UniversalIngestionReviewAction.decision_status != "cleared",
        )
        .order_by(
            UniversalIngestionReviewAction.created_at.asc(),
            UniversalIngestionReviewAction.id.asc(),
        )
        .all()
    )
    for action in actions:
        candidate_id = int(action.candidate_id)
        if candidate_ids is not None and candidate_id not in candidate_ids:
            continue
        decisions[candidate_id] = action.action_type
    return decisions


def _history_entries(metadata: dict[str, Any]) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    for key in ("split_history", "materialization_history"):
        value = metadata.get(key)
        if isinstance(value, list):
            entries.extend(item for item in value if isinstance(item, dict))
    return entries


def _existing_child_batch_id(db: Session, parent_batch: IngestBatch, candidate_id: int) -> int | None:
    metadata = parent_batch.metadata_json or {}
    for entry in _history_entries(metadata):
        if int(entry.get("candidate_id") or 0) != candidate_id:
            continue
        child_id = int(entry.get("child_batch_id") or 0)
        if child_id and db.get(IngestBatch, child_id) is not None:
            return child_id
    return None


def _candidate_detected_type(candidate: MediaIdentityCandidate, target_media_class: str | None = None) -> str:
    value = (target_media_class or candidate.candidate_media_type or "unknown").casefold()
    if "music" in value or "audio_track" in value or "discography_track" in value:
        return "music_album"
    if "audiobook" in value or value == "audio":
        return "audiobook"
    if "comic" in value:
        return "book"
    if "book" in value or "ebook" in value:
        return "book"
    if "movie" in value:
        return "video_movie"
    if "tv" in value or "show" in value:
        return "video_tv_show"
    if "art" in value:
        return "unknown_type"
    return "unknown_type"


def _active_media_class_override(db: Session, candidate: MediaIdentityCandidate) -> str | None:
    row = (
        db.query(UniversalIngestionReviewAction.target_media_class)
        .filter(
            UniversalIngestionReviewAction.batch_id == candidate.batch_id,
            UniversalIngestionReviewAction.candidate_id == candidate.id,
            UniversalIngestionReviewAction.action_type == "override_media_class",
            UniversalIngestionReviewAction.decision_status != "cleared",
        )
        .order_by(
            UniversalIngestionReviewAction.updated_at.desc(),
            UniversalIngestionReviewAction.id.desc(),
        )
        .first()
    )
    return str(row[0]) if row and row[0] else None


def _candidate_source_folder(candidate: MediaIdentityCandidate, files: list[IngestFile]) -> str:
    evidence = candidate.identity_evidence_json or {}
    for key in ("source_folder", "folder", "source"):
        value = evidence.get(key)
        if value:
            return str(value).strip()
    if files:
        path = Path(files[0].file_path or files[0].file_name or "")
        parent = path.parent.name
        if parent:
            return parent
    return str(candidate.candidate_key or candidate.id)


def _is_generic_audio_file(file: IngestFile) -> bool:
    role = str(file.detected_role or "").casefold()
    ext = str(file.extension or Path(file.file_name or "").suffix).casefold()
    return ext in GENERIC_AUDIO_EXTENSIONS or role in {"audio", "audio_track", "music_audio", "music_track", "discography_track"}


def _is_unknown_identity(value: Any) -> bool:
    return str(value or "").strip().casefold() in {
        "",
        "unknown",
        "unknown artist",
        "unknown author",
        "unknown creator",
        "unknown title",
        "unkn",
    }


def _latest_identity_override(
    db: Session,
    candidate: MediaIdentityCandidate,
) -> UniversalIngestionReviewAction | None:
    return (
        db.query(UniversalIngestionReviewAction)
        .filter(
            UniversalIngestionReviewAction.batch_id == candidate.batch_id,
            UniversalIngestionReviewAction.candidate_id == candidate.id,
            UniversalIngestionReviewAction.action_type == "override_identity",
            UniversalIngestionReviewAction.decision_status != "cleared",
        )
        .order_by(
            UniversalIngestionReviewAction.updated_at.desc(),
            UniversalIngestionReviewAction.id.desc(),
        )
        .first()
    )


def _common_scoped_source(paths: list[Path]) -> Path:
    source = paths[0].resolve().parent
    parents = [path.resolve().parent for path in paths[1:]]
    while parents and any(not parent.is_relative_to(source) for parent in parents):
        if source.parent == source:
            break
        source = source.parent
    return source


def _audiobook_child_state(
    db: Session,
    parent_batch: IngestBatch,
    files: list[IngestFile],
    *,
    candidate: MediaIdentityCandidate | None = None,
    existing_metadata: dict[str, Any] | None = None,
    refresh_file_metadata: bool = False,
) -> tuple[dict[str, Any], dict[str, Any], str] | None:
    parts = _partition_child_files(files)
    audio_rows = list(parts["audio"])
    if not audio_rows:
        return None

    def paths_for(rows: list[IngestFile]) -> list[Path]:
        return [Path(ingest_file.file_path) for ingest_file in rows]

    audio_paths = paths_for(audio_rows)
    artwork_paths = paths_for(parts["artwork"])
    sidecar_paths = paths_for(parts["sidecars"])
    other_paths = paths_for(parts["other"])
    source = _common_scoped_source(audio_paths)
    rebuilt = build_audiobook_metadata(
        source,
        settings.audiobooks_dir,
        scoped_files={
            "audio": audio_paths,
            "artwork": artwork_paths,
            "sidecars": sidecar_paths,
            "other": other_paths,
        },
    )
    metadata = {
        **dict(existing_metadata or {}),
        **rebuilt,
    }

    identity_override = (
        _latest_identity_override(db, candidate)
        if candidate is not None
        else None
    )
    if identity_override and identity_override.override_primary_creator:
        metadata["author"] = identity_override.override_primary_creator
    elif _is_unknown_identity(metadata.get("author")) and candidate is not None:
        if not _is_unknown_identity(candidate.candidate_primary_creator):
            metadata["author"] = candidate.candidate_primary_creator
    if identity_override and identity_override.override_title:
        metadata["title"] = identity_override.override_title
    elif existing_metadata and not _is_unknown_identity(
        existing_metadata.get("title")
    ):
        metadata["title"] = existing_metadata["title"]
    elif candidate is not None and not _is_unknown_identity(
        candidate.candidate_title
    ):
        metadata["title"] = candidate.candidate_title
    if identity_override and identity_override.override_year:
        metadata["year"] = identity_override.override_year
    elif not metadata.get("year") and candidate is not None:
        metadata["year"] = candidate.candidate_year
    if identity_override and identity_override.override_series:
        metadata["series"] = identity_override.override_series
    elif not metadata.get("series") and candidate is not None:
        metadata["series"] = candidate.candidate_series
    if identity_override and identity_override.override_series_index:
        metadata["series_index"] = identity_override.override_series_index
    elif not metadata.get("series_index") and candidate is not None:
        metadata["series_index"] = candidate.candidate_series_index

    author = str(metadata.get("author") or "Unknown Author").strip()
    title = str(metadata.get("title") or "Unknown Title").strip()
    year = str(metadata.get("year") or "").strip() or None
    warnings = [
        warning
        for warning in list(metadata.get("metadata_warnings") or [])
        if warning not in {
            "audiobook_author_missing",
            "audiobook_title_missing",
            "audiobook_year_missing",
        }
    ]
    if _is_unknown_identity(author):
        warnings.append("audiobook_author_missing")
    if _is_unknown_identity(title):
        warnings.append("audiobook_title_missing")
    if not year:
        warnings.append("audiobook_year_missing")
    destination = audiobook_destination(
        audiobooks_root=settings.audiobooks_dir,
        author=author,
        title=title,
        year=year,
    )
    metadata.update({
        "author": author,
        "title": title,
        "year": year,
        "file_count": len(files),
        "audiobook_file_count": len(audio_rows),
        "source_parent_batch_id": parent_batch.id,
        "source_parent_path": parent_batch.source_path,
        "source_candidate_id": (
            candidate.id
            if candidate is not None
            else metadata.get("source_candidate_id")
        ),
        "candidate_key": (
            candidate.candidate_key
            if candidate is not None
            else metadata.get("candidate_key")
        ),
        "review_origin": "approved_candidate_materialization",
        "metadata_warnings": list(dict.fromkeys(warnings)),
        "suggested_destination_preview": str(destination),
    })
    metadata = build_review_state("audiobook", metadata)
    suggested_metadata = {
        "metadata_assist_version": metadata.get(
            "metadata_assist_version",
            METADATA_ASSIST_VERSION,
        ),
        "author": author,
        "title": title,
        "year": year,
        "narrator": metadata.get("narrator"),
        "series": metadata.get("series"),
        "series_index": metadata.get("series_index"),
        "format": metadata.get("format"),
        "sources": {
            "author": "scoped embedded audio tags",
            "title": "scoped embedded audio tags",
            "year": "scoped embedded audio tags or source folder",
        },
    }

    if refresh_file_metadata:
        for ingest_file in audio_rows:
            path = Path(ingest_file.file_path)
            if path.is_file():
                refreshed = build_audiobook_file_metadata(path)
                ingest_file.metadata_json = {
                    **dict(ingest_file.metadata_json or {}),
                    **refreshed,
                }
            ingest_file.detected_role = "audiobook_audio"
        for ingest_file in parts["artwork"]:
            ingest_file.detected_role = "audiobook_artwork"
        for ingest_file in parts["sidecars"]:
            ingest_file.detected_role = "audiobook_sidecar"
    return metadata, suggested_metadata, str(destination)


def _normalized_source_name(value: Any) -> str:
    if value is None:
        return ""
    return Path(str(value).replace("\\", "/")).name.casefold()


def _parent_book_item(
    parent_batch: IngestBatch,
    files: list[IngestFile],
) -> dict[str, Any] | None:
    parent_metadata = (
        parent_batch.metadata_json
        if isinstance(parent_batch.metadata_json, dict)
        else {}
    )
    book_items = parent_metadata.get("book_items")
    if not isinstance(book_items, list):
        return None
    file_names = {
        name
        for ingest_file in files
        for name in (
            _normalized_source_name(ingest_file.file_name),
            _normalized_source_name(ingest_file.file_path),
        )
        if name
    }
    for item in book_items:
        if not isinstance(item, dict) or not item.get("include", True):
            continue
        source_names = {
            _normalized_source_name(item.get("source_file")),
            _normalized_source_name(item.get("source_key")),
        }
        if file_names.intersection(source_names):
            return item
    return None


def _book_child_state(
    parent_batch: IngestBatch,
    files: list[IngestFile],
    *,
    candidate: MediaIdentityCandidate | None = None,
    existing_metadata: dict[str, Any] | None = None,
) -> tuple[dict[str, Any], dict[str, Any], str] | None:
    item = _parent_book_item(parent_batch, files)
    if item is None:
        return None

    metadata = dict(existing_metadata or {})
    primary_files = [
        ingest_file
        for ingest_file in files
        if str(
            ingest_file.extension or Path(ingest_file.file_name).suffix
        ).casefold() in BOOK_EXTENSIONS
    ]
    artwork_files = [
        ingest_file
        for ingest_file in files
        if str(
            ingest_file.extension or Path(ingest_file.file_name).suffix
        ).casefold() in ARTWORK_EXTENSIONS
    ]
    title = str(
        item.get("title")
        or (candidate.candidate_title if candidate else None)
        or metadata.get("title")
        or "Unknown Title"
    ).strip()
    author = str(
        item.get("author")
        or (candidate.candidate_primary_creator if candidate else None)
        or metadata.get("author")
        or "Unknown Author"
    ).strip()
    year = item.get("year")
    if year is None and candidate is not None:
        year = candidate.candidate_year
    if year is None:
        year = metadata.get("year")
    year = str(year).strip() if year else None
    book_format = str(
        item.get("format")
        or item.get("book_format")
        or (primary_files[0].extension.lstrip(".") if primary_files else None)
        or metadata.get("format")
        or "EPUB"
    ).upper()
    parent_metadata = (
        parent_batch.metadata_json
        if isinstance(parent_batch.metadata_json, dict)
        else {}
    )
    destination = build_book_item_destination(
        books_root=settings.books_dir,
        item={
            **item,
            "title": title,
            "author": author,
            "year": year,
            "format": book_format,
        },
        collection_title=parent_metadata.get("collection_title"),
        keep_collection_together=bool(
            parent_metadata.get("keep_collection_together")
        ),
    )
    primary_name = (
        str(item.get("source_file") or "").strip()
        or (primary_files[0].file_name if primary_files else files[0].file_name)
    )
    warnings: list[str] = []
    if author.casefold() in {
        "",
        "unknown",
        "unknown author",
        "unknown creator",
        "unkn",
    }:
        warnings.append("book_author_missing")
    if title.casefold() in {"", "unknown title"}:
        warnings.append("book_title_missing")
    if not year:
        warnings.append("book_year_missing")

    metadata.update({
        "media_kind": "book",
        "metadata_assist_version": str(
            item.get("metadata_assist_version") or METADATA_ASSIST_VERSION
        ),
        "review_type": "book",
        "review_mode": "single_item",
        "author": author,
        "title": title,
        "metadata_title": title,
        "display_title": str(
            item.get("display_title") or clean_display_title(title)
        ),
        "destination_title": str(
            item.get("destination_title") or destination_title(title)
        ),
        "year": year,
        "series": item.get("series"),
        "series_index": item.get("series_index"),
        "format": book_format,
        "book_format": book_format,
        "book_file_count": len(primary_files),
        "book_files": [ingest_file.file_name for ingest_file in primary_files],
        "primary_book_file": primary_name,
        "file_count": len(files),
        "files": [ingest_file.file_name for ingest_file in files],
        "artwork_count": len(artwork_files),
        "artwork_files": [ingest_file.file_name for ingest_file in artwork_files],
        "matched_artwork": item.get("matched_artwork"),
        "alternate_formats": list(item.get("alternate_formats") or []),
        "metadata_candidates": dict(item.get("metadata_candidates") or {}),
        "candidate_notes": list(item.get("candidate_notes") or []),
        "candidate_runtime": dict(item.get("candidate_runtime") or {}),
        "accepted_unknown_author": bool(item.get("accepted_unknown_author")),
        "accepted_unknown_year": bool(item.get("accepted_unknown_year")),
        "lookup_later": bool(item.get("lookup_later")),
        "suggested_destination_preview": str(destination),
        "metadata_quality": (
            "weak"
            if {"book_author_missing", "book_title_missing"}.intersection(warnings)
            else "good"
        ),
        "metadata_warnings": warnings,
        "confidence": max(
            float(item.get("confidence") or 0.0),
            float(candidate.candidate_confidence or 0.0) if candidate else 0.0,
            0.9,
        ),
        "source_parent_batch_id": parent_batch.id,
        "source_parent_path": parent_batch.source_path,
        "source_candidate_id": (
            candidate.id
            if candidate is not None
            else metadata.get("source_candidate_id")
        ),
        "candidate_key": (
            candidate.candidate_key
            if candidate is not None
            else metadata.get("candidate_key")
        ),
        "review_origin": "approved_candidate_materialization",
    })
    metadata = build_review_state("book", metadata)
    suggested_metadata = {
        "metadata_assist_version": metadata["metadata_assist_version"],
        "author": author,
        "title": title,
        "year": year,
        "series": item.get("series"),
        "series_index": item.get("series_index"),
        "format": book_format,
        "sources": {
            field: "reviewed parent book item"
            for field in (
                "author",
                "title",
                "year",
                "series",
                "series_index",
                "format",
            )
        },
    }
    return metadata, suggested_metadata, str(destination)


def _candidate_metadata(candidate: MediaIdentityCandidate, files: list[IngestFile], parent_batch: IngestBatch, detected_type: str | None = None) -> dict[str, Any]:
    detected_type = detected_type or _candidate_detected_type(candidate)
    title = candidate.candidate_title or "Unknown Title"
    creator = candidate.candidate_primary_creator or "Unknown Creator"
    metadata: dict[str, Any] = {
        "metadata_assist_version": "parent_candidate_materialization_v1",
        "source_parent_batch_id": parent_batch.id,
        "source_parent_path": parent_batch.source_path,
        "source_candidate_id": candidate.id,
        "candidate_key": candidate.candidate_key,
        "file_count": len(files),
        "files": [file.file_name for file in files],
        "year": candidate.candidate_year,
        "metadata_quality": "fair",
        "metadata_warnings": [],
    }
    if detected_type == "music_album":
        audio_files = [file for file in files if _is_generic_audio_file(file)]
        metadata.update({
            "artist": creator,
            "albumartist": creator,
            "album": title,
            "title": title,
            "type": "music_album",
            "review_type": "music_album",
            "track_count": len(audio_files),
            "audio_files": [file.file_name for file in audio_files],
        })
    elif detected_type == "audiobook":
        metadata.update({
            "author": creator,
            "title": title,
            "audiobook_file_count": len(files),
            "audio_files": [file.file_name for file in files],
        })
    elif detected_type == "video_movie":
        metadata.update({
            "title": title,
            "video_file_count": len(files),
            "video_files": [file.file_name for file in files],
        })
    elif detected_type == "video_tv_show":
        metadata.update({
            "show_title": title,
            "video_file_count": len(files),
            "video_files": [file.file_name for file in files],
        })
    else:
        metadata.update({
            "title": title,
            "author": creator,
            "book_file_count": len(files),
            "book_files": [file.file_name for file in files],
        })
    return metadata


def _suggested_metadata(candidate: MediaIdentityCandidate, detected_type: str) -> dict[str, Any]:
    title = candidate.candidate_title or "Unknown Title"
    creator = candidate.candidate_primary_creator or "Unknown Creator"
    if detected_type == "music_album":
        return {"artist": creator, "album": title, "year": candidate.candidate_year}
    if detected_type == "audiobook":
        return {"author": creator, "title": title, "year": candidate.candidate_year}
    if detected_type == "video_movie":
        return {"title": title, "year": candidate.candidate_year}
    if detected_type == "video_tv_show":
        return {"show_title": title, "year": candidate.candidate_year}
    return {"title": title, "author": creator, "year": candidate.candidate_year}


def _append_materialization_history(parent_batch: IngestBatch, candidate: MediaIdentityCandidate, child_batch: IngestBatch, file_count: int) -> None:
    metadata = dict(parent_batch.metadata_json or {})
    history = metadata.get("materialization_history")
    if not isinstance(history, list):
        history = []
    if not any(int(item.get("candidate_id") or 0) == candidate.id for item in history if isinstance(item, dict)):
        history.append({
            "candidate_id": candidate.id,
            "child_batch_id": child_batch.id,
            "title": candidate.candidate_title,
            "creator": candidate.candidate_primary_creator,
            "file_count": file_count,
            "materialized_at": now_utc().isoformat(),
        })
    metadata["materialization_history"] = history
    parent_batch.metadata_json = metadata


def _mark_candidate_materialized(db: Session, batch_id: int, candidate_id: int) -> None:
    timestamp = now_utc()
    actions = db.query(UniversalIngestionReviewAction).filter(
        UniversalIngestionReviewAction.batch_id == batch_id,
        UniversalIngestionReviewAction.candidate_id == candidate_id,
        UniversalIngestionReviewAction.action_type.in_({"approve_candidate", "split_candidate"}),
        UniversalIngestionReviewAction.decision_status != "cleared",
    ).all()
    for action in actions:
        action.decision_status = "applied"
        action.applied_at = action.applied_at or timestamp
        action.updated_at = timestamp


def _candidate_member_file_ids(db: Session, candidate_id: int) -> list[int]:
    ids = [
        int(file_id)
        for (file_id,) in db.query(CandidateMember.batch_file_id)
        .filter(CandidateMember.candidate_id == candidate_id, CandidateMember.batch_file_id.isnot(None))
        .all()
    ]
    return list(dict.fromkeys(ids))


def _candidate_primary_file_ids(db: Session, candidate_id: int) -> set[int]:
    return {
        int(file_id)
        for (file_id,) in (
            db.query(CandidateMember.batch_file_id)
            .filter(
                CandidateMember.candidate_id == candidate_id,
                CandidateMember.batch_file_id.isnot(None),
                or_(
                    CandidateMember.role_in_candidate.is_(None),
                    CandidateMember.role_in_candidate != "support",
                ),
            )
            .all()
        )
    }

def _existing_child_from_candidate_files(db: Session, candidate: MediaIdentityCandidate, file_ids: list[int], parent_batch_id: int) -> int | None:
    if not file_ids:
        return None
    files = db.query(IngestFile).filter(IngestFile.id.in_(file_ids)).all()
    child_ids = {file.batch_id for file in files if file.batch_id and file.batch_id != parent_batch_id}
    for child_id in child_ids:
        child = db.get(IngestBatch, child_id)
        metadata = child.metadata_json if child else None
        if isinstance(metadata, dict) and int(metadata.get("source_candidate_id") or 0) == candidate.id:
            return child_id
    return None


def _candidate_parent_files(db: Session, parent_batch: IngestBatch, candidate: MediaIdentityCandidate) -> list[IngestFile]:
    file_ids = _candidate_member_file_ids(db, candidate.id)
    if not file_ids:
        raise MaterializationError("Candidate has no scoped files available for materialization.")
    existing_child_id = _existing_child_from_candidate_files(db, candidate, file_ids, parent_batch.id)
    if existing_child_id is not None:
        return []
    files = db.query(IngestFile).filter(
        IngestFile.id.in_(file_ids),
        IngestFile.batch_id == parent_batch.id,
    ).all()
    if not files:
        raise MaterializationError("Candidate has no scoped files available for materialization.")
    primary_file_ids = _candidate_primary_file_ids(db, candidate.id)
    if not any(file.id in primary_file_ids for file in files):
        raise MaterializationError(
            "Candidate has only artwork, playlists, or sidecar files attached to the parent. "
            "Support files remain on the parent for later Cleaner handling."
        )
    return files


def _music_child_metadata(candidate: MediaIdentityCandidate, files: list[IngestFile], parent_batch: IngestBatch) -> dict[str, Any]:
    source_folder = _candidate_source_folder(candidate, files)
    album = _album_from_candidate_and_files(candidate, None, files, source_folder)
    metadata = _build_album_batch_metadata(
        album=album,
        parent_batch=parent_batch,
        files_to_move=files,
        source_folder=source_folder,
        candidate=candidate,
        identity_override=None,
    )
    metadata["metadata_assist_version"] = "parent_candidate_materialization_v1"
    metadata["source_parent_batch_id"] = parent_batch.id
    metadata["source_parent_path"] = parent_batch.source_path
    metadata["source_candidate_id"] = candidate.id
    metadata["candidate_key"] = candidate.candidate_key
    metadata["review_origin"] = "approved_candidate_materialization"
    return metadata


def _create_child_batch(db: Session, parent_batch: IngestBatch, candidate: MediaIdentityCandidate, files: list[IngestFile]) -> int:
    detected_type = _candidate_detected_type(candidate, _active_media_class_override(db, candidate))
    if detected_type == "music_album":
        if not _partition_child_files(files)["audio"]:
            raise MaterializationError(
                "Music child creation requires at least one attached audio file. "
                "Support files remain on the parent for later Cleaner handling."
            )
        metadata = _music_child_metadata(candidate, files, parent_batch)
        suggested_metadata = _music_suggested_metadata(metadata)
        suggested_destination = _library_album_destination(metadata)
    elif detected_type == "book":
        book_state = _book_child_state(
            parent_batch,
            files,
            candidate=candidate,
        )
        if book_state is not None:
            metadata, suggested_metadata, suggested_destination = book_state
        else:
            metadata = _candidate_metadata(
                candidate,
                files,
                parent_batch,
                detected_type,
            )
            suggested_metadata = _suggested_metadata(candidate, detected_type)
            suggested_destination = None
    elif detected_type == "audiobook":
        audiobook_state = _audiobook_child_state(
            db,
            parent_batch,
            files,
            candidate=candidate,
            refresh_file_metadata=True,
        )
        if audiobook_state is None:
            raise MaterializationError(
                "Audiobook child creation requires at least one attached audio file. "
                "Support files remain on the parent for later Cleaner handling."
            )
        metadata, suggested_metadata, suggested_destination = audiobook_state
    else:
        metadata = _candidate_metadata(candidate, files, parent_batch, detected_type)
        suggested_metadata = _suggested_metadata(candidate, detected_type)
        suggested_destination = None

    timestamp = now_utc()
    child_batch = IngestBatch(
        source_kind=parent_batch.source_kind,
        source_path=parent_batch.source_path,
        detected_type=detected_type,
        status="pending_review",
        confidence=max(parent_batch.confidence or 0.0, candidate.candidate_confidence or 0.0, 0.7),
        suggested_destination=suggested_destination,
        suggested_metadata=suggested_metadata,
        metadata_json=metadata,
        metadata_confirmed=False,
        created_at=timestamp,
        updated_at=timestamp,
    )
    db.add(child_batch)
    db.flush()
    for ingest_file in files:
        ingest_file.batch_id = child_batch.id
    child_batch.files = list(files)
    if detected_type == "music_album":
        rebuild_music_batch_destination_from_attached_files(child_batch, db)
    elif detected_type == "audiobook":
        for ingest_file in files:
            if _is_generic_audio_file(ingest_file):
                ingest_file.detected_role = "audiobook_audio"
    _append_materialization_history(parent_batch, candidate, child_batch, len(files))
    _mark_candidate_materialized(db, parent_batch.id, candidate.id)
    parent_batch.updated_at = timestamp
    return child_batch.id


def repair_materialized_book_children(
    db: Session,
    *,
    parent_batch_id: int | None = None,
    apply: bool = False,
) -> dict[str, Any]:
    children = (
        db.query(IngestBatch)
        .options(selectinload(IngestBatch.files))
        .filter(
            IngestBatch.detected_type == "book",
            IngestBatch.status.in_({"pending_review", "needs_metadata_review"}),
        )
        .all()
    )
    parent_cache: dict[int, IngestBatch | None] = {}
    repairable_ids: list[int] = []
    repaired_ids: list[int] = []
    unmatched_ids: list[int] = []
    skipped_confirmed_ids: list[int] = []
    timestamp = now_utc()

    for child in children:
        existing = child.metadata_json if isinstance(child.metadata_json, dict) else {}
        source_parent_id = int(existing.get("source_parent_batch_id") or 0)
        if not source_parent_id:
            continue
        if parent_batch_id is not None and source_parent_id != parent_batch_id:
            continue
        if child.metadata_confirmed:
            skipped_confirmed_ids.append(child.id)
            continue
        if source_parent_id not in parent_cache:
            parent_cache[source_parent_id] = db.get(IngestBatch, source_parent_id)
        parent = parent_cache[source_parent_id]
        if parent is None:
            unmatched_ids.append(child.id)
            continue
        state = _book_child_state(
            parent,
            list(child.files),
            existing_metadata=existing,
        )
        if state is None:
            unmatched_ids.append(child.id)
            continue
        metadata, suggested_metadata, suggested_destination = state
        current_signature = (
            existing.get("title"),
            existing.get("author"),
            existing.get("year"),
            existing.get("format"),
            existing.get("primary_book_file"),
            child.suggested_destination,
            (child.suggested_metadata or {}).get("title"),
            (child.suggested_metadata or {}).get("author"),
        )
        desired_signature = (
            metadata.get("title"),
            metadata.get("author"),
            metadata.get("year"),
            metadata.get("format"),
            metadata.get("primary_book_file"),
            suggested_destination,
            suggested_metadata.get("title"),
            suggested_metadata.get("author"),
        )
        if current_signature == desired_signature:
            continue
        repairable_ids.append(child.id)
        if not apply:
            continue

        audit = list(existing.get("book_child_metadata_repair_audit") or [])
        audit.append({
            "repaired_at": timestamp.isoformat(),
            "source_parent_batch_id": source_parent_id,
            "source_file": metadata.get("primary_book_file"),
            "reason": "Restored reviewed parent book item metadata.",
        })
        metadata["book_child_metadata_repair_audit"] = audit
        child.metadata_json = metadata
        child.suggested_metadata = suggested_metadata
        child.suggested_destination = suggested_destination
        child.confidence = max(
            float(child.confidence or 0.0),
            float(metadata.get("confidence") or 0.0),
        )
        child.status = (
            "needs_metadata_review"
            if metadata.get("blocking_review_items")
            else "pending_review"
        )
        child.updated_at = timestamp
        repaired_ids.append(child.id)

    if apply:
        db.commit()
    return {
        "apply": apply,
        "repairable_child_batch_ids": repairable_ids,
        "repaired_child_batch_ids": repaired_ids,
        "unmatched_child_batch_ids": unmatched_ids,
        "skipped_confirmed_child_batch_ids": skipped_confirmed_ids,
        "repairable_count": len(repairable_ids),
        "repaired_count": len(repaired_ids),
    }


def repair_materialized_audiobook_children(
    db: Session,
    *,
    parent_batch_id: int | None = None,
    apply: bool = False,
) -> dict[str, Any]:
    children = (
        db.query(IngestBatch)
        .options(selectinload(IngestBatch.files))
        .filter(
            IngestBatch.detected_type == "audiobook",
            IngestBatch.status.in_({"pending_review", "needs_metadata_review"}),
        )
        .all()
    )
    parent_cache: dict[int, IngestBatch | None] = {}
    repairable_ids: list[int] = []
    repaired_ids: list[int] = []
    unmatched_ids: list[int] = []
    skipped_confirmed_ids: list[int] = []
    repair_previews: list[dict[str, Any]] = []
    timestamp = now_utc()

    for child in children:
        existing = child.metadata_json if isinstance(child.metadata_json, dict) else {}
        source_parent_id = int(existing.get("source_parent_batch_id") or 0)
        if not source_parent_id:
            continue
        if parent_batch_id is not None and source_parent_id != parent_batch_id:
            continue
        if child.metadata_confirmed:
            skipped_confirmed_ids.append(child.id)
            continue
        if source_parent_id not in parent_cache:
            parent_cache[source_parent_id] = db.get(IngestBatch, source_parent_id)
        parent = parent_cache[source_parent_id]
        if parent is None:
            unmatched_ids.append(child.id)
            continue

        source_candidate_id = int(existing.get("source_candidate_id") or 0)
        candidate = (
            db.get(MediaIdentityCandidate, source_candidate_id)
            if source_candidate_id
            else None
        )
        state = _audiobook_child_state(
            db,
            parent,
            list(child.files),
            candidate=candidate,
            existing_metadata=existing,
            refresh_file_metadata=False,
        )
        if state is None:
            unmatched_ids.append(child.id)
            continue
        metadata, suggested_metadata, suggested_destination = state
        current_suggested = (
            child.suggested_metadata
            if isinstance(child.suggested_metadata, dict)
            else {}
        )
        current_signature = (
            existing.get("author"),
            existing.get("title"),
            existing.get("year"),
            existing.get("format"),
            existing.get("audiobook_file_count"),
            child.suggested_destination,
            current_suggested.get("author"),
            current_suggested.get("title"),
        )
        desired_signature = (
            metadata.get("author"),
            metadata.get("title"),
            metadata.get("year"),
            metadata.get("format"),
            metadata.get("audiobook_file_count"),
            suggested_destination,
            suggested_metadata.get("author"),
            suggested_metadata.get("title"),
        )
        if current_signature == desired_signature:
            continue
        repairable_ids.append(child.id)
        repair_previews.append({
            "child_batch_id": child.id,
            "current": {
                "author": existing.get("author"),
                "title": existing.get("title"),
                "year": existing.get("year"),
                "narrator": existing.get("narrator"),
                "suggested_destination": child.suggested_destination,
            },
            "desired": {
                "author": metadata.get("author"),
                "title": metadata.get("title"),
                "year": metadata.get("year"),
                "narrator": metadata.get("narrator"),
                "suggested_destination": suggested_destination,
            },
        })
        if not apply:
            continue

        state = _audiobook_child_state(
            db,
            parent,
            list(child.files),
            candidate=candidate,
            existing_metadata=existing,
            refresh_file_metadata=True,
        )
        if state is None:
            unmatched_ids.append(child.id)
            continue
        metadata, suggested_metadata, suggested_destination = state
        audit = list(existing.get("audiobook_child_metadata_repair_audit") or [])
        audit.append({
            "repaired_at": timestamp.isoformat(),
            "source_parent_batch_id": source_parent_id,
            "source_candidate_id": source_candidate_id or None,
            "reason": "Rebuilt audiobook identity from attached scoped file tags.",
        })
        metadata["audiobook_child_metadata_repair_audit"] = audit
        child.metadata_json = metadata
        child.suggested_metadata = suggested_metadata
        child.suggested_destination = suggested_destination
        child.confidence = max(
            float(child.confidence or 0.0),
            float(metadata.get("confidence") or 0.0),
        )
        child.status = (
            "needs_metadata_review"
            if metadata.get("blocking_review_items")
            else "pending_review"
        )
        child.updated_at = timestamp
        repaired_ids.append(child.id)

    if apply:
        db.commit()
    return {
        "apply": apply,
        "repairable_child_batch_ids": repairable_ids,
        "repaired_child_batch_ids": repaired_ids,
        "unmatched_child_batch_ids": unmatched_ids,
        "skipped_confirmed_child_batch_ids": skipped_confirmed_ids,
        "repair_previews": repair_previews,
        "repairable_count": len(repairable_ids),
        "repaired_count": len(repaired_ids),
    }


def _materialize_candidate(db: Session, parent_batch: IngestBatch, candidate: MediaIdentityCandidate) -> tuple[int, bool]:
    existing_child_id = _existing_child_batch_id(db, parent_batch, candidate.id)
    if existing_child_id is not None:
        _mark_candidate_materialized(db, parent_batch.id, candidate.id)
        return existing_child_id, False

    file_ids = _candidate_member_file_ids(db, candidate.id)
    existing_from_files = _existing_child_from_candidate_files(db, candidate, file_ids, parent_batch.id)
    if existing_from_files is not None:
        _append_materialization_history(parent_batch, candidate, db.get(IngestBatch, existing_from_files), 0)
        _mark_candidate_materialized(db, parent_batch.id, candidate.id)
        return existing_from_files, False

    files = _candidate_parent_files(db, parent_batch, candidate)
    return _create_child_batch(db, parent_batch, candidate, files), True


def materialize_approved_candidates(db: Session, batch_id: int) -> dict[str, Any]:
    parent_batch = (
        db.query(IngestBatch)
        .options(selectinload(IngestBatch.files))
        .filter(IngestBatch.id == batch_id)
        .first()
    )
    if parent_batch is None:
        raise ValueError("Batch not found")
    if parent_batch.status in CLOSED_PARENT_STATUSES:
        raise ValueError("Moved or closed batches cannot be materialized")

    parent_summary = build_parent_candidate_summary(db, parent_batch)
    if not parent_summary["is_parent_review_container"]:
        raise ValueError("Batch is not a parent review container")
    current_candidates = {
        candidate.id: candidate
        for candidate in db.query(MediaIdentityCandidate)
        .filter(MediaIdentityCandidate.batch_id == batch_id)
        .all()
    }
    decisions = _active_candidate_decisions(db, batch_id, set(current_candidates))
    approved_candidate_ids = [candidate_id for candidate_id, action_type in decisions.items() if action_type == "approve_candidate"]
    if not approved_candidate_ids:
        raise ValueError("No approved current candidate groups are available to materialize. Approve safe candidate groups before creating child batches.")

    candidates = {
        candidate_id: current_candidates[candidate_id]
        for candidate_id in approved_candidate_ids
        if candidate_id in current_candidates
    }
    candidate_id_set = set(current_candidates)
    blocked_candidate_ids = sorted(candidate_id for candidate_id, action_type in decisions.items() if action_type == "block_candidate")
    excluded_candidate_ids = sorted(candidate_id for candidate_id, action_type in decisions.items() if action_type == "exclude_from_move_plan")
    review_later_candidate_ids = sorted(candidate_id for candidate_id, action_type in decisions.items() if action_type == "mark_review_later")
    decisioned_ids = set(approved_candidate_ids) | set(blocked_candidate_ids) | set(excluded_candidate_ids) | set(review_later_candidate_ids)
    unresolved_candidate_ids = sorted(candidate_id_set - decisioned_ids)

    child_batch_ids: list[int] = []
    materialized_candidate_ids: list[int] = []
    created_count = 0
    skipped_count = 0
    try:
        for candidate_id in approved_candidate_ids:
            candidate = candidates.get(candidate_id)
            if candidate is None:
                raise MaterializationError("Some approved candidates could not be materialized.")
            child_id, created = _materialize_candidate(db, parent_batch, candidate)
            child_batch_ids.append(child_id)
            materialized_candidate_ids.append(candidate_id)
            if created:
                created_count += 1
            else:
                skipped_count += 1

        timestamp = now_utc()
        metadata = dict(parent_batch.metadata_json or {})
        partial_audit = list(metadata.get("partial_materialization_audit") or [])
        partial_audit.append({
            "parent_batch_id": parent_batch.id,
            "materialized_candidate_ids": sorted(materialized_candidate_ids),
            "blocked_candidate_ids": blocked_candidate_ids,
            "excluded_candidate_ids": excluded_candidate_ids,
            "review_later_candidate_ids": review_later_candidate_ids,
            "unresolved_candidate_ids": unresolved_candidate_ids,
            "created_child_batch_ids": child_batch_ids,
            "materialized_at": timestamp.isoformat(),
        })
        metadata["partial_materialization_audit"] = partial_audit
        child_batch_count = get_child_batch_count(parent_batch, db)
        parent_file_inventory = get_parent_file_inventory(parent_batch, db)
        active_parent_file_count = parent_file_inventory["total"]
        parent_container_state = get_parent_container_display_state(parent_batch, db)
        metadata["child_candidate_count"] = len(candidate_id_set)
        metadata["materialized_child_count"] = child_batch_count
        metadata["blocked_candidate_count"] = len(blocked_candidate_ids)
        metadata["excluded_candidate_count"] = len(excluded_candidate_ids)
        metadata["review_later_candidate_count"] = len(review_later_candidate_ids)
        metadata["remaining_parent_file_count"] = active_parent_file_count
        metadata["active_parent_file_count"] = active_parent_file_count
        metadata["parent_container_state"] = parent_container_state
        metadata["parent_has_remaining_files"] = active_parent_file_count > 0
        metadata["parent_primary_file_count"] = parent_file_inventory["primary"]
        metadata["parent_support_file_count"] = parent_file_inventory["support"]
        metadata["parent_media_extraction_complete"] = parent_file_inventory["primary"] == 0
        metadata["parent_is_drained"] = parent_container_state == PARENT_CONTAINER_DRAINED
        metadata["unresolved_candidate_count"] = len(unresolved_candidate_ids)
        if active_parent_file_count > 0 and metadata["unresolved_candidate_count"] == 0:
            metadata["unresolved_candidate_count"] = 1
        parent_complete = child_batch_count > 0 and parent_file_inventory["primary"] == 0
        parent_batch.status = PARENT_SPLIT_COMPLETE if parent_complete else "pending_review"
        metadata["parent_review_state"] = PARENT_SPLIT_COMPLETE if parent_complete else PARENT_REVIEW_IN_PROGRESS
        parent_batch.metadata_json = metadata
        parent_batch.updated_at = timestamp
        db.commit()
    except Exception:
        db.rollback()
        raise

    db.refresh(parent_batch)
    parent_summary = build_parent_candidate_summary(db, parent_batch)
    parent_state = parent_summary["parent_review_state"]
    remaining_detail = parent_summary["unresolved_candidate_count"] + parent_summary["review_later_candidate_count"] + parent_summary["blocked_candidate_count"]
    message = (
        f"Created {created_count} child batch{'es' if created_count != 1 else ''}. {remaining_detail} candidate{'s' if remaining_detail != 1 else ''} remain on the parent."
        if created_count and parent_state != PARENT_SPLIT_COMPLETE
        else f"Created {created_count} child batch{'es' if created_count != 1 else ''}. Parent marked split complete."
        if created_count
        else f"Approved child batches already exist. {remaining_detail} candidate{'s' if remaining_detail != 1 else ''} remain on the parent."
        if parent_state != PARENT_SPLIT_COMPLETE
        else "Approved child batches already exist. Parent marked split complete."
    )
    return {
        "parent_batch_id": parent_batch.id,
        "created_child_batch_ids": child_batch_ids,
        "created_count": created_count,
        "skipped_count": skipped_count,
        "materialized_child_count": parent_summary["materialized_child_count"],
        "unresolved_candidate_count": parent_summary["unresolved_candidate_count"],
        "blocked_candidate_count": parent_summary["blocked_candidate_count"],
        "excluded_candidate_count": parent_summary["excluded_candidate_count"],
        "review_later_candidate_count": parent_summary["review_later_candidate_count"],
        "parent_review_state": parent_state,
        "message": message,
    }
