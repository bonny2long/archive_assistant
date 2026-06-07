from datetime import datetime
from pathlib import Path
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session, selectinload
from app.db.session import get_db
from app.models.archive import ArchiveItem, IngestBatch, IngestFile, MoveAction
from app.schemas.archive import (
    ApproveResponse, 
    BulkApproveError,
    BulkApproveRequest,
    BulkApproveResponse,
    BatchMoveSummary,
    BatchMetadataUpdate,
    BatchReview,
    BatchReviewTrack,
    BatchSummary, 
    DiscographyMetadataUpdate,
    DevResetResponse,
    IngestBatchOut, 
    IngestFileOut,
    LibrarySummary,
    MoveActionOut,
    MoveResponse,
    PaginatedResponse,
    ScanMusicResponse,
)
from app.services.dev_reset import DevResetBlockedError, reset_music_test_data
from app.services.batch_merge import (
    find_archived_duplicate_candidate,
    find_merge_candidate_batches,
    merge_music_batches,
)
from app.services.music_metadata import (
    canonical_album_key,
    canonical_artist_key,
    evaluate_music_album_metadata,
    is_compilation_artist,
    music_track_filename,
    music_track_numbers,
    sort_music_tracks,
    suggest_music_destination,
)
from app.services.scanner import scan_music_ingest
from app.services.mover import move_approved_batches
from app.core.config import settings

router = APIRouter(prefix="/api")

BLOCKING_APPROVAL_WARNINGS = {
    "possible_duplicate_destination",
    "possible_artist_alias",
    "possible_archived_duplicate_candidate",
    "destination_file_conflict",
    "child_album_metadata_missing",
    "discography_destination_exists",
}


@router.get("/health")
def health():
    return {
        "status": "ok",
        "service": "archive-assistant",
        "debug": settings.debug,
        "dev_tools_enabled": settings.debug and settings.dev_tools_enabled,
    }


@router.post("/scan/music", response_model=ScanMusicResponse)
def scan_music(db: Session = Depends(get_db)):
    result = scan_music_ingest(db)
    return ScanMusicResponse(
        created=result.created,
        skipped_duplicates=result.skipped_duplicates,
        batches=result.batches,
    )


@router.post("/dev/reset/music-test", response_model=DevResetResponse)
def dev_reset_music_test(db: Session = Depends(get_db)):
    if not (settings.debug and settings.dev_tools_enabled):
        raise HTTPException(status_code=404, detail="Dev reset is not available")
    try:
        summary = reset_music_test_data(db, apply=True)
    except DevResetBlockedError as exc:
        raise HTTPException(status_code=409, detail=exc.errors) from exc
    return DevResetResponse(**summary.__dict__)


@router.get("/batches", response_model=PaginatedResponse[BatchSummary])
def list_batches(
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=100),
    db: Session = Depends(get_db)
):
    query = db.query(IngestBatch).filter(IngestBatch.status != "merged")
    total = query.count()
    batches = (
        query.order_by(IngestBatch.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    
    items = [_batch_to_summary(b) for b in batches]
    return PaginatedResponse(
        items=items,
        page=page,
        page_size=page_size,
        total=total,
        total_pages=(total + page_size - 1) // page_size
    )


@router.get("/batches/pending", response_model=PaginatedResponse[BatchSummary])
def list_pending_batches(
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=100),
    db: Session = Depends(get_db)
):
    query = db.query(IngestBatch).filter(
        IngestBatch.status.in_(["pending_review", "needs_metadata_review", "metadata_recovery"])
    )
    total = query.count()
    batches = (
        query.order_by(IngestBatch.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    
    items = [_batch_to_summary(b) for b in batches]
    return PaginatedResponse(
        items=items,
        page=page,
        page_size=page_size,
        total=total,
        total_pages=(total + page_size - 1) // page_size
    )


@router.get("/batches/{batch_id}", response_model=IngestBatchOut)
def get_batch(batch_id: int, db: Session = Depends(get_db)):
    batch = (
        db.query(IngestBatch)
        .options(selectinload(IngestBatch.files))
        .filter(IngestBatch.id == batch_id)
        .first()
    )
    if not batch:
        raise HTTPException(status_code=404, detail="Batch not found")
    batch.files = sort_music_tracks(batch.files)
    return batch


@router.get("/batches/{batch_id}/review", response_model=BatchReview)
def get_batch_review(batch_id: int, db: Session = Depends(get_db)):
    batch = (
        db.query(IngestBatch)
        .options(selectinload(IngestBatch.files))
        .filter(IngestBatch.id == batch_id)
        .first()
    )
    if not batch:
        raise HTTPException(status_code=404, detail="Batch not found")

    metadata = batch.metadata_json or {}
    artist = str(metadata.get("artist") or metadata.get("albumartist") or "") or None
    album = str(metadata.get("album") or "") or None
    year = str(metadata.get("year") or metadata.get("date") or "")[:4] or None
    genre = str(metadata.get("genre") or "") or None
    format_bucket = str(metadata.get("format") or "MP3").upper()
    ordered_files = sort_music_tracks(batch.files)
    parsed_discs = [
        music_track_numbers(item.metadata_json or {}, item.file_name)[0]
        for item in ordered_files
    ]
    disc_count = max(parsed_discs, default=1)
    expected_artist_key = canonical_artist_key(artist or "")
    expected_album_key = canonical_album_key(album or "")
    compilation = is_compilation_artist(artist)

    tracks = []
    for position, ingest_file in enumerate(ordered_files, start=1):
        track_metadata = ingest_file.metadata_json or {}
        disc, track = music_track_numbers(track_metadata, ingest_file.file_name)
        track_artist = str(
            track_metadata.get("albumartist")
            or track_metadata.get("artist")
            or ""
        ) or None
        track_album = str(track_metadata.get("album") or "") or None
        warnings = []
        if (
            expected_album_key
            and track_album
            and canonical_album_key(track_album) != expected_album_key
        ):
            warnings.append("album_tag_mismatch")
        if (
            not compilation
            and expected_artist_key
            and track_artist
            and canonical_artist_key(track_artist) != expected_artist_key
        ):
            warnings.append("artist_tag_mismatch")

        tracks.append(
            BatchReviewTrack(
                position=position,
                disc=disc,
                track=track,
                title=str(
                    track_metadata.get("title")
                    or Path(ingest_file.file_name).stem
                ),
                source_filename=ingest_file.file_name,
                destination_filename=music_track_filename(
                    track_metadata,
                    ingest_file.extension,
                    disc_count,
                    ingest_file.file_name,
                ),
                artist=track_artist,
                album=track_album,
                warnings=warnings,
            )
        )

    return BatchReview(
        batch_id=batch.id,
        artist=artist,
        album=album,
        year=year,
        genre=genre,
        format=format_bucket,
        status=batch.status,
        confidence=batch.confidence,
        track_count=len(tracks),
        disc_count=disc_count,
        warnings=list(metadata.get("metadata_warnings", [])),
        source_path=batch.source_path,
        destination_preview=batch.suggested_destination,
        tracks=tracks,
    )


@router.get("/batches/{batch_id}/files", response_model=list[IngestFileOut])
def get_batch_files(batch_id: int, db: Session = Depends(get_db)):
    files = sort_music_tracks(
        db.query(IngestFile).filter(IngestFile.batch_id == batch_id).all()
    )
    if not files and not db.get(IngestBatch, batch_id):
        raise HTTPException(status_code=404, detail="Batch not found")
    return files


@router.get("/batches/{batch_id}/moves", response_model=BatchMoveSummary)
def get_batch_moves(batch_id: int, db: Session = Depends(get_db)):
    if not db.get(IngestBatch, batch_id):
        raise HTTPException(status_code=404, detail="Batch not found")

    actions = (
        db.query(MoveAction)
        .filter(MoveAction.batch_id == batch_id)
        .order_by(MoveAction.id.asc())
        .all()
    )
    moves = [
        MoveActionOut(
            id=action.id,
            source_path=action.source_path,
            destination_path=action.destination_path,
            file_name=Path(action.destination_path or action.source_path).name,
            status=action.status,
            error_message=action.error_message,
            created_at=action.created_at,
            completed_at=action.completed_at,
        )
        for action in actions
    ]
    return BatchMoveSummary(
        batch_id=batch_id,
        total=len(moves),
        completed=sum(move.status == "completed" for move in moves),
        failed=sum(move.status == "failed" for move in moves),
        moves=moves,
    )


@router.get("/library/summary", response_model=LibrarySummary)
def library_summary(db: Session = Depends(get_db)):
    moved_albums = db.query(IngestBatch).filter(IngestBatch.status == "moved").count()
    moved_tracks = db.query(MoveAction).filter(MoveAction.status == "completed").count()
    failed_moves = db.query(MoveAction).filter(MoveAction.status == "failed").count()
    approved_waiting = db.query(IngestBatch).filter(IngestBatch.status == "approved").count()
    needs_metadata = (
        db.query(IngestBatch)
        .filter(IngestBatch.status.in_(["needs_metadata_review", "metadata_recovery"]))
        .count()
    )
    return LibrarySummary(
        moved_albums=moved_albums,
        moved_tracks=moved_tracks,
        failed_moves=failed_moves,
        approved_waiting=approved_waiting,
        needs_metadata=needs_metadata,
    )


@router.patch("/batches/{batch_id}/metadata", response_model=BatchSummary)
def update_batch_metadata(batch_id: int, update: BatchMetadataUpdate, db: Session = Depends(get_db)):
    batch = db.get(IngestBatch, batch_id)
    if not batch:
        raise HTTPException(status_code=404, detail="Batch not found")
    
    if batch.status in {"moved", "move_failed", "merged"}:
        raise HTTPException(status_code=400, detail="Moved batches cannot be edited")

    meta = dict(batch.metadata_json or {})
    
    # Update core fields
    meta["artist"] = update.artist.strip()
    meta["albumartist"] = update.artist.strip()
    meta["album"] = update.album.strip()
    meta["year"] = update.year.strip()
    meta["date"] = update.year.strip()
    meta.pop("metadata_alerts", None)
    if update.primary_genre is not None:
        meta["genre"] = update.primary_genre.strip() or "Unknown"
    if update.format is not None:
        meta["format"] = update.format.strip().upper()
    
    # Re-evaluate quality
    quality_res = evaluate_music_album_metadata(meta)
    meta.update(quality_res)
    
    file_format = str(meta.get("format", "MP3")).lower()
    new_dest = suggest_music_destination(
        {
            "albumartist": meta["artist"],
            "album": meta["album"],
            "date": meta["year"],
            "extension": file_format,
        },
        settings.music_flac_dir,
        settings.music_mp3_dir
    )
    
    batch.metadata_json = meta
    batch.suggested_destination = str(new_dest)
    batch.suggested_metadata = {
        "artist": meta["artist"],
        "album": meta["album"],
        "year": meta["year"],
        "genre": meta.get("genre"),
        "sources": {
            "artist": "manual correction",
            "album": "manual correction",
            "year": "manual correction",
            "genre": "manual correction",
        },
    }
    batch.confidence = quality_res["confidence"]
    batch.metadata_confirmed = True

    if quality_res["metadata_quality"] in ("good", "fair"):
        batch.status = "pending_review"
    elif quality_res["metadata_quality"] == "broken":
        batch.status = "metadata_recovery"
    else:
        batch.status = "needs_metadata_review"
    
    batch.updated_at = datetime.utcnow()
    db.flush()

    merge_candidates = find_merge_candidate_batches(db, batch)
    merge_result = merge_music_batches(db, batch, merge_candidates)
    action_message = merge_result.message
    if not merge_result.merged_batch_ids:
        archived_candidate = find_archived_duplicate_candidate(db, merge_result.batch)
        if archived_candidate:
            merged_meta = dict(merge_result.batch.metadata_json or {})
            warnings = list(merged_meta.get("metadata_warnings", []))
            warnings.append("possible_archived_duplicate_candidate")
            merged_meta["metadata_warnings"] = list(dict.fromkeys(warnings))
            merged_meta["metadata_alerts"] = [
                *list(merged_meta.get("metadata_alerts", [])),
                {
                    "type": "possible_archived_duplicate_candidate",
                    "message": (
                        f"Batch {archived_candidate.id} already archived this "
                        "canonical release. It was not merged."
                    ),
                    "existing_batch_id": archived_candidate.id,
                    "existing_path": archived_candidate.suggested_destination,
                },
            ]
            merge_result.batch.metadata_json = merged_meta
            action_message = (
                "Metadata saved. Matching release is already archived in "
                f"Batch {archived_candidate.id}; no merge was performed."
            )
    db.commit()
    return _batch_to_summary(
        merge_result.batch,
        action_message=action_message or "Metadata saved.",
    )


@router.patch("/batches/{batch_id}/discography", response_model=BatchSummary)
def update_discography_metadata(
    batch_id: int,
    update: DiscographyMetadataUpdate,
    db: Session = Depends(get_db),
):
    batch = db.get(IngestBatch, batch_id)
    if not batch:
        raise HTTPException(status_code=404, detail="Batch not found")
    if batch.detected_type != "music_discography":
        raise HTTPException(status_code=400, detail="Batch is not a discography")
    if batch.status in {"moved", "merged"}:
        raise HTTPException(status_code=400, detail="Moved batches cannot be edited")

    artist = update.artist.strip()
    metadata = dict(batch.metadata_json or {})
    metadata["artist"] = artist
    albums = []
    for album in metadata.get("albums", []):
        album_copy = dict(album)
        album_copy["artist"] = artist
        albums.append(album_copy)
    metadata["albums"] = albums
    warnings = [
        warning
        for warning in metadata.get("metadata_warnings", [])
        if warning != "artist_missing"
    ]
    blocking = "child_album_metadata_missing" in warnings
    metadata["metadata_warnings"] = warnings
    metadata["metadata_quality"] = "weak" if blocking else "good"
    metadata["confidence"] = 0.6 if blocking else 1.0

    batch.metadata_json = metadata
    batch.suggested_metadata = {
        "artist": artist,
        "sources": {"artist": "manual correction"},
    }
    batch.suggested_destination = str(settings.music_discographies_dir / artist)
    batch.metadata_confirmed = True
    batch.confidence = metadata["confidence"]
    batch.status = "needs_metadata_review" if blocking else "pending_review"
    batch.updated_at = datetime.utcnow()
    db.commit()
    return _batch_to_summary(batch, action_message="Discography metadata saved.")


@router.post("/batches/{batch_id}/approve", response_model=ApproveResponse)
def approve_batch(batch_id: int, db: Session = Depends(get_db)):
    batch = db.get(IngestBatch, batch_id)
    if not batch:
        raise HTTPException(status_code=404, detail="Batch not found")
    
    meta = batch.metadata_json or {}
    quality = meta.get("metadata_quality", "weak")
    if batch.status in {"needs_metadata_review", "metadata_recovery"} or quality in {"weak", "broken"}:
        return ApproveResponse(
            batch_id=batch.id, 
            status=batch.status, 
            message="Batch requires metadata review before approval.",
            metadata_quality=meta.get("metadata_quality"),
            metadata_warnings=meta.get("metadata_warnings", [])
        )
    blocking_warnings = set(meta.get("metadata_warnings", [])) & BLOCKING_APPROVAL_WARNINGS
    if blocking_warnings:
        return ApproveResponse(
            batch_id=batch.id,
            status=batch.status,
            message="Batch has a blocking warning that must be resolved before approval.",
            metadata_quality=meta.get("metadata_quality"),
            metadata_warnings=sorted(blocking_warnings),
        )

    if batch.status != "pending_review":
        raise HTTPException(status_code=400, detail=f"Cannot approve batch with status {batch.status}")

    batch.status = "approved"
    batch.approved_at = datetime.utcnow()
    batch.approved_by = "bonny-local"
    batch.updated_at = datetime.utcnow()
    db.commit()
    return ApproveResponse(batch_id=batch.id, status=batch.status, message="Batch approved")


@router.post("/batches/approve-selected", response_model=BulkApproveResponse)
def approve_selected_batches(
    request: BulkApproveRequest,
    db: Session = Depends(get_db),
):
    approved = []
    skipped = []
    errors = []
    batches = {
        batch.id: batch
        for batch in db.query(IngestBatch)
        .filter(IngestBatch.id.in_(set(request.batch_ids)))
        .all()
    }

    for batch_id in dict.fromkeys(request.batch_ids):
        batch = batches.get(batch_id)
        if not batch:
            skipped.append(batch_id)
            errors.append(BulkApproveError(batch_id=batch_id, reason="not_found"))
            continue

        metadata = batch.metadata_json or {}
        quality = metadata.get("metadata_quality", "weak")
        warnings = set(metadata.get("metadata_warnings", []))
        if batch.status in {"needs_metadata_review", "metadata_recovery"} or quality in {
            "weak",
            "broken",
        }:
            reason = "metadata_not_confirmed"
        elif warnings & BLOCKING_APPROVAL_WARNINGS:
            reason = "blocking_warning"
        elif batch.status != "pending_review":
            reason = f"invalid_status:{batch.status}"
        else:
            batch.status = "approved"
            batch.approved_at = datetime.utcnow()
            batch.approved_by = "bonny-local"
            batch.updated_at = datetime.utcnow()
            approved.append(batch_id)
            continue

        skipped.append(batch_id)
        errors.append(BulkApproveError(batch_id=batch_id, reason=reason))

    db.commit()
    return BulkApproveResponse(
        approved=approved,
        skipped=skipped,
        errors=errors,
    )


@router.post("/batches/{batch_id}/reject", response_model=ApproveResponse)
def reject_batch(batch_id: int, db: Session = Depends(get_db)):
    batch = db.get(IngestBatch, batch_id)
    if not batch:
        raise HTTPException(status_code=404, detail="Batch not found")
    if batch.status in {"moved", "merged"}:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot reject batch with status {batch.status}",
        )
    batch.status = "rejected"
    batch.updated_at = datetime.utcnow()
    db.commit()
    return ApproveResponse(batch_id=batch.id, status=batch.status, message="Batch rejected")


@router.post("/batches/{batch_id}/recovery", response_model=ApproveResponse)
def send_to_recovery(batch_id: int, db: Session = Depends(get_db)):
    batch = db.get(IngestBatch, batch_id)
    if not batch:
        raise HTTPException(status_code=404, detail="Batch not found")
    batch.status = "metadata_recovery"
    batch.updated_at = datetime.utcnow()
    db.commit()
    return ApproveResponse(batch_id=batch.id, status=batch.status, message="Batch sent to metadata recovery")


@router.post("/move/approved", response_model=MoveResponse)
def move_approved(db: Session = Depends(get_db)):
    moved, errors = move_approved_batches(db)
    return MoveResponse(moved=moved, errors=errors)


@router.get("/library")
def library(db: Session = Depends(get_db)):
    items = db.query(ArchiveItem).order_by(ArchiveItem.created_at.desc()).all()
    return items


def _batch_to_summary(
    batch: IngestBatch,
    *,
    action_message: str | None = None,
) -> BatchSummary:
    meta = batch.metadata_json or {}
    return BatchSummary(
        id=batch.id,
        detected_type=batch.detected_type,
        status=batch.status,
        artist=meta.get("artist") or meta.get("albumartist"),
        album=meta.get("album"),
        year=str(meta.get("year") or meta.get("date") or "")[:4] or None,
        primary_genre=meta.get("genre"),
        format=meta.get("format") or ", ".join(meta.get("format_summary", [])) or "MP3",
        track_count=meta.get("track_count", 0),
        album_count=meta.get("album_count", 0),
        disc_count=meta.get("disc_count", 1),
        confidence=batch.confidence,
        metadata_quality=meta.get("metadata_quality", "weak"),
        metadata_warnings=meta.get("metadata_warnings", []),
        suggested_destination=batch.suggested_destination,
        suggested_metadata=batch.suggested_metadata,
        metadata_confirmed=batch.metadata_confirmed,
        action_message=action_message,
        created_at=batch.created_at,
    )
