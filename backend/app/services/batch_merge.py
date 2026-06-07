from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from sqlalchemy.orm import Session, selectinload

from app.models.archive import IngestBatch, IngestFile
from app.services.music_metadata import (
    canonical_album_key,
    canonical_artist_key,
    evaluate_music_album_metadata,
    sort_music_tracks,
)


ACTIVE_MERGE_STATUSES = {
    "pending_review",
    "needs_metadata_review",
    "metadata_recovery",
    "approved",
}


@dataclass(frozen=True)
class BatchMergeResult:
    batch: IngestBatch
    merged_batch_ids: list[int]
    merged_track_count: int

    @property
    def message(self) -> str | None:
        if not self.merged_batch_ids:
            return None
        return (
            f"Metadata saved. {self.merged_track_count} track(s) merged into "
            f"Batch {self.batch.id}."
        )


def _batch_metadata(batch: IngestBatch) -> tuple[str, str, str | None, str]:
    metadata = batch.metadata_json or {}
    artist = str(metadata.get("artist") or metadata.get("albumartist") or "")
    album = str(metadata.get("album") or "")
    raw_year = str(metadata.get("year") or metadata.get("date") or "")[:4]
    year = raw_year if raw_year.isdigit() else None
    format_bucket = str(metadata.get("format") or "").upper()
    if format_bucket not in {"MP3", "FLAC"}:
        destination_parts = {
            part.upper() for part in Path(batch.suggested_destination or "").parts
        }
        format_bucket = "FLAC" if "FLAC" in destination_parts else "MP3"
    return artist, album, year, format_bucket


def _years_match(left: str | None, right: str | None) -> bool:
    return not left or not right or left == right


def find_merge_candidate_batches(
    db: Session,
    batch: IngestBatch,
) -> list[IngestBatch]:
    artist, album, year, format_bucket = _batch_metadata(batch)
    if not artist or not album:
        return []

    candidates = (
        db.query(IngestBatch)
        .options(selectinload(IngestBatch.files))
        .filter(
            IngestBatch.id != batch.id,
            IngestBatch.detected_type == "music_album",
            IngestBatch.status.in_(ACTIVE_MERGE_STATUSES),
        )
        .all()
    )
    matches = []
    for candidate in candidates:
        candidate_artist, candidate_album, candidate_year, candidate_format = (
            _batch_metadata(candidate)
        )
        if canonical_artist_key(candidate_artist) != canonical_artist_key(artist):
            continue
        if canonical_album_key(candidate_album) != canonical_album_key(album):
            continue
        if not _years_match(candidate_year, year):
            continue
        if candidate_format != format_bucket:
            continue
        if not (
            Path(candidate.source_path).resolve() == Path(batch.source_path).resolve()
            or candidate.suggested_destination == batch.suggested_destination
            or batch.metadata_confirmed
        ):
            continue
        matches.append(candidate)
    return matches


def find_archived_duplicate_candidate(
    db: Session,
    batch: IngestBatch,
) -> IngestBatch | None:
    artist, album, year, format_bucket = _batch_metadata(batch)
    if not artist or not album:
        return None
    moved_batches = (
        db.query(IngestBatch)
        .filter(
            IngestBatch.id != batch.id,
            IngestBatch.detected_type == "music_album",
            IngestBatch.status == "moved",
        )
        .all()
    )
    for candidate in moved_batches:
        candidate_artist, candidate_album, candidate_year, candidate_format = (
            _batch_metadata(candidate)
        )
        if (
            canonical_artist_key(candidate_artist) == canonical_artist_key(artist)
            and canonical_album_key(candidate_album) == canonical_album_key(album)
            and _years_match(candidate_year, year)
            and candidate_format == format_bucket
        ):
            return candidate
    return None


def _combined_track_metadata(files: list[IngestFile]) -> tuple[list[dict], int]:
    tracks = []
    discs = set()
    for ingest_file in sort_music_tracks(files):
        metadata = ingest_file.metadata_json or {}
        disc_number = metadata.get("discnumber", 1)
        normalized_disc = str(disc_number).split("/")[0].split(".")[0]
        discs.add(normalized_disc)
        tracks.append(
            {
                "title": metadata.get("title") or Path(ingest_file.file_name).stem,
                "track_number": metadata.get("tracknumber", "1"),
                "disc_number": disc_number,
            }
        )
    return tracks, max(1, len(discs))


def merge_music_batches(
    db: Session,
    confirmed_batch: IngestBatch,
    source_batches: list[IngestBatch],
) -> BatchMergeResult:
    if not source_batches:
        return BatchMergeResult(confirmed_batch, [], 0)

    batches = [confirmed_batch, *source_batches]
    target = max(batches, key=lambda item: (len(item.files), -item.id))
    confirmed_metadata = dict(confirmed_batch.metadata_json or {})
    merged_ids = [item.id for item in batches if item.id != target.id]
    merged_track_count = sum(len(item.files) for item in batches if item.id != target.id)

    warnings = []
    previous_merged_ids = []
    for item in batches:
        metadata = item.metadata_json or {}
        warnings.extend(metadata.get("metadata_warnings", []))
        previous_merged_ids.extend(metadata.get("merged_batch_ids", []))

    for source in batches:
        if source.id == target.id:
            continue
        db.query(IngestFile).filter(IngestFile.batch_id == source.id).update(
            {IngestFile.batch_id: target.id},
            synchronize_session=False,
        )
        source_metadata = dict(source.metadata_json or {})
        source_metadata["merged_into_batch_id"] = target.id
        source.metadata_json = source_metadata
        source.status = "merged"
        source.updated_at = datetime.utcnow()

    db.flush()
    files = (
        db.query(IngestFile)
        .filter(IngestFile.batch_id == target.id)
        .order_by(IngestFile.id.asc())
        .all()
    )
    tracks, disc_count = _combined_track_metadata(files)

    confirmed_metadata["track_count"] = len(files)
    confirmed_metadata["disc_count"] = disc_count
    confirmed_metadata["tracks"] = tracks
    confirmed_metadata["metadata_warnings"] = list(
        dict.fromkeys([*warnings, "manual_duplicate_batch_merge_performed"])
    )
    confirmed_metadata["merged_batch_ids"] = sorted(
        set([*previous_merged_ids, *merged_ids])
    )
    quality = evaluate_music_album_metadata(confirmed_metadata)
    quality["metadata_warnings"] = confirmed_metadata["metadata_warnings"]
    confirmed_metadata.update(quality)

    target.metadata_json = confirmed_metadata
    target.suggested_metadata = confirmed_batch.suggested_metadata
    target.suggested_destination = confirmed_batch.suggested_destination
    target.metadata_confirmed = True
    target.confidence = quality["confidence"]
    target.status = (
        "pending_review"
        if quality["metadata_quality"] in {"good", "fair"}
        else "needs_metadata_review"
    )
    target.approved_at = None
    target.approved_by = None
    target.updated_at = datetime.utcnow()
    db.flush()
    db.refresh(target)
    return BatchMergeResult(target, merged_ids, merged_track_count)
