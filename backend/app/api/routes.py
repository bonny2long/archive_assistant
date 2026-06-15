import json
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
    AudiobookMetadataUpdate,
    BookCollectionReviewUpdate,
    BookMetadataUpdate,
    DiscographyMetadataUpdate,
    DevResetResponse,
    IngestBatchOut, 
    IngestFileOut,
    LibrarySummary,
    MovieCollectionReviewUpdate,
    MovieMetadataUpdate,
    MoveActionOut,
    MoveResponse,
    PaginatedResponse,
    ScanMusicResponse,
    TvMetadataUpdate,
    TvEpisodeReviewUpdate,
    ReviewConfirmationUpdate,
)
from app.services.dev_reset import (
    DevResetBlockedError,
    reset_music_test_data,
    reset_test_data,
)
from app.services.batch_display import build_batch_display_fields
from app.services.batch_merge import (
    find_archived_duplicate_candidate,
    find_merge_candidate_batches,
    merge_music_batches,
)
from app.services.music_metadata import (
    canonical_album_key,
    canonical_artist_key,
    clean_compilation_artist,
    evaluate_music_album_metadata,
    is_compilation_artist,
    music_track_filename,
    music_track_numbers,
    sort_music_tracks,
    suggest_music_destination,
)
from app.services.scanner import scan_music_ingest
from app.services.mover import _lock_metadata_for_move, move_approved_batches
from app.services.quarantine import quarantine_batch, restore_quarantined_batch
from app.services.video_metadata import safe_movie_path_part, safe_tv_path_part
from app.services.tv_review import apply_tv_episode_review_patches, sync_tv_episode_metadata_to_ingest_files
from app.services.review_items import (
    build_review_items_for_movie_collection,
)
from app.services.review_state import build_review_state
from app.services.book_metadata import (
    book_destination,
    build_book_item_destination,
)
from app.services.title_display import clean_display_title, destination_title
from app.services.metadata_candidates import (
    METADATA_ASSIST_VERSION,
    normalize_metadata_text,
)
from app.services.audiobook_metadata import audiobook_destination
from app.core.config import settings
from app.core.time import configured_timezone, now_local, now_utc, serialize_utc

router = APIRouter(prefix="/api")

@router.get("/health")
def health():
    return {
        "status": "ok",
        "service": "archive-assistant",
        "debug": settings.debug,
        "dev_tools_enabled": settings.debug and settings.dev_tools_enabled,
    }


@router.get("/system/time")
def system_time():
    utc_now = now_utc()
    return {
        "server_utc": serialize_utc(utc_now),
        "server_timezone": configured_timezone(),
        "server_local": now_local().isoformat(),
        "source": "server_clock",
    }


@router.post("/scan/music", response_model=ScanMusicResponse)
def scan_music(db: Session = Depends(get_db)):
    result = scan_music_ingest(db)
    return ScanMusicResponse(
        created=result.created,
        skipped_duplicates=result.skipped_duplicates,
        batches=result.batches,
        music_albums_found=result.music_albums_found,
        discographies_found=result.discographies_found,
        unknown_items=result.unknown_items,
        unsupported_files=result.unsupported_files,
        ignored_system_files=result.ignored_system_files,
        artwork_files_found=result.artwork_files_found,
        movie_batches_found=result.movie_batches_found,
        tv_shows_found=result.tv_shows_found,
        tv_episodes_found=result.tv_episodes_found,
        subtitle_files_found=result.subtitle_files_found,
        book_batches_found=result.book_batches_found,
        book_files_found=result.book_files_found,
        audiobook_batches_found=result.audiobook_batches_found,
        audiobook_files_found=result.audiobook_files_found,
    )


@router.post("/dev/reset/music-test", response_model=DevResetResponse)
def dev_reset_music_test(db: Session = Depends(get_db)):
    """Compatibility route for older clients."""
    if not (settings.debug and settings.dev_tools_enabled):
        raise HTTPException(status_code=404, detail="Dev reset is not available")
    try:
        summary = reset_music_test_data(db, apply=True)
    except DevResetBlockedError as exc:
        raise HTTPException(status_code=409, detail=exc.errors) from exc
    return DevResetResponse(**summary.__dict__)


@router.post("/dev/reset/test-data", response_model=DevResetResponse)
def dev_reset_test_data(db: Session = Depends(get_db)):
    if not (settings.debug and settings.dev_tools_enabled):
        raise HTTPException(status_code=404, detail="Dev reset is not available")
    try:
        summary = reset_test_data(db, apply=True)
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
    batch.metadata_json = build_review_state(
        batch.detected_type,
        batch.metadata_json,
    )
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
    ordered_files = sort_music_tracks(
        [
            ingest_file
            for ingest_file in batch.files
            if ingest_file.detected_role != "artwork"
        ]
    )
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
    batch = db.get(IngestBatch, batch_id)
    if not batch:
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
        manifest=(batch.metadata_json or {}).get("move_manifest"),
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
        moved_batches=moved_albums,
        moved_files=moved_tracks,
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

    meta = build_review_state(batch.detected_type, batch.metadata_json)
    
    # Update core fields
    raw_artist = update.artist.strip()
    display_artist, artist_cleanup = clean_compilation_artist(raw_artist)
    meta["artist"] = display_artist
    meta["albumartist"] = display_artist
    if artist_cleanup:
        meta["raw_artist"] = raw_artist
        meta["display_artist"] = display_artist
        meta["artist_cleanup"] = artist_cleanup
        meta["is_compilation"] = True
    meta["album"] = update.album.strip()
    year = update.year.strip() if update.year else ""
    meta["year"] = year
    meta["date"] = year
    meta["accepted_unknown_album_artist"] = (
        update.accepted_unknown_album_artist
    )
    meta["accepted_unknown_album_title"] = (
        update.accepted_unknown_album_title
    )
    meta["accepted_unknown_year"] = update.accepted_unknown_year
    meta["lookup_later"] = update.lookup_later
    meta["review_type"] = "music_album"
    meta["review_mode"] = "single_album"
    meta["metadata_assist_version"] = METADATA_ASSIST_VERSION
    meta.pop("metadata_alerts", None)
    if update.primary_genre is not None:
        meta["genre"] = update.primary_genre.strip() or "Unknown"
    if update.format is not None:
        meta["format"] = update.format.strip().upper()
    if update.note is not None:
        meta["review_note"] = update.note.strip() or None
    
    # Re-evaluate quality
    quality_res = evaluate_music_album_metadata(meta)
    meta.update(quality_res)
    if any((
        update.accepted_unknown_album_artist,
        update.accepted_unknown_album_title,
        update.accepted_unknown_year,
    )):
        meta["metadata_quality"] = "accepted_with_unknowns"
        meta["confidence"] = max(float(meta.get("confidence") or 0), 0.75)
    if artist_cleanup:
        warnings = list(meta.get("metadata_warnings", []))
        warnings.extend(["compilation_detected", "compilation_prefix_removed"])
        meta["metadata_warnings"] = list(dict.fromkeys(warnings))
    
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
    
    meta["review_confirmed"] = True
    meta = build_review_state(batch.detected_type, meta)
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
    batch.confidence = meta["confidence"]
    batch.metadata_confirmed = not bool(meta["blocking_review_items"])

    if not meta["blocking_review_items"]:
        batch.status = "pending_review"
    elif quality_res["metadata_quality"] == "broken":
        batch.status = "metadata_recovery"
    else:
        batch.status = "needs_metadata_review"
    
    batch.updated_at = now_utc()
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


@router.patch("/batches/{batch_id}/movie-metadata", response_model=BatchSummary)
def update_movie_metadata(
    batch_id: int,
    update: MovieMetadataUpdate,
    db: Session = Depends(get_db),
):
    batch = db.get(IngestBatch, batch_id)
    if not batch:
        raise HTTPException(status_code=404, detail="Batch not found")
    if batch.detected_type != "video_movie":
        raise HTTPException(status_code=400, detail="Batch is not a movie")
    if batch.status in {"moved", "merged"}:
        raise HTTPException(status_code=400, detail="Moved batches cannot be edited")

    title = update.title.strip()
    if not title:
        raise HTTPException(status_code=422, detail="Movie title is required")
    year = normalize_metadata_text(update.year) if update.year else None
    edition = update.edition.strip() if update.edition else None
    movie_format = update.format.strip().upper() if update.format else None
    metadata = dict(batch.metadata_json or {})
    warnings = [
        warning
        for warning in metadata.get("metadata_warnings", [])
        if warning not in {"movie_year_missing", "movie_destination_exists"}
    ]
    if not year:
        warnings.append("movie_year_missing")
    metadata["metadata_alerts"] = [
        alert
        for alert in (metadata.get("metadata_alerts") or [])
        if not (
            isinstance(alert, dict)
            and alert.get("type") == "movie_destination_exists"
        )
    ]

    metadata.update(
        {
            "title": title,
            "year": year,
            "edition": edition,
            "accepted_unknown_title": update.accepted_unknown_title,
            "accepted_unknown_year": update.accepted_unknown_year,
            "lookup_later": update.lookup_later,
            "review_type": "movie",
            "review_mode": "single_item",
            "metadata_assist_version": METADATA_ASSIST_VERSION,
            "metadata_quality": (
                "accepted_with_unknowns"
                if update.accepted_unknown_title
                or update.accepted_unknown_year
                else "good" if year else "weak"
            ),
            "metadata_warnings": warnings,
            "confidence": 1.0 if year else 0.65,
        }
    )
    if movie_format:
        metadata["format"] = movie_format

    folder = safe_movie_path_part(
        f"{year or 'Unknown Year'} - {title}"
        if not edition
        else f"{year or 'Unknown Year'} - {title} [{edition}]"
    )
    metadata["review_confirmed"] = True
    metadata = build_review_state(batch.detected_type, metadata)
    batch.metadata_json = metadata
    batch.suggested_metadata = {
        "title": title,
        "year": year,
        "edition": edition,
        "format": metadata.get("format"),
        "sources": {
            "title": "manual correction",
            "year": "manual correction",
            "edition": "manual correction",
            "format": "manual correction",
        },
    }
    batch.suggested_destination = str(settings.movies_dir / folder)
    batch.confidence = metadata["confidence"]
    if metadata["blocking_review_items"]:
        batch.metadata_confirmed = False
        batch.status = "needs_metadata_review"
    else:
        batch.metadata_confirmed = True
        batch.status = "pending_review"
    batch.updated_at = now_utc()
    db.commit()
    return _batch_to_summary(batch, action_message="Movie metadata saved.")


@router.patch("/batches/{batch_id}/movie-collection-review", response_model=BatchSummary)
def update_movie_collection_review(
    batch_id: int,
    update: MovieCollectionReviewUpdate,
    db: Session = Depends(get_db),
):
    batch = (
        db.query(IngestBatch)
        .options(selectinload(IngestBatch.files))
        .filter(IngestBatch.id == batch_id)
        .first()
    )
    if not batch:
        raise HTTPException(status_code=404, detail="Batch not found")
    if batch.detected_type != "video_movie":
        raise HTTPException(status_code=400, detail="Batch is not a movie")
    if batch.status in {"moved", "merged"}:
        raise HTTPException(status_code=400, detail="Moved batches cannot be edited")

    metadata = dict(batch.metadata_json or {})

    # Normalize movie_items from the submitted update
    movie_items = []
    destination_parts = []
    for movie_update in update.movies:
        existing_item = next(
            (
                item
                for item in metadata.get("movie_items", [])
                if isinstance(item, dict)
                and str(item.get("source_file") or "").casefold()
                == movie_update.source_file.casefold()
            ),
            {},
        )
        title = movie_update.title.strip()
        year = movie_update.year.strip() if movie_update.year else ""
        edition = movie_update.edition.strip() if movie_update.edition else None
        fmt = movie_update.format.strip().upper() if movie_update.format else None
        include = bool(movie_update.include)

        destination_title = title or "Unknown Movie"
        destination_year = year or "Unknown Year"
        dest_label = (
            f"{destination_year} - {destination_title}"
            if not edition
            else f"{destination_year} - {destination_title} [{edition}]"
        )
        dest = f"Movies/Library/{safe_movie_path_part(dest_label)}"
        destination_parts.append(dest)

        movie_items.append(
            {
                "item_kind": "movie",
                "source_key": movie_update.source_file,
                "source_file": movie_update.source_file,
                "include": include,
                "title": title or "Unknown Movie",
                "year": year or None,
                "edition": edition,
                "format": fmt,
                "resolution": existing_item.get("resolution"),
                "source": existing_item.get("source"),
                "accepted_unknown_title": movie_update.accepted_unknown_title,
                "accepted_unknown_year": movie_update.accepted_unknown_year,
                "lookup_later": movie_update.lookup_later,
                "metadata_candidates": existing_item.get(
                    "metadata_candidates",
                    {},
                ),
                "release_cleanup": existing_item.get(
                    "release_cleanup",
                    {},
                ),
                "destination_preview": dest if include else None,
            }
        )

    metadata["movie_items"] = movie_items
    metadata["review_type"] = "movie_collection"
    metadata["review_mode"] = "item_list"
    metadata["metadata_assist_version"] = METADATA_ASSIST_VERSION

    if update.collection_title:
        metadata["collection_title"] = update.collection_title.strip()

    warnings = [
        w for w in metadata.get("metadata_warnings", [])
        if w != "multiple_movie_candidates"
    ]
    metadata["metadata_warnings"] = warnings

    metadata["confidence"] = 0.8

    if update.confirm_non_blocking_warnings:
        metadata["review_confirmed"] = True

    metadata = build_review_state(batch.detected_type, metadata)

    if metadata.get("blocking_review_items"):
        batch.status = "needs_metadata_review"
        metadata["metadata_quality"] = "weak"
        metadata["confidence"] = 0.7
    else:
        metadata["metadata_quality"] = (
            "accepted_with_unknowns"
            if any(
                item.get("accepted_unknown_title")
                or item.get("accepted_unknown_year")
                for item in movie_items
            )
            else "reviewed"
        )
        metadata["review_confirmed"] = True
        metadata["confidence"] = 1.0
        if batch.status in {"needs_metadata_review", "pending_review"}:
            batch.status = "pending_review"

    batch.metadata_json = metadata
    batch.metadata_confirmed = not bool(metadata.get("blocking_review_items"))
    batch.confidence = metadata["confidence"]
    batch.updated_at = now_utc()
    db.commit()
    return _batch_to_summary(batch, action_message="Movie collection review saved.")


@router.patch("/batches/{batch_id}/book-metadata", response_model=BatchSummary)
def update_book_metadata(
    batch_id: int,
    update: BookMetadataUpdate,
    db: Session = Depends(get_db),
):
    batch = db.get(IngestBatch, batch_id)
    if not batch:
        raise HTTPException(status_code=404, detail="Batch not found")
    if batch.detected_type != "book":
        raise HTTPException(status_code=400, detail="Batch is not a book")
    if batch.status in {"moved", "merged"}:
        raise HTTPException(status_code=400, detail="Moved batches cannot be edited")

    title = normalize_metadata_text(update.title)
    author = normalize_metadata_text(update.author)
    year = update.year.strip() if update.year else None
    metadata = dict(batch.metadata_json or {})
    book_format = (
        update.format.strip().upper()
        if update.format
        else str(metadata.get("format") or "EPUB").upper()
    )
    destination = book_destination(
        book_format,
        author,
        title,
        year,
        settings.books_dir,
    )
    warnings = [
        warning
        for warning in metadata.get("metadata_warnings", [])
        if warning not in {
            "book_author_missing",
            "book_title_missing",
            "book_year_missing",
            "book_year_invalid",
        }
    ]
    if not year:
        warnings.append("book_year_missing")
    metadata.update({
        "review_type": "book",
        "review_mode": "single_item",
        "author": author,
        "title": title,
        "metadata_title": title,
        "display_title": clean_display_title(title),
        "destination_title": destination_title(title),
        "year": year,
        "format": book_format,
        "book_format": book_format,
        "note": update.note.strip() if update.note else None,
        "suggested_destination_preview": str(destination),
        "metadata_quality": "good",
        "metadata_warnings": list(dict.fromkeys(warnings)),
        "confidence": 1.0,
        "review_confirmed": True,
    })
    metadata = build_review_state("book", metadata)
    batch.metadata_json = metadata
    batch.suggested_metadata = {
        "metadata_assist_version": METADATA_ASSIST_VERSION,
        "author": author,
        "title": title,
        "year": year,
        "format": book_format,
        "sources": {
            "author": "manual correction",
            "title": "manual correction",
            "year": "manual correction",
            "format": "manual correction",
        },
    }
    batch.suggested_destination = str(destination)
    batch.metadata_confirmed = not bool(metadata["blocking_review_items"])
    batch.confidence = metadata["confidence"]
    batch.status = (
        "needs_metadata_review"
        if metadata["blocking_review_items"]
        else "pending_review"
    )
    batch.updated_at = now_utc()
    db.commit()
    return _batch_to_summary(batch, action_message="Book metadata saved.")


@router.patch("/batches/{batch_id}/book-collection-review", response_model=BatchSummary)
def update_book_collection_review(
    batch_id: int,
    update: BookCollectionReviewUpdate,
    db: Session = Depends(get_db),
):
    batch = db.get(IngestBatch, batch_id)
    if not batch:
        raise HTTPException(status_code=404, detail="Batch not found")
    if batch.detected_type != "book":
        raise HTTPException(status_code=400, detail="Batch is not a book")
    if batch.status in {"moved", "merged"}:
        raise HTTPException(status_code=400, detail="Moved batches cannot be edited")

    metadata = dict(batch.metadata_json or {})
    collection_title = (
        update.collection_title.strip()
        if update.collection_title
        else None
    )
    keep_together = bool(update.keep_collection_together)
    if keep_together and not collection_title:
        raise HTTPException(
            status_code=400,
            detail="Collection label is required when keeping a collection together.",
        )
    items = []
    existing_items = {
        str(item.get("source_file") or ""): item
        for item in metadata.get("book_items", [])
        if isinstance(item, dict)
    }
    for item in update.books:
        title = normalize_metadata_text(item.title)
        author = normalize_metadata_text(item.author)
        year = normalize_metadata_text(item.year) if item.year else None
        book_format = (
            item.format.strip().upper()
            if item.format
            else Path(item.source_file).suffix.lstrip(".").upper() or "EPUB"
        )
        item_metadata = {
            "item_kind": "book",
            "source_key": item.source_file,
            "source_file": item.source_file,
            "include": bool(item.include),
            "author": author,
            "title": title,
            "metadata_title": title,
            "display_title": clean_display_title(title),
            "destination_title": destination_title(title),
            "year": year,
            "series": (
                normalize_metadata_text(item.series)
                if item.series
                else None
            ),
            "series_index": (
                normalize_metadata_text(item.series_index)
                if item.series_index
                else None
            ),
            "format": book_format,
            "metadata_candidates": dict(
                existing_items.get(item.source_file, {}).get(
                    "metadata_candidates",
                    {},
                )
            ),
            "candidate_notes": list(
                existing_items.get(item.source_file, {}).get(
                    "candidate_notes",
                    [],
                )
            ),
            "candidate_runtime": dict(
                existing_items.get(item.source_file, {}).get(
                    "candidate_runtime",
                    {},
                )
            ),
            "matched_artwork": existing_items.get(
                item.source_file, {}
            ).get("matched_artwork"),
            "alternate_formats": list(
                existing_items.get(item.source_file, {}).get(
                    "alternate_formats",
                    [],
                )
            ),
            "accepted_unknown_author": bool(
                item.accepted_unknown_author
            ),
            "accepted_unknown_year": bool(item.accepted_unknown_year),
            "lookup_later": bool(item.lookup_later),
        }
        destination = build_book_item_destination(
            books_root=settings.books_dir,
            item=item_metadata,
            collection_title=collection_title,
            keep_collection_together=keep_together,
        )
        item_metadata["destination_path"] = (
            str(destination) if item.include else None
        )
        item_metadata["destination_preview"] = (
            destination.relative_to(settings.data_root).as_posix()
            if item.include
            else None
        )
        items.append(item_metadata)

    collection_root = None
    first_included = next(
        (item for item in items if item.get("include", True)),
        None,
    )
    if keep_together and first_included:
        first_destination = build_book_item_destination(
            books_root=settings.books_dir,
            item=first_included,
            collection_title=collection_title,
            keep_collection_together=True,
        )
        collection_root = (
            first_destination.parent.relative_to(settings.data_root).as_posix()
        )
    metadata.update({
        "review_type": "book_collection",
        "review_mode": "item_list",
        "collection_title": collection_title,
        "keep_collection_together": keep_together,
        "collection_destination_root": collection_root,
        "book_items": items,
        "metadata_warnings": [
            warning
            for warning in metadata.get("metadata_warnings", [])
            if warning != "multiple_book_candidates"
        ],
        "confidence": 0.8,
    })
    collection_summary = dict(metadata.get("collection_summary") or {})
    collection_summary["included_book_count"] = sum(
        item.get("include", True) for item in items
    )
    collection_summary["needs_repair_count"] = sum(
        item.get("include", True)
        and (
            (
                str(item.get("author") or "").casefold()
                == "unknown author"
                and not item.get("accepted_unknown_author", False)
            )
            or str(item.get("title") or "").casefold() == "unknown title"
        )
        for item in items
    )
    collection_summary["accepted_unknown_count"] = sum(
        item.get("include", True)
        and item.get("accepted_unknown_author", False)
        for item in items
    )
    collection_summary["lookup_later_count"] = sum(
        item.get("include", True) and item.get("lookup_later", False)
        for item in items
    )
    metadata["collection_summary"] = collection_summary
    if update.confirm_non_blocking_warnings:
        metadata["review_confirmed"] = True
    metadata = build_review_state("book", metadata)
    if metadata["blocking_review_items"]:
        metadata["metadata_quality"] = "weak"
        batch.status = "needs_metadata_review"
    else:
        metadata["metadata_quality"] = (
            "accepted_with_unknowns"
            if any(
                item.get("include", True)
                and (
                    item.get("accepted_unknown_author", False)
                    or item.get("accepted_unknown_year", False)
                )
                for item in items
            )
            else "reviewed"
        )
        metadata["review_confirmed"] = True
        metadata["confidence"] = 1.0
        batch.status = "pending_review"
    batch.metadata_json = metadata
    batch.metadata_confirmed = not bool(metadata["blocking_review_items"])
    batch.confidence = metadata["confidence"]
    batch.updated_at = now_utc()
    db.commit()
    return _batch_to_summary(
        batch,
        action_message="Book collection review saved.",
    )


@router.patch("/batches/{batch_id}/audiobook-metadata", response_model=BatchSummary)
def update_audiobook_metadata(
    batch_id: int,
    update: AudiobookMetadataUpdate,
    db: Session = Depends(get_db),
):
    batch = db.get(IngestBatch, batch_id)
    if not batch:
        raise HTTPException(status_code=404, detail="Batch not found")
    if batch.detected_type != "audiobook":
        raise HTTPException(status_code=400, detail="Batch is not an audiobook")
    if batch.status in {"moved", "merged"}:
        raise HTTPException(status_code=400, detail="Moved batches cannot be edited")

    author = normalize_metadata_text(update.author)
    title = normalize_metadata_text(update.title)
    year = normalize_metadata_text(update.year) if update.year else None
    narrator = (
        normalize_metadata_text(update.narrator)
        if update.narrator
        else None
    )
    series = (
        normalize_metadata_text(update.series)
        if update.series
        else None
    )
    series_index = (
        normalize_metadata_text(update.series_index)
        if update.series_index
        else None
    )
    metadata = dict(batch.metadata_json or {})
    audio_format = (
        update.format.strip().upper()
        if update.format
        else str(metadata.get("format") or "MP3").upper()
    )
    destination = audiobook_destination(
        audiobooks_root=settings.audiobooks_dir,
        author=author,
        title=title,
        year=year,
    )
    warnings = [
        warning
        for warning in metadata.get("metadata_warnings", [])
        if warning not in {
            "audiobook_author_missing",
            "audiobook_title_missing",
            "audiobook_year_missing",
            "audiobook_year_invalid",
            "audiobook_narrator_missing",
        }
    ]
    if not year:
        warnings.append("audiobook_year_missing")
    if not narrator:
        warnings.append("audiobook_narrator_missing")
    metadata.update({
        "media_kind": "audiobook",
        "review_type": "audiobook",
        "review_mode": "single_item",
        "author": author,
        "title": title,
        "year": year,
        "narrator": narrator,
        "series": series,
        "series_index": series_index,
        "format": audio_format,
        "note": update.note.strip() if update.note else None,
        "accepted_unknown_author": bool(update.accepted_unknown_author),
        "accepted_unknown_year": bool(update.accepted_unknown_year),
        "accepted_unknown_narrator": bool(
            update.accepted_unknown_narrator
        ),
        "lookup_later": bool(update.lookup_later),
        "suggested_destination_preview": str(destination),
        "metadata_quality": "good",
        "metadata_warnings": list(dict.fromkeys(warnings)),
        "confidence": 1.0,
        "review_confirmed": True,
    })
    metadata = build_review_state("audiobook", metadata)
    batch.metadata_json = metadata
    batch.suggested_metadata = {
        "author": author,
        "title": title,
        "year": year,
        "narrator": narrator,
        "series": series,
        "series_index": series_index,
        "format": audio_format,
        "sources": {
            "author": "manual correction",
            "title": "manual correction",
            "year": "manual correction",
            "narrator": "manual correction",
            "series": "manual correction",
            "series_index": "manual correction",
            "format": "manual correction",
        },
        "accepted_unknown_author": bool(update.accepted_unknown_author),
        "accepted_unknown_year": bool(update.accepted_unknown_year),
        "accepted_unknown_narrator": bool(
            update.accepted_unknown_narrator
        ),
        "lookup_later": bool(update.lookup_later),
    }
    batch.suggested_destination = str(destination)
    batch.metadata_confirmed = not bool(metadata["blocking_review_items"])
    batch.confidence = metadata["confidence"]
    batch.status = (
        "needs_metadata_review"
        if metadata["blocking_review_items"]
        else "pending_review"
    )
    batch.updated_at = now_utc()
    db.commit()
    return _batch_to_summary(
        batch,
        action_message="Audiobook metadata saved.",
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
    metadata["accepted_unknown_discography_artist"] = (
        update.accepted_unknown_discography_artist
    )
    metadata["lookup_later"] = update.lookup_later
    metadata["review_type"] = "music_discography"
    metadata["review_mode"] = "album_list"
    metadata["metadata_assist_version"] = METADATA_ASSIST_VERSION
    updates_by_source = {
        item.source_folder: item
        for item in (update.albums or [])
    }
    albums = []
    for album in metadata.get("albums", []):
        album_copy = dict(album)
        album_copy["artist"] = artist
        correction = updates_by_source.get(
            str(album_copy.get("source_folder") or "")
        )
        if correction:
            included = correction.include and correction.release_type != "exclude"
            album_copy["album"] = correction.album.strip()
            album_copy["year"] = correction.year
            album_copy["release_type"] = correction.release_type
            album_copy["include"] = included
            album_copy["accepted_unknown_album_artist"] = (
                correction.accepted_unknown_album_artist
            )
            album_copy["accepted_unknown_album_title"] = (
                correction.accepted_unknown_album_title
            )
            album_copy["accepted_unknown_year"] = (
                correction.accepted_unknown_year
            )
            album_copy["lookup_later"] = correction.lookup_later
            album_warnings = [
                warning
                for warning in album_copy.get("warnings", [])
                if warning not in {"album_missing_year", "album_missing_title"}
            ]
            if (
                included
                and not correction.year
                and not correction.accepted_unknown_year
            ):
                album_warnings.append("album_missing_year")
            album_copy["warnings"] = list(dict.fromkeys(album_warnings))
            album_copy["status"] = (
                "excluded"
                if not included
                else "needs_review"
                if "album_missing_year" in album_copy["warnings"]
                else "warning"
                if album_copy["warnings"]
                else "ready"
            )
        albums.append(album_copy)
    metadata["albums"] = albums
    metadata["album_count"] = sum(
        bool(album.get("include", True))
        for album in albums
    )
    metadata["release_count"] = metadata["album_count"]
    metadata["artist_source"] = "manual correction"
    for ingest_file in batch.files:
        track_metadata = dict(ingest_file.metadata_json or {})
        album_metadata = dict(track_metadata.get("_discography_album") or {})
        correction = updates_by_source.get(
            str(album_metadata.get("source_folder") or "")
        )
        if not correction:
            continue
        included = correction.include and correction.release_type != "exclude"
        album_metadata["album"] = correction.album.strip()
        album_metadata["year"] = correction.year
        album_metadata["release_type"] = correction.release_type
        album_metadata["include"] = included
        album_metadata["accepted_unknown_album_artist"] = (
            correction.accepted_unknown_album_artist
        )
        album_metadata["accepted_unknown_album_title"] = (
            correction.accepted_unknown_album_title
        )
        album_metadata["accepted_unknown_year"] = (
            correction.accepted_unknown_year
        )
        album_metadata["lookup_later"] = correction.lookup_later
        track_metadata["_discography_album"] = album_metadata
        ingest_file.metadata_json = track_metadata
    warnings = [
        warning
        for warning in metadata.get("metadata_warnings", [])
        if warning not in {
            "artist_missing",
            "child_album_metadata_missing",
            "destination_file_conflict",
            "discography_destination_exists",
        }
    ]
    metadata["metadata_alerts"] = [
        alert
        for alert in metadata.get("metadata_alerts", [])
        if not (
            isinstance(alert, dict)
            and alert.get("type") in {
                "destination_file_conflict",
                "discography_destination_exists",
            }
        )
    ]
    blocking = any(
        album.get("include", True)
        and (
            (
                not album.get("album")
                and not album.get("accepted_unknown_album_title")
            )
        )
        for album in albums
    )
    if blocking:
        warnings.append("child_album_metadata_missing")
    metadata["metadata_warnings"] = warnings
    accepted_unknowns = bool(
        update.accepted_unknown_discography_artist
        or any(
            album.get("accepted_unknown_album_artist")
            or album.get("accepted_unknown_album_title")
            or album.get("accepted_unknown_year")
            for album in albums
        )
    )
    metadata["metadata_quality"] = (
        "weak"
        if blocking
        else "accepted_with_unknowns"
        if accepted_unknowns
        else "good"
    )
    metadata["confidence"] = 0.6 if blocking else 1.0
    metadata["review_confirmed"] = True
    metadata = build_review_state(batch.detected_type, metadata)

    batch.metadata_json = metadata
    batch.suggested_metadata = {
        "artist": artist,
        "sources": {"artist": "manual correction"},
    }
    batch.suggested_destination = str(settings.music_discographies_dir / artist)
    batch.metadata_confirmed = not bool(metadata["blocking_review_items"])
    batch.confidence = metadata["confidence"]
    batch.status = (
        "needs_metadata_review"
        if metadata["blocking_review_items"]
        else "pending_review"
    )
    batch.updated_at = now_utc()
    db.commit()
    return _batch_to_summary(batch, action_message="Discography metadata saved.")


@router.patch("/batches/{batch_id}/tv-metadata", response_model=BatchSummary)
def update_tv_metadata(
    batch_id: int,
    update: TvMetadataUpdate,
    db: Session = Depends(get_db),
):
    batch = db.get(IngestBatch, batch_id)
    if not batch:
        raise HTTPException(status_code=404, detail="Batch not found")
    if batch.detected_type != "video_tv_show":
        raise HTTPException(status_code=400, detail="Batch is not a TV show")
    if batch.status in {"moved", "merged"}:
        raise HTTPException(status_code=400, detail="Moved batches cannot be edited")

    show_title = update.show_title.strip()
    if not show_title:
        raise HTTPException(status_code=422, detail="TV show title is required")
    year = update.year.strip() if update.year else None
    season_title = update.season_title.strip() if update.season_title else None
    metadata = dict(batch.metadata_json or {})
    seasons = [
        dict(season)
        for season in metadata.get("seasons", [])
        if isinstance(season, dict)
    ]
    season_number = update.season_number
    if season_number is None and len(seasons) == 1:
        season_number = seasons[0].get("season_number")
    if season_number is not None:
        all_episodes = []
        for season in seasons:
            for episode_value in season.get("episodes", []):
                episode = dict(episode_value)
                episode["season_number"] = season_number
                if episode.get("episode_number") is not None:
                    episode["episode_code"] = (
                        f"S{season_number:02d}"
                        f"E{int(episode['episode_number']):02d}"
                    )
                all_episodes.append(episode)
        seasons = [{
            "season_number": season_number,
            "season_title": season_title,
            "episode_count": len(all_episodes),
            "episodes": all_episodes,
        }]
        for ingest_file in batch.files:
            if ingest_file.detected_role not in {"tv_episode", "tv_subtitle"}:
                continue
            file_metadata = dict(ingest_file.metadata_json or {})
            file_metadata["season_number"] = season_number
            if file_metadata.get("episode_number") is not None:
                file_metadata["episode_code"] = (
                    f"S{season_number:02d}"
                    f"E{int(file_metadata['episode_number']):02d}"
                )
            ingest_file.metadata_json = file_metadata
    metadata["seasons"] = seasons
    metadata["season_number"] = season_number
    metadata["season_count"] = len(seasons)
    metadata["season_title"] = season_title
    warnings = [
        warning
        for warning in metadata.get("metadata_warnings", [])
        if warning not in {
            "tv_show_title_missing",
            "tv_show_title_from_folder",
            "tv_metadata_review_required",
            "tv_destination_exists",
        }
    ]
    metadata["metadata_alerts"] = [
        alert
        for alert in (metadata.get("metadata_alerts") or [])
        if not (
            isinstance(alert, dict)
            and alert.get("type") == "tv_destination_exists"
        )
    ]
    parse_failed = any(
        episode.get("season_number") is None
        or episode.get("episode_number") is None
        for season in seasons
        for episode in season.get("episodes", [])
        if isinstance(episode, dict)
    )
    if not parse_failed:
        warnings = [
            warning
            for warning in warnings
            if warning != "tv_episode_parse_failed"
        ]
    metadata.update(
        {
            "show_title": show_title,
            "year": year,
            "metadata_quality": "weak" if parse_failed else "good",
            "metadata_warnings": warnings,
            "confidence": 0.65 if parse_failed else 1.0,
        }
    )
    metadata["review_confirmed"] = True
    metadata = build_review_state(batch.detected_type, metadata)
    batch.metadata_json = metadata
    batch.suggested_metadata = {
        "show_title": show_title,
        "year": year,
        "season_number": season_number,
        "season_title": season_title,
        "sources": {
            "show_title": "manual correction",
            "year": "manual correction",
            "season_number": "manual correction",
            "season_title": "manual correction",
        },
    }
    batch.suggested_destination = str(
        settings.tv_dir / safe_tv_path_part(show_title)
    )
    batch.metadata_confirmed = True
    batch.confidence = metadata["confidence"]
    batch.status = (
        "needs_metadata_review"
        if metadata["blocking_review_items"]
        else "pending_review"
    )
    batch.updated_at = now_utc()
    db.commit()
    return _batch_to_summary(batch, action_message="TV metadata saved.")


@router.patch("/batches/{batch_id}/tv-episode-review", response_model=BatchSummary)
def update_tv_episode_review(
    batch_id: int,
    update: TvEpisodeReviewUpdate,
    db: Session = Depends(get_db),
):
    batch = (
        db.query(IngestBatch)
        .options(selectinload(IngestBatch.files))
        .filter(IngestBatch.id == batch_id)
        .first()
    )
    if not batch:
        raise HTTPException(status_code=404, detail="Batch not found")
    if batch.detected_type != "video_tv_show":
        raise HTTPException(status_code=400, detail="Batch is not a TV show")
    if batch.status in {"moved", "merged"}:
        raise HTTPException(status_code=400, detail="Moved batches cannot be edited")

    metadata = dict(batch.metadata_json or {})

    if update.show_title is not None:
        stripped = update.show_title.strip()
        if stripped:
            metadata["show_title"] = stripped

    if update.year is not None:
        year = update.year.strip()
        metadata["year"] = year or None

    metadata, reviewed_episodes = apply_tv_episode_review_patches(
        metadata, batch.files, update.patches
    )

    unmatched = sync_tv_episode_metadata_to_ingest_files(
        batch.files, reviewed_episodes
    )

    if unmatched:
        warnings = list(metadata.get("metadata_warnings", []))
        warnings.append("tv_review_file_sync_unmatched")
        metadata["metadata_warnings"] = list(dict.fromkeys(warnings))
        metadata["tv_review_file_sync_unmatched"] = unmatched

    included_file_count = sum(
        1
        for item in batch.files
        if item.detected_role == "tv_episode"
        and (item.metadata_json or {}).get("include", True)
    )

    included_batch_count = sum(
        1
        for season in metadata.get("seasons", [])
        for episode in season.get("episodes", [])
        if episode.get("include", True)
    )

    if included_file_count != included_batch_count:
        warnings = list(metadata.get("metadata_warnings", []))
        warnings.append("tv_review_count_mismatch")
        metadata["metadata_warnings"] = list(dict.fromkeys(warnings))
        metadata["tv_review_count_mismatch"] = {
            "batch_episode_count": included_batch_count,
            "file_episode_count": included_file_count,
        }
        batch.status = "needs_metadata_review"

    if update.confirm_non_blocking_warnings:
        metadata["review_confirmed"] = True

    metadata = build_review_state(batch.detected_type, metadata)

    has_sync_errors = bool(unmatched)

    if metadata.get("blocking_review_items") or has_sync_errors:
        batch.status = "needs_metadata_review"
        metadata["metadata_quality"] = "weak"
    else:
        metadata["metadata_quality"] = "reviewed"
        metadata["review_confirmed"] = True
        if batch.status in {"needs_metadata_review", "pending_review"}:
            batch.status = "pending_review"

    batch.metadata_json = metadata
    batch.metadata_confirmed = True
    batch.suggested_metadata = {
        "show_title": metadata.get("show_title"),
        "year": metadata.get("year"),
        "sources": {
            "show_title": "manual review",
            "year": "manual review",
        },
    }
    show_title_safe = str(metadata.get("show_title") or "Unknown TV Show")
    batch.suggested_destination = str(
        settings.tv_dir / safe_tv_path_part(show_title_safe)
    )
    batch.confidence = metadata.get("confidence", 1.0)
    batch.updated_at = now_utc()
    db.commit()
    return _batch_to_summary(batch, action_message="TV episode review saved.")


@router.patch(
    "/batches/{batch_id}/review-confirmation",
    response_model=BatchSummary,
)
def update_review_confirmation(
    batch_id: int,
    update: ReviewConfirmationUpdate,
    db: Session = Depends(get_db),
):
    batch = db.get(IngestBatch, batch_id)
    if not batch:
        raise HTTPException(status_code=404, detail="Batch not found")
    if batch.detected_type in {"unknown_type", "unsupported_file"}:
        raise HTTPException(
            status_code=400,
            detail="Unknown items belong to quarantine review",
        )
    if batch.status in {"moved", "merged"}:
        raise HTTPException(status_code=400, detail="Moved batches cannot be confirmed")

    metadata = dict(batch.metadata_json or {})
    metadata["review_confirmed"] = update.confirmed
    metadata["review_note"] = update.note.strip() if update.note else None
    metadata["non_blocking_warnings_accepted"] = bool(
        update.confirmed and update.accept_non_blocking_warnings
    )
    metadata = build_review_state(batch.detected_type, metadata)
    batch.metadata_json = metadata
    batch.metadata_confirmed = bool(update.confirmed and not metadata["blocking_review_items"])
    if metadata["blocking_review_items"]:
        batch.status = "needs_metadata_review"
    elif update.confirmed:
        batch.status = "pending_review"
        if metadata["metadata_quality"] in {"weak", "broken"}:
            metadata["metadata_quality"] = "fair"
    elif batch.status == "pending_review":
        batch.status = "needs_metadata_review"
    batch.updated_at = now_utc()
    db.commit()
    return _batch_to_summary(
        batch,
        action_message=(
            "Review confirmed."
            if update.confirmed
            else "Review confirmation removed."
        ),
    )


@router.post("/batches/{batch_id}/approve", response_model=ApproveResponse)
def approve_batch(batch_id: int, db: Session = Depends(get_db)):
    batch = db.get(IngestBatch, batch_id)
    if not batch:
        raise HTTPException(status_code=404, detail="Batch not found")
    if batch.detected_type in {"unknown_type", "unsupported_file"}:
        raise HTTPException(status_code=400, detail="Unknown items cannot be approved")
    
    meta = build_review_state(batch.detected_type, batch.metadata_json)
    if meta["blocking_review_items"]:
        return ApproveResponse(
            batch_id=batch.id, 
            status=batch.status, 
            message="Batch requires metadata review before approval.",
            metadata_quality=meta.get("metadata_quality"),
            metadata_warnings=meta.get("metadata_warnings", [])
        )
    if batch.status in {"needs_metadata_review", "metadata_recovery"}:
        return ApproveResponse(
            batch_id=batch.id,
            status=batch.status,
            message="Batch review must be confirmed before approval.",
            metadata_quality=meta.get("metadata_quality"),
            metadata_warnings=meta.get("metadata_warnings", []),
        )

    if batch.status != "pending_review":
        raise HTTPException(status_code=400, detail=f"Cannot approve batch with status {batch.status}")

    batch.status = "approved"
    batch.approved_at = now_utc()
    batch.approved_by = "bonny-local"
    batch.updated_at = now_utc()
    _lock_metadata_for_move(batch)
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

        metadata = build_review_state(batch.detected_type, batch.metadata_json)
        if batch.detected_type in {"unknown_type", "unsupported_file"}:
            reason = "quarantine_review_required"
        elif metadata["blocking_review_items"]:
            reason = "blocking_review_items"
        elif batch.status in {"needs_metadata_review", "metadata_recovery"}:
            reason = "metadata_not_confirmed"
        elif batch.status != "pending_review":
            reason = f"invalid_status:{batch.status}"
        else:
            batch.status = "approved"
            batch.approved_at = now_utc()
            batch.approved_by = "bonny-local"
            batch.updated_at = now_utc()
            _lock_metadata_for_move(batch)
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
    batch.updated_at = now_utc()
    db.commit()
    return ApproveResponse(batch_id=batch.id, status=batch.status, message="Batch rejected")


@router.post("/batches/{batch_id}/quarantine", response_model=BatchSummary)
def quarantine_review_batch(batch_id: int, db: Session = Depends(get_db)):
    batch = db.get(IngestBatch, batch_id)
    if not batch:
        raise HTTPException(status_code=404, detail="Batch not found")
    try:
        destination = quarantine_batch(db, batch)
    except (ValueError, FileNotFoundError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return _batch_to_summary(
        batch,
        action_message=f"Moved to quarantine: {destination}",
    )


@router.get("/quarantine/review", response_model=list[BatchSummary])
def list_quarantine_review(db: Session = Depends(get_db)):
    batches = (
        db.query(IngestBatch)
        .filter(IngestBatch.status == "needs_quarantine_review")
        .order_by(IngestBatch.created_at.desc())
        .all()
    )
    return [_batch_to_summary(batch) for batch in batches]


@router.post("/batches/{batch_id}/restore-quarantine", response_model=BatchSummary)
def restore_quarantine_batch(batch_id: int, db: Session = Depends(get_db)):
    batch = db.get(IngestBatch, batch_id)
    if not batch:
        raise HTTPException(status_code=404, detail="Batch not found")
    try:
        destination = restore_quarantined_batch(db, batch)
    except (ValueError, FileNotFoundError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return _batch_to_summary(
        batch,
        action_message=f"Restored to ingest: {destination}",
    )


@router.get("/quarantine/reports")
def list_quarantine_reports():
    if not settings.quarantine_reports_dir.exists():
        return []
    reports = []
    for path in sorted(
        settings.quarantine_reports_dir.glob("*.json"),
        reverse=True,
    ):
        try:
            reports.append(json.loads(path.read_text(encoding="utf-8")))
        except (OSError, json.JSONDecodeError):
            continue
    return reports


@router.post("/batches/{batch_id}/recovery", response_model=ApproveResponse)
def send_to_recovery(batch_id: int, db: Session = Depends(get_db)):
    batch = db.get(IngestBatch, batch_id)
    if not batch:
        raise HTTPException(status_code=404, detail="Batch not found")
    batch.status = "metadata_recovery"
    batch.updated_at = now_utc()
    db.commit()
    return ApproveResponse(batch_id=batch.id, status=batch.status, message="Batch sent to metadata recovery")


@router.post("/move/approved", response_model=MoveResponse)
def move_approved(db: Session = Depends(get_db)):
    approved_ids = [
        value[0]
        for value in (
            db.query(IngestBatch.id)
            .filter(IngestBatch.status == "approved")
            .all()
        )
    ]
    moved, errors = move_approved_batches(db)
    moved_batches = (
        db.query(IngestBatch)
        .filter(IngestBatch.id.in_(approved_ids))
        .all()
        if approved_ids
        else []
    )
    manifests = []
    for batch in moved_batches:
        pointer = (batch.metadata_json or {}).get("move_manifest")
        if pointer:
            manifests.append({"batch_id": batch.id, **pointer})
    return MoveResponse(
        moved=moved,
        errors=errors,
        files_moved=sum(
            int(item.get("files_moved") or 0)
            + int(item.get("artwork_moved") or 0)
            for item in manifests
        ),
        failed_moves=sum(
            int(item.get("failed_moves") or 0) for item in manifests
        ),
        manifests=manifests,
    )


@router.get("/library")
def library(db: Session = Depends(get_db)):
    items = db.query(ArchiveItem).order_by(ArchiveItem.created_at.desc()).all()
    return items


def _batch_to_summary(
    batch: IngestBatch,
    *,
    action_message: str | None = None,
) -> BatchSummary:
    meta = build_review_state(batch.detected_type, batch.metadata_json)
    display = build_batch_display_fields(batch)
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
        artwork_count=meta.get("artwork_count", 0),
        ignored_sidecar_count=meta.get("ignored_sidecar_count", 0),
        subtitle_count=meta.get("subtitle_count", 0),
        video_file_count=meta.get("video_file_count", 0),
        video_files=meta.get("video_files", []),
        title=meta.get("title"),
        edition=meta.get("edition"),
        resolution=meta.get("resolution"),
        source=meta.get("source"),
        original_release_name=meta.get("original_release_name"),
        primary_video_file=meta.get("primary_video_file"),
        artwork_files=meta.get("artwork_files", []),
        subtitle_files=meta.get("subtitle_files", []),
        ignored_sidecar_files=meta.get("ignored_sidecar_files", []),
        release_tags_removed=meta.get("release_tags_removed", []),
        show_title=meta.get("show_title"),
        season_count=meta.get("season_count", 0),
        episode_count=meta.get("episode_count", 0),
        special_episode_count=meta.get("special_episode_count", 0),
        special_episodes=meta.get("special_episodes", []),
        seasons=meta.get("seasons", []),
        ignored_corrupt_video_count=meta.get("ignored_corrupt_video_count", 0),
        ignored_corrupt_video_files=meta.get("ignored_corrupt_video_files", []),
        name=meta.get("name"),
        reason=meta.get("reason"),
        file_count=meta.get("file_count", 0),
        folder_count=meta.get("folder_count", 0),
        size_bytes=meta.get("size_bytes", 0),
        recommended_action=meta.get("recommended_action"),
        release_count=meta.get("release_count", meta.get("album_count", 0)),
        album_count=meta.get("album_count", 0),
        albums=meta.get("albums", []),
        disc_count=meta.get("disc_count", 1),
        confidence=batch.confidence,
        metadata_quality=meta.get("metadata_quality", "weak"),
        metadata_warnings=meta.get("metadata_warnings", []),
        blocking_review_items=meta.get("blocking_review_items", []),
        non_blocking_review_items=meta.get("non_blocking_review_items", []),
        review_confirmed=meta.get("review_confirmed", False),
        review_type=meta.get("review_type"),
        review_mode=meta.get("review_mode"),
        movie_items=list(meta.get("movie_items") or []),
        collection_title=meta.get("collection_title"),
        keep_collection_together=meta.get("keep_collection_together"),
        collection_destination_root=meta.get(
            "collection_destination_root"
        ),
        author=meta.get("author"),
        book_file_count=meta.get("book_file_count", 0),
        book_files=list(meta.get("book_files") or []),
        primary_book_file=meta.get("primary_book_file"),
        book_items=list(meta.get("book_items") or []),
        collection_summary=dict(meta.get("collection_summary") or {}),
        narrator=meta.get("narrator"),
        series=meta.get("series"),
        series_index=meta.get("series_index"),
        audiobook_file_count=meta.get("audiobook_file_count", 0),
        audio_files=list(meta.get("audio_files") or []),
        primary_audio_file=meta.get("primary_audio_file"),
        chapter_count=meta.get("chapter_count", 0),
        metadata_candidates=dict(meta.get("metadata_candidates") or {}),
        chapter_candidates=list(meta.get("chapter_candidates") or []),
        artwork_candidates=list(meta.get("artwork_candidates") or []),
        generic_audio_tag_count=meta.get("generic_audio_tag_count", 0),
        detected_disc_count=meta.get("detected_disc_count", 0),
        candidate_warning_count=meta.get("candidate_warning_count", 0),
        audiobook_collection_type=meta.get("audiobook_collection_type"),
        contained_books=list(meta.get("contained_books") or []),
        accepted_unknown_author=bool(
            meta.get("accepted_unknown_author", False)
        ),
        accepted_unknown_year=bool(
            meta.get("accepted_unknown_year", False)
        ),
        accepted_unknown_narrator=bool(
            meta.get("accepted_unknown_narrator", False)
        ),
        accepted_unknown_album_artist=bool(
            meta.get("accepted_unknown_album_artist", False)
        ),
        accepted_unknown_album_title=bool(
            meta.get("accepted_unknown_album_title", False)
        ),
        accepted_unknown_discography_artist=bool(
            meta.get("accepted_unknown_discography_artist", False)
        ),
        accepted_unknown_title=bool(
            meta.get("accepted_unknown_title", False)
        ),
        lookup_later=bool(meta.get("lookup_later", False)),
        move_manifest=meta.get("move_manifest"),
        metadata_assist_version=meta.get("metadata_assist_version"),
        suggested_destination=batch.suggested_destination,
        suggested_metadata=batch.suggested_metadata,
        metadata_confirmed=batch.metadata_confirmed,
        action_message=action_message,
        **display,
        created_at=batch.created_at,
    )
