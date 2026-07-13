from __future__ import annotations

from pathlib import Path
from typing import Any

from sqlalchemy import or_
from sqlalchemy.orm import Session, selectinload

from app.core.config import settings
from app.core.time import now_utc
from app.models.archive import IngestBatch, IngestFile
from app.models.media_metadata import CandidateMember, MediaIdentityCandidate, UniversalIngestionReviewAction
from app.services.audiobook_metadata import audiobook_destination
from app.services.destination_authority import rebuild_music_batch_destination_from_attached_files
from app.services.parent_candidate_materialization import is_parent_container_batch
from app.services.review_state import build_review_state


AUDIO_EXTENSIONS = {
    ".aac", ".aiff", ".alac", ".flac", ".m4a", ".m4b", ".mp3",
    ".ogg", ".opus", ".wav", ".wma",
}
SUPPORT_ROLES = {"artwork", "cover_art", "album_artwork", "sidecar", "metadata_sidecar", "playlist"}
WHOLE_BATCH_SCOPE_CONFIRMATION = "all_attached_primary_audio_files"


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
    if len(candidate_ids) != 1 or candidate_ids[0] != candidate_id:
        return False
    member_file_ids = {
        int(row[0])
        for row in db.query(CandidateMember.batch_file_id)
        .filter(
            CandidateMember.candidate_id == candidate_id,
            CandidateMember.batch_file_id.isnot(None),
            or_(
                CandidateMember.role_in_candidate.is_(None),
                CandidateMember.role_in_candidate != "support",
            ),
        )
        .all()
    }
    audio_file_ids = {item.id for item in _audio_files(batch)}
    return bool(audio_file_ids) and audio_file_ids.issubset(member_file_ids)


def _append_audit(metadata: dict[str, Any], *, batch: IngestBatch, candidate: MediaIdentityCandidate, target_type: str) -> None:
    audio = _audio_files(batch)
    audit = list(metadata.get("media_type_correction_audit") or [])
    audit.append({
        "previous_detected_type": batch.detected_type,
        "target_detected_type": target_type,
        "candidate_id": candidate.id,
        "file_count": len(batch.files),
        "previous_suggested_destination": batch.suggested_destination,
        "previous_candidate_media_type": candidate.candidate_media_type,
        "scoped_audio_file_ids": [int(item.id) for item in audio if item.id is not None],
        "scoped_file_roles": [
            {"file_id": int(item.id), "role": item.detected_role}
            for item in audio
            if item.id is not None
        ],
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
    _append_audit(metadata, batch=batch, candidate=candidate, target_type="audiobook")
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
    _append_audit(metadata, batch=batch, candidate=candidate, target_type="music_album")
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


def _apply_fully_scoped_media_class_override(
    db: Session,
    batch_id: int,
    candidate_id: int,
    target_media_class: str,
) -> bool:
    """Apply an explicitly confirmed whole-batch correction."""
    if target_media_class not in {"audiobook_audio", "music_audio"}:
        return False
    batch = (
        db.query(IngestBatch)
        .options(selectinload(IngestBatch.files))
        .filter(IngestBatch.id == batch_id)
        .first()
    )
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


def _scoped_candidates(db: Session, batch_id: int) -> list[MediaIdentityCandidate]:
    return (
        db.query(MediaIdentityCandidate)
        .filter(MediaIdentityCandidate.batch_id == batch_id)
        .order_by(MediaIdentityCandidate.id)
        .all()
    )


def correct_batch_media_type(
    db: Session,
    batch_id: int,
    target_detected_type: str,
    *,
    confirmed: bool = False,
    scope_confirmation: str | None = None,
    expected_audio_file_ids: list[int] | set[int] | None = None,
) -> IngestBatch:
    """Apply a confirmed whole-batch correction to one fully scoped candidate."""
    if not confirmed:
        raise ValueError("Whole-batch media correction requires explicit user confirmation")
    target_classes = {
        "audiobook": "audiobook_audio",
        "music_album": "music_audio",
    }
    target_media_class = target_classes.get(target_detected_type)
    if target_media_class is None:
        raise ValueError("Unsupported target media type")
    batch = (
        db.query(IngestBatch)
        .options(selectinload(IngestBatch.files))
        .filter(IngestBatch.id == batch_id)
        .first()
    )
    if batch is None:
        raise ValueError("Batch not found")
    if batch.status in {"moved", "merged", "approved"}:
        raise ValueError("Closed or approved batches cannot change media type")
    if is_parent_container_batch(batch):
        raise ValueError(
            "Parent or reconstructed containers cannot use whole-batch media conversion. "
            "Review and separate candidate groups first."
        )

    actual_audio_file_ids = {
        int(item.id)
        for item in _audio_files(batch)
        if item.id is not None
    }
    confirmed_audio_file_ids = {
        int(file_id)
        for file_id in (expected_audio_file_ids or [])
    }
    if scope_confirmation != WHOLE_BATCH_SCOPE_CONFIRMATION:
        raise ValueError(
            "Whole-batch media correction requires confirmation that every attached primary "
            "audio file belongs to one media object."
        )
    if not actual_audio_file_ids or confirmed_audio_file_ids != actual_audio_file_ids:
        raise ValueError(
            "Attached audio ownership changed or was not fully confirmed. "
            "Refresh the batch and review its file membership before changing the whole batch type."
        )

    candidates = _scoped_candidates(db, batch_id)
    if not candidates:
        from app.services.universal_ingestion import snapshot_universal_ingestion_boundary

        snapshot_universal_ingestion_boundary(db, batch)
        db.flush()
        candidates = _scoped_candidates(db, batch_id)
    if len(candidates) != 1:
        raise ValueError(
            "Whole-batch media correction requires exactly one scoped candidate. "
            "Use Review Workspace to separate mixed candidates first."
        )
    candidate = candidates[0]
    if not _candidate_covers_batch_audio(db, batch, candidate.id):
        raise ValueError("The candidate does not own every attached primary audio file")
    if batch.detected_type != target_detected_type:
        changed = _apply_fully_scoped_media_class_override(
            db,
            batch_id,
            candidate.id,
            target_media_class,
        )
        if not changed:
            raise ValueError("The candidate does not own every attached primary audio file")
    return db.get(IngestBatch, batch_id)


def _linked_child_batches(db: Session, batch: IngestBatch) -> list[IngestBatch]:
    metadata = batch.metadata_json or {}
    known_ids = {
        int(value)
        for value in (metadata.get("created_child_batch_ids") or [])
        if str(value).isdigit()
    }
    for row in metadata.get("split_history") or []:
        if isinstance(row, dict) and str(row.get("child_batch_id") or "").isdigit():
            known_ids.add(int(row["child_batch_id"]))
    children: list[IngestBatch] = []
    for child in db.query(IngestBatch).options(selectinload(IngestBatch.files)).all():
        if child.id == batch.id:
            continue
        child_metadata = child.metadata_json or {}
        linked = child_metadata.get("source_parent_batch_id") == batch.id or child_metadata.get("split_from_batch_id") == batch.id
        if linked or child.id in known_ids:
            children.append(child)
    return sorted(children, key=lambda item: item.id)


def inspect_batch_media_type_recovery(db: Session, batch_id: int) -> dict[str, Any]:
    """Return current type, ownership, linkage, and correction audit without mutation."""
    batch = (
        db.query(IngestBatch)
        .options(selectinload(IngestBatch.files))
        .filter(IngestBatch.id == batch_id)
        .first()
    )
    if batch is None:
        raise ValueError("Batch not found")
    candidates = _scoped_candidates(db, batch_id)
    candidate_ids = [candidate.id for candidate in candidates]
    members = (
        db.query(CandidateMember)
        .filter(CandidateMember.candidate_id.in_(candidate_ids))
        .all()
        if candidate_ids
        else []
    )
    members_by_file: dict[int, list[CandidateMember]] = {}
    for member in members:
        if member.batch_file_id is not None:
            members_by_file.setdefault(int(member.batch_file_id), []).append(member)
    overrides = {
        int(action.candidate_id): action.target_media_class
        for action in db.query(UniversalIngestionReviewAction)
        .filter(
            UniversalIngestionReviewAction.batch_id == batch_id,
            UniversalIngestionReviewAction.action_type == "override_media_class",
            UniversalIngestionReviewAction.decision_status != "cleared",
            UniversalIngestionReviewAction.candidate_id.isnot(None),
        )
        .order_by(UniversalIngestionReviewAction.updated_at, UniversalIngestionReviewAction.id)
        .all()
        if action.candidate_id is not None
    }
    children = _linked_child_batches(db, batch)
    metadata = batch.metadata_json or {}
    return {
        "batch_id": batch.id,
        "current_detected_type": batch.detected_type,
        "attached_file_count": len(batch.files),
        "candidate_count": len(candidates),
        "candidate_media_classes": [
            {
                "candidate_id": candidate.id,
                "candidate_key": candidate.candidate_key,
                "title": candidate.candidate_title,
                "creator": candidate.candidate_primary_creator,
                "stored_media_class": candidate.candidate_media_type,
                "effective_media_class": overrides.get(candidate.id) or candidate.candidate_media_type,
            }
            for candidate in candidates
        ],
        "child_batches": [
            {
                "batch_id": child.id,
                "detected_type": child.detected_type,
                "status": child.status,
                "attached_file_count": len(child.files),
                "suggested_destination": child.suggested_destination,
            }
            for child in children
        ],
        "media_type_correction_audit": list(metadata.get("media_type_correction_audit") or []),
        "current_file_owners": [
            {
                "file_id": item.id,
                "file_name": item.file_name,
                "batch_id": item.batch_id,
                "detected_role": item.detected_role,
                "candidate_owners": [
                    {
                        "candidate_id": member.candidate_id,
                        "role": member.role_in_candidate,
                        "media_class": member.media_class,
                    }
                    for member in members_by_file.get(item.id, [])
                ],
            }
            for item in batch.files
        ],
        "source_parent_linkage": {
            "source_parent_batch_id": metadata.get("source_parent_batch_id"),
            "split_from_batch_id": metadata.get("split_from_batch_id"),
            "source_parent_path": metadata.get("source_parent_path"),
            "split_from_source_path": metadata.get("split_from_source_path"),
        },
    }


def repair_batch_media_type_from_audit(
    db: Session,
    batch_id: int,
    *,
    target_detected_type: str | None = None,
    confirmed: bool = False,
) -> IngestBatch:
    """Repair a wrong whole-batch classification using audit and attached evidence."""
    if not confirmed:
        raise ValueError("Media type recovery requires explicit user confirmation")
    batch = (
        db.query(IngestBatch)
        .options(selectinload(IngestBatch.files))
        .filter(IngestBatch.id == batch_id)
        .first()
    )
    if batch is None:
        raise ValueError("Batch not found")
    metadata = dict(batch.metadata_json or {})
    correction_audit = list(metadata.get("media_type_correction_audit") or [])
    latest = correction_audit[-1] if correction_audit and isinstance(correction_audit[-1], dict) else {}
    target = target_detected_type or latest.get("previous_detected_type")
    if not target:
        raise ValueError("No audited previous media type is available; provide a recovery target")
    if target in {"music_album", "audiobook"}:
        recovered_from = batch.detected_type
        repaired = correct_batch_media_type(
            db,
            batch_id,
            str(target),
            confirmed=True,
            scope_confirmation=WHOLE_BATCH_SCOPE_CONFIRMATION,
            expected_audio_file_ids=[
                int(item.id)
                for item in _audio_files(batch)
                if item.id is not None
            ],
        )
        repaired_metadata = dict(repaired.metadata_json or {})
        recovery_audit = list(repaired_metadata.get("media_type_recovery_audit") or [])
        recovery_audit.append({
            "recovered_from": recovered_from,
            "restored_detected_type": target,
            "recovered_at": now_utc().isoformat(),
            "source": "correction_audit_and_attached_file_evidence",
        })
        repaired_metadata["media_type_recovery_audit"] = recovery_audit
        repaired.metadata_json = repaired_metadata
        db.commit()
        return repaired
    if target != "music_discography":
        raise ValueError("Unsupported recovery target")
    if not correction_audit:
        raise ValueError("Restoring a parent container requires a media type correction audit")

    for item in batch.files:
        file_metadata = dict(item.metadata_json or {})
        override = file_metadata.get("media_type_override")
        if isinstance(override, dict) and override.get("previous_role"):
            item.detected_role = str(override["previous_role"])
            recovery_rows = list(file_metadata.get("media_type_recovery_audit") or [])
            recovery_rows.append({
                "restored_role": item.detected_role,
                "recovered_at": now_utc().isoformat(),
            })
            file_metadata["media_type_recovery_audit"] = recovery_rows
            item.metadata_json = file_metadata

    candidate_id = latest.get("candidate_id")
    candidate = db.get(MediaIdentityCandidate, int(candidate_id)) if str(candidate_id or "").isdigit() else None
    if candidate is not None and candidate.batch_id == batch.id and latest.get("previous_candidate_media_type"):
        candidate.candidate_media_type = str(latest["previous_candidate_media_type"])
        candidate.updated_at = now_utc()

    metadata.update({
        "type": "music_discography",
        "review_type": "music_discography",
        "review_mode": "collection",
        "metadata_confirmed": False,
        "review_confirmed": False,
    })
    recovery_audit = list(metadata.get("media_type_recovery_audit") or [])
    recovery_audit.append({
        "recovered_from": batch.detected_type,
        "restored_detected_type": "music_discography",
        "recovered_at": now_utc().isoformat(),
        "source": "correction_audit_and_attached_file_evidence",
    })
    metadata["media_type_recovery_audit"] = recovery_audit
    batch.detected_type = "music_discography"
    batch.status = "pending_review"
    batch.metadata_confirmed = False
    batch.suggested_destination = latest.get("previous_suggested_destination")
    metadata["suggested_destination"] = batch.suggested_destination
    batch.metadata_json = metadata
    batch.updated_at = now_utc()
    db.commit()
    return batch