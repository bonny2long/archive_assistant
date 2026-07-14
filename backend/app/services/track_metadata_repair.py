from __future__ import annotations

from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session, selectinload

from app.core.time import now_utc
from app.models.archive import IngestBatch, IngestFile
from app.services.duplicate_fragment_review import music_track_completeness_for_batch
from app.services.music_metadata import (
    apply_track_number_conflict_warnings,
    normalize_track_title_for_destination,
    resolved_music_track_evidence,
)
from app.services.review_state import build_review_state


PENDING_MUSIC_STATUSES = {"pending_review", "needs_metadata_review", "metadata_recovery"}
MUSIC_AUDIO_EXTENSIONS = {
    ".aac", ".aiff", ".alac", ".flac", ".m4a", ".mp3",
    ".ogg", ".opus", ".wav", ".wma",
}
MUSIC_AUDIO_ROLES = {"audio", "audio_track", "music_audio", "music_track", "discography_track"}
STALE_TRACK_WARNINGS = {
    "partial_track_set",
    "track_number_conflict",
    "track_number_conflict_detected",
    "track_order_ambiguous",
}


def _is_music_audio_file(ingest_file: IngestFile) -> bool:
    extension = str(ingest_file.extension or Path(ingest_file.file_name or "").suffix).casefold()
    role = str(ingest_file.detected_role or "").casefold()
    return extension in MUSIC_AUDIO_EXTENSIONS or role in MUSIC_AUDIO_ROLES


def _track_title(ingest_file: IngestFile, resolved_track: int | None) -> str:
    metadata = ingest_file.metadata_json or {}
    raw_title = str(metadata.get("title") or Path(ingest_file.file_name or "").stem).strip()
    return normalize_track_title_for_destination(raw_title, resolved_track)


def rebuild_pending_music_track_metadata(batch: IngestBatch) -> dict[str, Any]:
    """Rebuild stored music track evidence from attached files without filesystem I/O."""
    if batch.detected_type != "music_album":
        raise ValueError("Track metadata repair only supports music album batches")
    if batch.status not in PENDING_MUSIC_STATUSES:
        raise ValueError("Track metadata repair only supports pending music batches")

    audio_files = [item for item in (batch.files or []) if _is_music_audio_file(item)]
    if not audio_files:
        raise ValueError("Music batch has no attached audio files")

    metadata = dict(batch.metadata_json or {})
    previous = {
        "track_count": metadata.get("track_count"),
        "disc_count": metadata.get("disc_count"),
        "completeness_status": metadata.get("completeness_status"),
        "missing_track_numbers": list(metadata.get("missing_track_numbers") or []),
        "duplicate_track_numbers": list(metadata.get("duplicate_track_numbers") or []),
    }
    metadata["metadata_warnings"] = [
        warning
        for warning in (metadata.get("metadata_warnings") or [])
        if str(warning).strip().casefold().replace(" ", "_") not in STALE_TRACK_WARNINGS
    ]
    metadata = apply_track_number_conflict_warnings(metadata, audio_files)
    conflict_summary = dict(metadata.get("track_number_conflicts") or {})

    track_rows: list[tuple[int, int, str, int, dict[str, Any]]] = []
    discs: set[int] = set()
    for ingest_file in audio_files:
        file_metadata = dict(ingest_file.metadata_json or {})
        evidence = resolved_music_track_evidence(file_metadata, ingest_file.file_name)
        resolved_track = evidence.get("resolved_track")
        disc = int(evidence.get("disc") or 1)
        discs.add(disc)
        track_rows.append((
            disc,
            int(resolved_track) if resolved_track is not None else 1_000_000,
            ingest_file.file_name.casefold(),
            int(ingest_file.id or 0),
            {
                "title": _track_title(ingest_file, resolved_track),
                "track_number": resolved_track,
                "disc_number": disc,
                "file_name": ingest_file.file_name,
                "file_id": ingest_file.id,
                "track_number_source": evidence.get("preferred_source"),
            },
        ))

    track_rows.sort(key=lambda row: row[:4])
    metadata["track_count"] = len(audio_files)
    metadata["disc_count"] = max(1, len(discs))
    metadata["tracks"] = [row[4] for row in track_rows]
    batch.metadata_json = metadata

    completeness = music_track_completeness_for_batch(batch)
    metadata["track_completeness"] = completeness
    metadata["present_track_numbers"] = completeness["present_track_numbers"]
    metadata["present_track_positions"] = completeness["present_track_positions"]
    metadata["missing_track_numbers"] = completeness["missing_track_numbers"]
    metadata["missing_track_positions"] = completeness["missing_track_positions"]
    metadata["duplicate_track_numbers"] = completeness["duplicate_track_numbers"]
    metadata["duplicate_track_positions"] = completeness["duplicate_track_positions"]
    metadata["track_number_conflicts"] = completeness["track_number_conflicts"]
    metadata["track_number_conflict_summary"] = conflict_summary
    metadata["completeness_status"] = completeness["completeness_status"]

    warnings = [
        warning
        for warning in (metadata.get("metadata_warnings") or [])
        if str(warning).strip().casefold().replace(" ", "_") not in STALE_TRACK_WARNINGS
    ]
    if conflict_summary.get("conflict_count", 0) > 0:
        warnings.append("track_number_conflict_detected")
    if conflict_summary.get("ambiguous_count", 0) > 0 and not conflict_summary.get("filename_preferred_count", 0):
        warnings.append("track_order_ambiguous")
    if completeness["missing_track_numbers"]:
        warnings.append("partial_track_set")
    metadata["metadata_warnings"] = list(dict.fromkeys(warnings))

    audit = list(metadata.get("track_metadata_repair_audit") or [])
    audit.append({
        "batch_id": batch.id,
        "repaired_at": now_utc().isoformat(),
        "repair_version": "AA-TRACK2.1",
        "attached_audio_file_count": len(audio_files),
        "previous": previous,
        "result": {
            "track_count": metadata["track_count"],
            "disc_count": metadata["disc_count"],
            "completeness_status": metadata["completeness_status"],
            "missing_track_numbers": metadata["missing_track_numbers"],
            "duplicate_track_numbers": metadata["duplicate_track_numbers"],
        },
    })
    metadata["track_metadata_repair_audit"] = audit
    batch.metadata_json = build_review_state("music_album", metadata)
    batch.updated_at = now_utc()
    return {
        "batch_id": batch.id,
        "track_count": metadata["track_count"],
        "disc_count": metadata["disc_count"],
        "present_track_numbers": completeness["present_track_numbers"],
        "present_track_positions": completeness["present_track_positions"],
        "missing_track_numbers": completeness["missing_track_numbers"],
        "missing_track_positions": completeness["missing_track_positions"],
        "duplicate_track_numbers": completeness["duplicate_track_numbers"],
        "duplicate_track_positions": completeness["duplicate_track_positions"],
        "track_number_conflicts": completeness["track_number_conflicts"],
        "completeness_status": completeness["completeness_status"],
    }


def repair_pending_music_batch_track_metadata(
    db: Session,
    batch_id: int,
    *,
    commit: bool = True,
) -> dict[str, Any]:
    batch = (
        db.query(IngestBatch)
        .options(selectinload(IngestBatch.files))
        .filter(IngestBatch.id == batch_id)
        .first()
    )
    if batch is None:
        raise ValueError("Batch not found")
    result = rebuild_pending_music_track_metadata(batch)
    if commit:
        db.commit()
        db.refresh(batch)
    else:
        db.flush()
    return result


def repair_all_pending_music_track_metadata(
    db: Session,
    *,
    commit: bool = True,
) -> list[dict[str, Any]]:
    batches = (
        db.query(IngestBatch)
        .options(selectinload(IngestBatch.files))
        .filter(
            IngestBatch.detected_type == "music_album",
            IngestBatch.status.in_(PENDING_MUSIC_STATUSES),
        )
        .order_by(IngestBatch.id)
        .all()
    )
    results = [
        rebuild_pending_music_track_metadata(batch)
        for batch in batches
        if any(_is_music_audio_file(item) for item in (batch.files or []))
    ]
    if commit:
        db.commit()
    else:
        db.flush()
    return results
