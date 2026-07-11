from __future__ import annotations

from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.time import now_utc
from app.models.archive import IngestBatch, IngestFile
from app.models.media_metadata import CandidateMember, MediaIdentityCandidate
from app.services.audiobook_metadata import audiobook_destination
from app.services.destination_authority import rebuild_music_batch_destination_from_attached_files
from app.services.review_state import build_review_state


AUDIO_EXTENSIONS = {
    ".aac", ".aiff", ".alac", ".flac", ".m4a", ".m4b", ".mp3",
    ".ogg", ".opus", ".wav", ".wma",
}
SUPPORT_ROLES = {"artwork", "cover_art", "album_artwork", "sidecar", "metadata_sidecar", "playlist"}


def _audio_files(batch: IngestBatch) -> list[IngestFile]:
    return [
        item
        for item in batch.files
        if str(item.extension or Path(item.file_name).suffix).casefold() in AUDIO_EXTENSIONS
    ]


def _audio_format(files: list[IngestFile]) -> str:
    formats = {
        str(item.extension or Path(item.file_name).suffix).lstrip(".").upper()
        for item in files
    }
    if len(formats) == 1:
        value = next(iter(formats))
        return "M4B" if value == "M4B" else "FLAC" if value == "FLAC" else "MP3" if value == "MP3" else value
    return "MIXED"


def _candidate_covers_batch_audio(db: Session, batch: IngestBatch, candidate_id: int) -> bool:
    candidate_ids = [
        row[0]
        for row in db.query(MediaIdentityCandidate.id)
        .filter(MediaIdentityCandidate.batch_id == batch.id)
        .all()
    ]
    if candidate_ids != [candidate_id]:
        return False
    member_file_ids = {
        int(row[0])
        for row in db.query(CandidateMember.batch_file_id)
        .filter(
            CandidateMember.candidate_id == candidate_id,
            CandidateMember.batch_file_id.isnot(None),
            CandidateMember.role_in_candidate != "support",
        )
        .all()
    }
    audio_file_ids = {item.id for item in _audio_files(batch)}
    return bool(audio_file_ids) and audio_file_ids.issubset(member_file_ids)


def _append_audit(metadata: dict[str, Any], *, batch: IngestBatch, candidate_id: int, target_type: str) -> None:
    audit = list(metadata.get("media_type_correction_audit") or [])
    audit.append({
        "previous_detected_type": batch.detected_type,
        "target_detected_type": target_type,
        "candidate_id": candidate_id,
        "file_count": len(batch.files),
        "previous_suggested_destination": batch.suggested_destination,
        "corrected_at": now_utc().isoformat(),
        "corrected_by": "local_user",
    })
    metadata["media_type_correction_audit"] = audit


def _reclassify_as_audiobook(
    db: Session,
    batch: IngestBatch,
    candidate: MediaIdentityCandidate,
) -> None:
    audio = _audio_files(batch)
    if not audio:
        raise ValueError("Audiobook correction requires attached audio files")

    metadata = dict(batch.metadata_json or {})
    _append_audit(metadata, batch=batch, candidate_id=candidate.id, target_type="audiobook")
    author = str(
        candidate.candidate_primary_creator
        or metadata.get("author")
        or metadata.get("albumartist")
        or metadata.get("artist")
        or "Unknown Author"
    ).strip()
    title = str(
        candidate.candidate_title
        or metadata.get("title")
        or metadata.get("album")
        or "Unknown Title"
    ).strip()
    year = str(candidate.candidate_year or metadata.get("year") or metadata.get("date") or "").strip()[:4] or None
    audio_format = _audio_format(audio)
    destination = audiobook_destination(
        audiobooks_root=settings.audiobooks_dir,
        author=author,
        title=title,
        year=year,
    )

    metadata.update({
        "media_kind": "audiobook",
        "type": "audiobook",
        "review_type": "audiobook",
        "review_mode": "single_item",
        "author": author,
        "title": title,
        "year": year,
        "format": audio_format,
        "audiobook_file_count": len(audio),
        "audio_files": [item.file_name for item in audio],
        "file_count": len(batch.files),
        "artwork_count": len([item for item in batch.files if str(item.detected_role).casefold() in SUPPORT_ROLES]),
        "suggested_destination": str(destination),
        "suggested_destination_preview": str(destination),
        "metadata_confirmed": False,
        "review_confirmed": False,
        "metadata_quality": "fair",
    })
    metadata.pop("track_count", None)
    metadata.pop("tracks", None)
    metadata = build_review_state("audiobook", metadata)

    for item in audio:
        file_metadata = dict(item.metadata_json or {})
        file_metadata["media_type_override"] = {
            "previous_role": item.detected_role,
            "target_role": "audiobook_audio",
            "corrected_at": now_utc().isoformat(),
        }
        item.metadata_json = file_metadata
        item.detected_role = "audiobook_audio"

    candidate.candidate_media_type = "audiobook"
    candidate.updated_at = now_utc()
    batch.detected_type = "audiobook"
    batch.metadata_json = metadata
    batch.suggested_metadata = {
        "author": author,
        "title": title,
        "year": year,
        "format": audio_format,
        "sources": {"media_type": "manual correction"},
    }
    batch.suggested_destination = str(destination)
    batch.metadata_confirmed = False
    batch.status = "needs_metadata_review"
    batch.updated_at = now_utc()


def _reclassify_as_music(
    db: Session,
    batch: IngestBatch,
    candidate: MediaIdentityCandidate,
) -> None:
    audio = _audio_files(batch)
    if not audio:
        raise ValueError("Music correction requires attached audio files")
    metadata = dict(batch.metadata_json or {})
    _append_audit(metadata, batch=batch, candidate_id=candidate.id, target_type="music_album")
    artist = str(candidate.candidate_primary_creator or metadata.get("artist") or metadata.get("author") or "Unknown Artist").strip()
    album = str(candidate.candidate_title or metadata.get("album") or metadata.get("title") or "Unknown Album").strip()
    year = str(candidate.candidate_year or metadata.get("year") or metadata.get("date") or "").strip()[:4] or None
    metadata.update({
        "media_kind": "music",
        "type": "music_album",
        "review_type": "music_album",
        "review_mode": "single_album",
        "artist": artist,
        "albumartist": artist,
        "album": album,
        "title": album,
        "year": year,
        "track_count": len(audio),
        "audio_files": [item.file_name for item in audio],
        "file_count": len(batch.files),
        "metadata_confirmed": False,
        "review_confirmed": False,
        "metadata_quality": "fair",
    })
    metadata = build_review_state("music_album", metadata)
    for item in audio:
        item.detected_role = "music_track"
    candidate.candidate_media_type = "music"
    candidate.updated_at = now_utc()
    batch.detected_type = "music_album"
    batch.metadata_json = metadata
    batch.suggested_metadata = {"artist": artist, "album": album, "year": year}
    batch.metadata_confirmed = False
    batch.status = "needs_metadata_review"
    batch.updated_at = now_utc()
    rebuild_music_batch_destination_from_attached_files(batch, db)


def apply_fully_scoped_media_class_override(
    db: Session,
    batch_id: int,
    candidate_id: int | None,
    target_media_class: str | None,
) -> bool:
    """Persist a candidate type correction only when it safely represents the whole batch."""
    if candidate_id is None or target_media_class not in {"audiobook_audio", "music_audio"}:
        return False
    batch = db.get(IngestBatch, batch_id)
    candidate = db.get(MediaIdentityCandidate, candidate_id)
    if batch is None or candidate is None or candidate.batch_id != batch_id:
        return False
    if batch.status in {"moved", "merged", "approved"}:
        raise ValueError("Closed or approved batches cannot change media type")
    if not _candidate_covers_batch_audio(db, batch, candidate_id):
        return False

    if target_media_class == "audiobook_audio" and batch.detected_type != "audiobook":
        _reclassify_as_audiobook(db, batch, candidate)
    elif target_media_class == "music_audio" and batch.detected_type != "music_album":
        _reclassify_as_music(db, batch, candidate)
    else:
        return False
    db.commit()
    return True

def correct_batch_media_type(db: Session, batch_id: int, target_detected_type: str) -> IngestBatch:
    """Apply an explicit whole-batch correction after rebuilding scoped candidates."""
    target_classes = {
        "audiobook": "audiobook_audio",
        "music_album": "music_audio",
    }
    target_media_class = target_classes.get(target_detected_type)
    if target_media_class is None:
        raise ValueError("Unsupported target media type")
    batch = db.get(IngestBatch, batch_id)
    if batch is None:
        raise ValueError("Batch not found")
    if batch.status in {"moved", "merged", "approved"}:
        raise ValueError("Closed or approved batches cannot change media type")

    from app.services.universal_ingestion import snapshot_universal_ingestion_boundary

    snapshot_universal_ingestion_boundary(db, batch)
    db.flush()
    candidates = (
        db.query(MediaIdentityCandidate)
        .filter(MediaIdentityCandidate.batch_id == batch_id)
        .all()
    )
    if len(candidates) != 1:
        raise ValueError(
            "Whole-batch media correction requires exactly one scoped candidate. "
            "Use Review Workspace to separate mixed candidates first."
        )
    if batch.detected_type != target_detected_type:
        changed = apply_fully_scoped_media_class_override(
            db,
            batch_id,
            candidates[0].id,
            target_media_class,
        )
        if not changed:
            raise ValueError("The candidate does not own every attached audio file")
    return db.get(IngestBatch, batch_id)
