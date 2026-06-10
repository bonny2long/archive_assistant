# Archive Assistant Update 043 — Movie Collection Approval Fix and Review-Type Persistence

Owner: Bonny Makaniankhondo  
Project: NAS / Archive Assistant  
Phase: Movie collections / universal review hardening  
Priority: High  

## 1. Problem observed

The Harold and Kumar trilogy test exposed a backend review-state bug.

Source folder:

```text
data/_INGEST/Harold and Kumar Trilogy 2004-2011 UNRATED 1080p BluRay HEVC x265 5.1 BONE/
```

Files:

```text
A Very Harold And Kumar Christmas 2011 UNRATED 1080p BluRay HEVC x265 5.1 BONE.mkv
Harold and Kumar Escape from Guantanamo Bay 2008 UNRATED 1080p BluRay HEVC x265 5.1 BONE.mkv
Harold and Kumar Go to White Castle 2004 UNRATED 1080p BluRay HEVC x265 5.1 BONE.mkv
```

The app correctly detected a multi-video movie folder and opened the movie collection editor. The user edited and saved the collection review. The JSON showed `movie_items`, but the batch still could not be approved. The approve modal still reported a blocking review item.

Bad resulting JSON pattern:

```json
{
  "detected_type": "video_movie",
  "status": "pending_review",
  "metadata_confirmed": true,
  "metadata_json": {
    "review_type": "movie",
    "review_mode": "single_item",
    "movie_items": [...],
    "blocking_review_items": [
      {
        "type": "multiple_movie_candidates",
        "message": "3 video files found. Could not determine if they are editions, duplicates, or unrelated files."
      }
    ]
  }
}
```

That state is contradictory. A reviewed movie collection should not revert to single movie review mode and should not continue to block on `multiple_movie_candidates`.

## 2. Root cause

Inspect:

```text
backend/app/services/review_state.py
```

`build_review_state()` currently does this at the end:

```python
meta.update({
    ...
    "review_type": REVIEW_TYPES.get(detected_type, detected_type),
    "review_mode": review_mode,
})
```

For every `detected_type == "video_movie"`, this overwrites an existing:

```python
metadata["review_type"] = "movie_collection"
```

back into:

```python
review_type = "movie"
```

Then later calls to `build_review_state()` no longer see `review_type == "movie_collection"`, so the multi-video blocker comes back.

This also breaks downstream move routing because:

```text
backend/app/services/mover.py
```

uses:

```python
if metadata.get("review_type") == "movie_collection" and metadata.get("movie_items"):
    _move_movie_collection_batch(...)
```

If `review_type` gets overwritten as `movie`, the app risks using single-movie move behavior even though `movie_items` exist.

## 3. Required behavior

A multi-video movie folder can resolve in one of two safe ways:

1. `movie_collection`: each video file becomes its own movie folder.
2. `movie_editions`: multiple video files are editions/versions of the same movie.

For this update, implement and harden only the existing `movie_collection` path.

After a movie collection review is saved:

```json
"review_type": "movie_collection",
"review_mode": "item_list",
"metadata_confirmed": true,
"status": "pending_review",
"blocking_review_items": []
```

Approval must work through both:

```text
single approve button
bulk approve selected modal
```

Move must use:

```python
_move_movie_collection_batch(...)
```

and create separate folders:

```text
Movies/Library/2004 - Harold and Kumar Go to White Castle/
Movies/Library/2008 - Harold and Kumar Escape from Guantanamo Bay/
Movies/Library/2011 - A Very Harold And Kumar Christmas/
```

## 4. Files to inspect/change

Backend:

```text
backend/app/services/review_state.py
backend/app/api/routes.py
backend/app/services/mover.py
backend/app/services/review_items.py
backend/app/schemas/archive.py
```

Frontend:

```text
frontend/src/components/MovieCollectionEditor.tsx
frontend/src/components/MediaReviewRouter.tsx
frontend/src/components/BulkApproveModal.tsx
frontend/src/types/archive.ts
```

Regression scripts:

```text
scripts/check_movie_collection_split_review.py
scripts/check_movie_final_polish.py
scripts/check_universal_review_contract.py
```

Add a focused regression script if needed:

```text
scripts/check_movie_collection_approval_fix.py
```

## 5. Backend fix requirements

### 5.1 Preserve explicit review_type

In `build_review_state()`, do not blindly overwrite an existing valid media-specific review type.

For `detected_type == "video_movie"`:

- If `meta["review_type"] == "movie_collection"`, preserve it.
- If `meta["movie_items"]` exists and at least one included item exists, infer/preserve `review_type = "movie_collection"`.
- Otherwise use `review_type = "movie"`.

Suggested logic concept:

```python
existing_review_type = str(meta.get("review_type") or "")

if detected_type == "video_movie":
    has_movie_items = bool(meta.get("movie_items"))
    if existing_review_type == "movie_collection" or has_movie_items:
        resolved_review_type = "movie_collection"
    else:
        resolved_review_type = "movie"
else:
    resolved_review_type = REVIEW_TYPES.get(detected_type, detected_type)
```

Then use `resolved_review_type` in both the blocker logic and final `meta.update()`.

### 5.2 Clear stale `multiple_movie_candidates` after collection review

When a movie collection has valid `movie_items`, do not retain the old blocker.

The old blocker:

```json
{"type": "multiple_movie_candidates", ...}
```

must not appear in `blocking_review_items` after all included movie items have valid titles and years.

### 5.3 Validate each included movie item

For every included `movie_item`:

- `source_file` required
- `title` required
- `year` required and must be four digits
- destination preview required or rebuildable

Excluded items should not block approval.

### 5.4 Require at least one included movie

If all movie items are excluded, block with:

```json
{
  "type": "movie_collection_no_included_items",
  "message": "At least one movie must be included before approval."
}
```

### 5.5 Keep batch status consistent

After saving a valid movie collection review:

```python
batch.status = "pending_review"
batch.metadata_confirmed = True
batch.confidence = 1.0
metadata["metadata_quality"] = "reviewed"
metadata["review_confirmed"] = True
metadata["review_type"] = "movie_collection"
metadata["review_mode"] = "item_list"
metadata["blocking_review_items"] = []
```

If blockers remain:

```python
batch.status = "needs_metadata_review"
batch.metadata_confirmed = False
batch.confidence <= 0.75
```

Do not allow this contradictory state:

```text
status=pending_review + metadata_confirmed=true + blocking_review_items non-empty
```

### 5.6 Review confirmation route must not corrupt movie collection state

Inspect:

```text
PATCH /batches/{batch_id}/review-confirmation
```

This route currently calls `build_review_state()` again. It must preserve `movie_collection` state and must not revert `review_type` to `movie` or `review_mode` to `single_item`.

Also fix this line if needed:

```python
batch.metadata_confirmed = update.confirmed
```

It should not set `metadata_confirmed=True` if blockers remain. Safer rule:

```python
batch.metadata_confirmed = bool(update.confirmed and not metadata["blocking_review_items"])
```

### 5.7 Approve-selected route must use current review state but not resurrect stale blockers

Inspect:

```text
POST /batches/approve-selected
```

It calls `build_review_state()`. After the review-state fix, this route should approve valid movie collections.

Also make sure approve-selected locks metadata before move, same as the single approve route if that is part of the app pattern.

## 6. Frontend fix requirements

### 6.1 Movie collection editor should reopen saved values

When reopening a saved collection review, the editor should populate each movie item from `batch.movie_items`.

Already mostly implemented, but verify it works after the backend preserves `review_type = movie_collection`.

### 6.2 Collection label should not default to first movie title

Current issue:

```tsx
const [collectionTitle, setCollectionTitle] = useState(
  () => (batch.movie_items?.[0] as MovieCollectionItem | undefined)?.title ?? "",
)
```

This incorrectly sets the collection title to the first movie title.

Change it to use `batch.collection_title` if the type exists, or read from metadata if exposed. If collection title is not exposed yet, add it to `BatchSummary` and `frontend/src/types/archive.ts`.

Correct behavior:

```text
Collection label placeholder: e.g. Harold and Kumar Trilogy
Empty is allowed.
Do not use first movie title as collection label.
```

### 6.3 Approval modal wording

If blockers remain, the modal can say:

```text
1 blocking review item(s)
```

But after a valid movie collection save, it should show as ready to approve.

### 6.4 Confidence display

While unresolved, a movie collection should not show 100% confidence. Suggested:

```text
needs metadata review: 70–75%
pending review after valid collection save: 100% or Confirmed
moved after successful move: Confirmed / Moved
```

## 7. Move behavior requirements

For the Harold and Kumar test, after approval and move, the final structure must be:

```text
data/Movies/Library/
  2004 - Harold and Kumar Go to White Castle/
    metadata/
    Harold and Kumar Go to White Castle 2004 UNRATED 1080p BluRay HEVC x265 5.1 BONE.mkv

  2008 - Harold and Kumar Escape from Guantanamo Bay/
    metadata/
    Harold and Kumar Escape from Guantanamo Bay 2008 UNRATED 1080p BluRay HEVC x265 5.1 BONE.mkv

  2011 - A Very Harold And Kumar Christmas/
    metadata/
    A Very Harold And Kumar Christmas 2011 UNRATED 1080p BluRay HEVC x265 5.1 BONE.mkv
```

Sidecars/artwork/subtitles can go into a shared `_collection_sidecars/` folder for now if they cannot be matched safely.

No overwrite. No deletion. No embedded metadata mutation.

## 8. Regression test requirements

Create or update a script:

```text
scripts/check_movie_collection_approval_fix.py
```

Test case:

```text
Harold and Kumar Trilogy 2004-2011 UNRATED 1080p BluRay HEVC x265 5.1 BONE/
  A Very Harold And Kumar Christmas 2011 UNRATED 1080p BluRay HEVC x265 5.1 BONE.mkv
  Harold and Kumar Escape from Guantanamo Bay 2008 UNRATED 1080p BluRay HEVC x265 5.1 BONE.mkv
  Harold and Kumar Go to White Castle 2004 UNRATED 1080p BluRay HEVC x265 5.1 BONE.mkv
```

Expected sequence:

1. Scan creates one movie batch with 3 videos and status `needs_metadata_review`.
2. Initial blocker includes `multiple_movie_candidates`.
3. Save collection review with 3 included items.
4. Batch becomes `pending_review`.
5. `metadata_confirmed == True`.
6. `metadata_json.review_type == "movie_collection"`.
7. `metadata_json.review_mode == "item_list"`.
8. `blocking_review_items == []`.
9. Single approve succeeds.
10. Bulk approve selected also succeeds in a separate run.
11. Move approved creates three separate final movie folders.
12. No source file is deleted without being moved.
13. No overwrite occurs.

Also rerun existing checks:

```bash
cd backend
python -m compileall app

cd ../frontend
npm run build

cd ..
python scripts/check_movie_final_polish.py
python scripts/check_movie_collection_split_review.py
python scripts/check_universal_review_contract.py
python scripts/check_tv_final_polish.py
```

## 9. Do not do

Do not rebuild TV.
Do not change TV editor behavior.
Do not add Mutagen.
Do not add TMDB, OMDb, MusicBrainz, Open Library, or AI metadata calls.
Do not mutate embedded tags.
Do not delete source files.
Do not overwrite destination files.
Do not convert the movie collection editor into a spreadsheet.
Do not make collection folders the final movie destination in v1.
Each movie in the collection must move to its own `Movies/Library/<Year> - <Title>/` folder.

## 10. Acceptance summary

This update is complete when Bonny can:

1. Scan the Harold and Kumar trilogy folder.
2. Open movie collection review.
3. Edit all three movie rows.
4. Save collection review.
5. See the batch become ready to approve.
6. Approve it without the stale blocking error.
7. Move it into three separate movie folders.
8. Reopen debug JSON and see stable `review_type: movie_collection` with no stale `multiple_movie_candidates` blocker.
