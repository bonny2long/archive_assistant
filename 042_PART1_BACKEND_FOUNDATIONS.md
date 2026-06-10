# UPDATE 042 — PART 1: BACKEND FOUNDATIONS
## Universal Media Review Framework — Backend

Context: Archive Assistant is a controlled ingest, review, and move system for a personal NAS.
No files are deleted. No embedded tags are mutated. No file moves happen without user approval.
Every media type must have a clear review path before approval.

Read this file fully before touching any file. All changes in this part are additive.
Existing routes, schemas, and services are NOT removed — only extended.

Run at the end:
```bash
cd backend
python -m compileall app
```

---

## CONTEXT: What already exists and must NOT be broken

Existing working routes (do not remove or change signatures):
- `PATCH /batches/{batch_id}/metadata` — music album
- `PATCH /batches/{batch_id}/discography` — discography
- `PATCH /batches/{batch_id}/movie-metadata` — single movie
- `PATCH /batches/{batch_id}/tv-metadata` — TV show-level
- `PATCH /batches/{batch_id}/tv-episode-review` — TV episode-level repair
- `PATCH /batches/{batch_id}/review-confirmation` — universal confirm

Existing working services (do not remove):
- `review_state.py` — `build_review_state()`, `has_blocking_review_items()`
- `tv_review.py` — `apply_tv_episode_review_patches()`
- `mover.py` — `_move_movie_batch()`, `_move_tv_batch()`, all music movers
- `video_metadata.py` — all parsers and safe path helpers
- `music_metadata.py` — all music helpers

The TV workflow is complete and passing. Do not touch TV logic.

---

## CHANGE 1 — `backend/app/services/review_items.py` (NEW FILE)

Create this file. It does not exist. It builds normalized `review_items` lists
for each media type. These are used for the universal review contract and
later consumed by `movie_collection` review.

```python
"""
review_items.py

Builds normalized review_items lists for each media type.
These supplement (never replace) media-specific metadata.
Used by batch_display and the new movie collection review flow.
"""
from pathlib import Path


def build_review_items_for_music_album(metadata: dict) -> list[dict]:
    """Single-item list describing the album being reviewed."""
    artist = str(metadata.get("artist") or metadata.get("albumartist") or "").strip()
    album = str(metadata.get("album") or "").strip()
    year = str(metadata.get("year") or metadata.get("date") or "")[:4]
    fmt = str(metadata.get("format") or "").strip()
    track_count = int(metadata.get("track_count") or 0)
    disc_count = int(metadata.get("disc_count") or 1)
    artwork_count = int(metadata.get("artwork_count") or 0)
    dest = str(metadata.get("suggested_destination") or "").strip()

    return [
        {
            "item_kind": "album",
            "source_key": "album",
            "include": True,
            "title": album or None,
            "artist": artist or None,
            "year": year or None,
            "format": fmt or None,
            "track_count": track_count,
            "disc_count": disc_count,
            "artwork_count": artwork_count,
            "destination_preview": dest or None,
        }
    ]


def build_review_items_for_discography(metadata: dict) -> list[dict]:
    """One item per release in the discography."""
    artist = str(metadata.get("artist") or "").strip()
    items = []
    for album in metadata.get("albums", []):
        if not isinstance(album, dict):
            continue
        source_folder = str(album.get("source_folder") or "").strip()
        release_year = str(album.get("year") or "").strip()
        title = str(album.get("album") or "").strip()
        release_type = str(album.get("release_type") or "album").strip()
        include = bool(album.get("include", True))
        track_count = int(album.get("track_count") or 0)
        artwork_count = int(album.get("artwork_count") or 0)
        dest = str(album.get("destination_preview") or "").strip()

        items.append(
            {
                "item_kind": "release",
                "source_key": source_folder,
                "include": include,
                "artist": artist or None,
                "title": title or None,
                "year": release_year or None,
                "release_type": release_type,
                "track_count": track_count,
                "artwork_count": artwork_count,
                "destination_preview": dest or None,
            }
        )
    return items


def build_review_items_for_single_movie(metadata: dict) -> list[dict]:
    """Single-item list for a single movie batch."""
    title = str(metadata.get("title") or "").strip()
    year = str(metadata.get("year") or "")[:4]
    edition = str(metadata.get("edition") or "").strip()
    fmt = str(metadata.get("format") or "").strip()
    primary_file = str(metadata.get("primary_video_file") or "").strip()
    dest = str(metadata.get("suggested_destination") or "").strip()

    return [
        {
            "item_kind": "movie",
            "source_key": primary_file or "video",
            "include": True,
            "title": title or None,
            "year": year or None,
            "edition": edition or None,
            "format": fmt or None,
            "destination_preview": dest or None,
        }
    ]


def build_review_items_for_movie_collection(
    metadata: dict,
    files: list,
) -> list[dict]:
    """
    One item per video file in a multi-video movie batch.

    If movie_items already exist in metadata (set by a prior review save),
    use those as the canonical source of truth and just fill in any
    new files that are not yet represented.

    Files argument: list of IngestFile ORM objects.
    """
    from app.services.video_metadata import (
        VIDEO_EXTENSIONS,
        parse_movie_name,
        safe_movie_path_part,
    )

    existing_items: dict[str, dict] = {}
    for item in metadata.get("movie_items", []):
        if isinstance(item, dict) and item.get("source_file"):
            key = str(item["source_file"]).casefold()
            existing_items[key] = item

    video_files = [
        f for f in files
        if Path(f.file_name).suffix.lower() in VIDEO_EXTENSIONS
    ]

    items = []
    for vf in video_files:
        key = str(vf.file_name).casefold()
        if key in existing_items:
            item = dict(existing_items[key])
        else:
            parsed = parse_movie_name(vf.file_name)
            title = str(parsed.get("title") or "").strip()
            year = str(parsed.get("year") or "")[:4]
            edition = str(parsed.get("edition") or "").strip()
            fmt = str(parsed.get("format") or "").strip().upper()

            dest_part = (
                f"{year or 'Unknown Year'} - {title or 'Unknown Title'}"
                if not edition
                else f"{year or 'Unknown Year'} - {title or 'Unknown Title'} [{edition}]"
            )
            dest = f"Movies/Library/{safe_movie_path_part(dest_part)}"

            item = {
                "item_kind": "movie",
                "source_key": vf.file_name,
                "source_file": vf.file_name,
                "include": True,
                "title": title or None,
                "year": year or None,
                "edition": edition or None,
                "format": fmt or None,
                "destination_preview": dest,
            }
        items.append(item)
    return items


def build_review_items_for_batch(batch) -> list[dict]:
    """
    Entry point: build normalized review_items for any batch.
    Returns an empty list for unsupported types rather than raising.
    """
    detected_type = str(batch.detected_type or "")
    metadata = dict(batch.metadata_json or {})

    if detected_type == "music_album":
        return build_review_items_for_music_album(metadata)
    if detected_type == "music_discography":
        return build_review_items_for_discography(metadata)
    if detected_type == "video_movie":
        review_type = str(metadata.get("review_type") or "")
        if review_type == "movie_collection" or metadata.get("movie_items"):
            return build_review_items_for_movie_collection(metadata, batch.files)
        return build_review_items_for_single_movie(metadata)
    # TV review_items are handled separately (TV uses seasons/episodes structure)
    return []
```

---

## CHANGE 2 — `backend/app/services/review_state.py`

### 2a. Add `movie_collection` to `REVIEW_TYPES`

Find this dict:
```python
REVIEW_TYPES = {
    "music_album": "music_album",
    "music_discography": "music_discography",
    "video_movie": "movie",
    "video_tv_show": "tv_show",
    "unknown_type": "quarantine",
    "unsupported_file": "quarantine",
}
```

Add one entry so movie collections get their own review_type string:
```python
REVIEW_TYPES = {
    "music_album": "music_album",
    "music_discography": "music_discography",
    "video_movie": "movie",
    "video_movie_collection": "movie_collection",
    "video_tv_show": "tv_show",
    "unknown_type": "quarantine",
    "unsupported_file": "quarantine",
}
```

### 2b. Add `movie_collection` blocking logic inside the `video_movie` branch

Find the existing `elif detected_type == "video_movie":` block. It currently ends here:
```python
            else:
                blocking.append(_item(
                    "multiple_movie_candidates",
                    f"{video_file_count} video files found. Could not determine if they are editions, duplicates, or unrelated files.",
                ))
```

After that `blocking.append(...)` line (still inside the `video_movie` branch), add:

```python
        # If movie_items have been set by a movie collection review,
        # check each included item has title and year.
        for movie_item in meta.get("movie_items", []):
            if not isinstance(movie_item, dict):
                continue
            if not movie_item.get("include", True):
                continue
            source_file = str(movie_item.get("source_file") or "")
            if not str(movie_item.get("title") or "").strip():
                blocking.append(_item(
                    "movie_collection_item_missing_title",
                    "Movie in collection is missing a title.",
                    file_name=source_file,
                ))
            raw_year = str(movie_item.get("year") or "")
            if len(raw_year) != 4 or not raw_year.isdigit():
                blocking.append(_item(
                    "movie_collection_item_missing_year",
                    "Movie in collection is missing a valid year.",
                    file_name=source_file,
                ))
```

### 2c. Add `review_mode` to the meta update at the bottom of `build_review_state`

Find this block near the end of `build_review_state`:
```python
    meta.update({
        "metadata_quality": quality,
        "metadata_warnings": warnings,
        "blocking_review_items": blocking,
        "non_blocking_review_items": non_blocking,
        "review_confirmed": confirmed,
        "review_type": REVIEW_TYPES.get(detected_type, detected_type),
    })
```

Replace it with:
```python
    # Determine review_mode
    if detected_type == "video_tv_show":
        review_mode = "guided_episode_review"
    elif detected_type in {"music_discography"}:
        review_mode = "item_list"
    elif detected_type == "video_movie" and meta.get("review_type") == "movie_collection":
        review_mode = "item_list"
    elif detected_type in {"unknown_type", "unsupported_file"}:
        review_mode = "quarantine_review"
    else:
        review_mode = "single_item"

    meta.update({
        "metadata_quality": quality,
        "metadata_warnings": warnings,
        "blocking_review_items": blocking,
        "non_blocking_review_items": non_blocking,
        "review_confirmed": confirmed,
        "review_type": REVIEW_TYPES.get(detected_type, detected_type),
        "review_mode": review_mode,
    })
```

---

## CHANGE 3 — `backend/app/schemas/archive.py`

### 3a. Add `review_mode` to `BatchSummary`

Find this field in `BatchSummary`:
```python
    review_type: str | None = None
```

After it, add:
```python
    review_mode: str | None = None
    movie_items: list[dict] = Field(default_factory=list)
```

### 3b. Add `MovieCollectionItemUpdate` and `MovieCollectionReviewUpdate`

Add these two classes after `TvEpisodeReviewUpdate`:

```python
class MovieCollectionItemUpdate(BaseModel):
    source_file: str = Field(min_length=1)
    include: bool = True
    title: str = Field(min_length=1)
    year: str = Field(pattern=r"^(19|20)\d{2}$")
    edition: str | None = None
    format: str | None = None


class MovieCollectionReviewUpdate(BaseModel):
    collection_title: str | None = None
    movies: list[MovieCollectionItemUpdate] = Field(min_length=1)
    confirm_non_blocking_warnings: bool = False
```

---

## CHANGE 4 — `backend/app/services/batch_display.py`

Add `review_mode` and `movie_items` to whatever dict/object `_batch_to_summary` builds.

Find the section in `batch_display.py` (or in `routes.py` if `_batch_to_summary` lives there)
that builds the `BatchSummary` fields from the batch ORM object. It will have a block that
sets fields from `metadata_json`.

Add these two lines alongside where `review_type` is set:

```python
    review_mode=meta.get("review_mode"),
    movie_items=list(meta.get("movie_items") or []),
```

If `_batch_to_summary` is in `routes.py`, search for `review_type=meta.get("review_type")` and
add both lines directly after it.

---

## CHANGE 5 — `backend/app/api/routes.py`

### 5a. Add new imports

Find the existing imports from `app.services` and `app.schemas`. Add:

```python
from app.services.review_items import (
    build_review_items_for_movie_collection,
)
```

Also add `MovieCollectionReviewUpdate` to the schemas import:
```python
    MovieCollectionReviewUpdate,
```

### 5b. Add `PATCH /batches/{batch_id}/movie-collection-review` route

Add this route after the existing `update_movie_metadata` function
(after its `return _batch_to_summary(...)` line, before `@router.patch("/batches/{batch_id}/discography"`):

```python
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
        title = movie_update.title.strip()
        year = movie_update.year.strip()
        edition = movie_update.edition.strip() if movie_update.edition else None
        fmt = movie_update.format.strip().upper() if movie_update.format else None
        include = bool(movie_update.include)

        dest_label = (
            f"{year} - {title}"
            if not edition
            else f"{year} - {title} [{edition}]"
        )
        dest = f"Movies/Library/{safe_movie_path_part(dest_label)}"
        destination_parts.append(dest)

        movie_items.append(
            {
                "item_kind": "movie",
                "source_key": movie_update.source_file,
                "source_file": movie_update.source_file,
                "include": include,
                "title": title,
                "year": year,
                "edition": edition,
                "format": fmt,
                "destination_preview": dest if include else None,
            }
        )

    metadata["movie_items"] = movie_items
    metadata["review_type"] = "movie_collection"
    metadata["review_mode"] = "item_list"

    if update.collection_title:
        metadata["collection_title"] = update.collection_title.strip()

    # Clear the blocker that triggered collection review, since user has now
    # provided per-item metadata. build_review_state will re-evaluate and set
    # new per-item blockers if anything is still missing.
    warnings = [
        w for w in metadata.get("metadata_warnings", [])
        if w != "multiple_movie_candidates"
    ]
    metadata["metadata_warnings"] = warnings

    # Remove old single-movie title/year confidence fields that no longer apply
    # (leave them as fallback in case mover needs them for legacy reasons)
    metadata["confidence"] = 0.8  # will be raised to 1.0 after all items valid

    if update.confirm_non_blocking_warnings:
        metadata["review_confirmed"] = True

    metadata = build_review_state(batch.detected_type, metadata)

    if metadata.get("blocking_review_items"):
        batch.status = "needs_metadata_review"
        metadata["metadata_quality"] = "weak"
        metadata["confidence"] = 0.7
    else:
        metadata["metadata_quality"] = "reviewed"
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
```

---

## CHANGE 6 — `backend/app/services/mover.py`

### 6a. Add `_move_movie_collection_batch` function

Add this function immediately after `_move_movie_batch` (after its closing brace,
before `_move_tv_batch`):

```python
def _move_movie_collection_batch(
    db: Session,
    batch: IngestBatch,
) -> tuple[list[str], list[str]]:
    """
    Move a movie collection batch where each video file becomes its own
    Movies/Library/<Year> - <Title>/ folder.

    Rules:
    - Each included movie_item maps to one video file.
    - Artwork and subtitles that cannot be safely matched to a specific item
      are placed in a _collection_sidecars/ folder under Movies/Library/.
    - No overwrite. No deletion.
    - A move log is written per movie item.
    """
    from app.services.video_metadata import safe_movie_path_part, VIDEO_EXTENSIONS

    metadata = dict(batch.metadata_json or {})
    movie_items = metadata.get("movie_items") or []

    if not movie_items:
        return [], ["Movie collection has no movie_items — cannot move"]

    moved_files: list[str] = []
    failed_files: list[str] = []
    reserved: set[str] = set()

    # Build source_file -> item map for included items
    item_by_source: dict[str, dict] = {}
    for item in movie_items:
        if isinstance(item, dict) and item.get("include", True):
            sf = str(item.get("source_file") or "").strip()
            if sf:
                item_by_source[sf.casefold()] = item

    # Categorize all ingest files
    video_ingest_files = []
    sidecar_ingest_files = []
    for ingest_file in batch.files:
        if Path(ingest_file.file_name).suffix.lower() in VIDEO_EXTENSIONS:
            video_ingest_files.append(ingest_file)
        else:
            sidecar_ingest_files.append(ingest_file)

    # Move each matched video file
    for ingest_file in video_ingest_files:
        key = ingest_file.file_name.casefold()
        item = item_by_source.get(key)

        if not item:
            # Excluded or unmatched — skip
            continue

        title = str(item.get("title") or "Unknown Movie").strip()
        year = str(item.get("year") or "Unknown Year")[:4]
        edition = str(item.get("edition") or "").strip()
        dest_label = (
            f"{year} - {title}"
            if not edition
            else f"{year} - {title} [{edition}]"
        )
        movie_folder = settings.movies_dir / _safe_path_part(dest_label)

        source = Path(ingest_file.file_path)
        completed = _completed_move_destination(db, batch.id, source)
        if not source.exists() and completed:
            moved_files.append(str(completed))
            reserved.add(_path_key(completed))
            continue

        destination_file = movie_folder / ingest_file.file_name
        if _path_key(destination_file) in reserved or destination_file.exists():
            failed_files.append(
                f"Destination conflict for {ingest_file.file_name}: {destination_file}"
            )
            continue

        movie_folder.mkdir(parents=True, exist_ok=True)
        reserved.add(_path_key(destination_file))

        action = MoveAction(
            batch_id=batch.id,
            source_path=str(source),
            destination_path=str(destination_file),
            status="running",
        )
        db.add(action)
        db.flush()
        try:
            shutil.move(str(source), str(destination_file))
            action.status = "completed"
            action.completed_at = now_utc()
            moved_files.append(str(destination_file))

            # Write per-movie move log
            log_dir = movie_folder / "metadata"
            log_dir.mkdir(parents=True, exist_ok=True)
            (log_dir / f"batch-{batch.id}-movie-move-log.json").write_text(
                json.dumps(
                    {
                        "batch_id": batch.id,
                        "media_type": "video_movie_collection",
                        "title": title,
                        "year": year,
                        "edition": edition or None,
                        "format": item.get("format"),
                        "source_file": str(source),
                        "destination": str(destination_file),
                        "moved_at": serialize_utc(now_utc()),
                    },
                    indent=2,
                ),
                encoding="utf-8",
            )
        except Exception as exc:
            action.status = "failed"
            action.error_message = str(exc)
            failed_files.append(f"Failed to move {source}: {exc}")
            db.flush()

    # Move sidecars/artwork/subtitles to a shared _collection_sidecars folder
    # (conservative — do not try to match sidecars to individual movies in v1)
    if sidecar_ingest_files:
        collection_title = str(metadata.get("collection_title") or "collection").strip()
        sidecar_folder = settings.movies_dir / "_collection_sidecars" / _safe_path_part(collection_title)
        sidecar_folder.mkdir(parents=True, exist_ok=True)

        for ingest_file in sidecar_ingest_files:
            source = Path(ingest_file.file_path)
            completed = _completed_move_destination(db, batch.id, source)
            if not source.exists() and completed:
                moved_files.append(str(completed))
                continue
            if not source.exists():
                continue

            dest_file = sidecar_folder / ingest_file.file_name
            if dest_file.exists():
                # Don't overwrite — add numeric suffix
                dest_file = _unique_artwork_destination(dest_file, reserved)

            reserved.add(_path_key(dest_file))
            action = MoveAction(
                batch_id=batch.id,
                source_path=str(source),
                destination_path=str(dest_file),
                status="running",
            )
            db.add(action)
            db.flush()
            try:
                shutil.move(str(source), str(dest_file))
                action.status = "completed"
                action.completed_at = now_utc()
                moved_files.append(str(dest_file))
            except Exception as exc:
                action.status = "failed"
                action.error_message = str(exc)
                failed_files.append(f"Failed to move sidecar {source}: {exc}")
                db.flush()

    return moved_files, failed_files
```

### 6b. Wire `_move_movie_collection_batch` into the main move dispatcher

Find the function `move_batch` (or `_dispatch_move`) in `mover.py` that calls
`_move_movie_batch`. It will have a line like:

```python
    if batch.detected_type == "video_movie":
        return _move_movie_batch(db, batch)
```

Replace that block with:

```python
    if batch.detected_type == "video_movie":
        metadata = dict(batch.metadata_json or {})
        if metadata.get("review_type") == "movie_collection" and metadata.get("movie_items"):
            return _move_movie_collection_batch(db, batch)
        return _move_movie_batch(db, batch)
```

---

## CHANGE 7 — `backend/app/services/video_metadata.py`

### 7a. Add `safe_movie_path_part` if not already present

Search for `safe_movie_path_part` in `video_metadata.py`. If it already exists, skip this.
If it does not exist, add it after `safe_tv_path_part`:

```python
def safe_movie_path_part(value: str) -> str:
    """Sanitize a movie title/folder name for filesystem use."""
    return "".join(c if c not in '<>:"/\\|?*' else "_" for c in value).strip()
```

---

## CHANGE 8 — `backend/app/services/review_state.py` (confidence fix)

The Harold and Kumar test showed `confidence: 1.0` while `metadata_quality: weak`
and a blocking item exists. This is misleading.

In `build_review_state`, after the quality logic block, add a confidence cap:

Find this existing block near the end (just before or inside the `meta.update(...)` call):

```python
    confirmed = bool(meta.get("review_confirmed", False))
    quality = str(meta.get("metadata_quality") or "weak")
    if blocking:
        quality = "broken" if quality == "broken" else "weak"
    elif quality in {"weak", "broken", "unsupported"} and confirmed:
        quality = "fair"
```

After that block and before the `meta.update(...)`, add:

```python
    # Cap confidence while blockers exist
    if blocking:
        existing_confidence = float(meta.get("confidence") or 0.5)
        if existing_confidence > 0.8:
            meta["confidence"] = 0.75
```

---

## VALIDATION CHECKLIST

- [ ] `backend/app/services/review_items.py` created
- [ ] `review_state.py` — `REVIEW_TYPES` has `video_movie_collection`
- [ ] `review_state.py` — `movie_items` per-item validation added to `video_movie` branch
- [ ] `review_state.py` — `review_mode` added to `meta.update(...)` at bottom
- [ ] `review_state.py` — confidence cap added for blocked batches
- [ ] `schemas/archive.py` — `BatchSummary` has `review_mode` and `movie_items` fields
- [ ] `schemas/archive.py` — `MovieCollectionItemUpdate` and `MovieCollectionReviewUpdate` added
- [ ] `batch_display.py` (or `routes.py`) — `review_mode` and `movie_items` populated in `_batch_to_summary`
- [ ] `routes.py` — new `PATCH /batches/{id}/movie-collection-review` route added
- [ ] `mover.py` — `_move_movie_collection_batch` added
- [ ] `mover.py` — dispatcher checks `review_type == "movie_collection"` before dispatching
- [ ] `video_metadata.py` — `safe_movie_path_part` exists
- [ ] `python -m compileall app` passes with zero errors

## DO NOT

- Do not remove or rename any existing route
- Do not change TV logic
- Do not add Mutagen
- Do not add TMDB, MusicBrainz, or any external metadata API
- Do not mutate embedded audio/video tags
- Do not delete files
- Do not overwrite existing files
