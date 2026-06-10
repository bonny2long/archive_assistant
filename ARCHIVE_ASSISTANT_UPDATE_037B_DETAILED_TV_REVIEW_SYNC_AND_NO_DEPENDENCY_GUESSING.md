# ARCHIVE ASSISTANT UPDATE 037B
# Detailed TV Review Sync, Move Safety, and No-Dependency-Guessing Repair

Status: Required follow-up to Update 037  
Branch context: `archive_assistant-feat_edit_test`  
Primary issue: the IDE AI is making assumptions. This file is intentionally explicit and prescriptive. Do not improvise outside this scope.

---

## 0. Read this first

This is not a new feature expansion. This is a repair and hardening pass for the TV review system that already exists.

The branch currently proves that the guided TV review workflow is the right direction. The UI is much better than the spreadsheet approach, and the Shingeki no Kyojin stress test can reach `approved` after removing zero-byte test artifacts.

However, there is still a serious data consistency problem:

> The TV review editor updates `batch.metadata_json.seasons[].episodes[]`, but the mover reads `IngestFile.metadata_json` when deciding where each file goes.

That means the UI can show corrected/reviewed TV metadata, while the move worker may still move files using stale per-file metadata.

This must be fixed before more TV review work is added.

---

## 1. Non-negotiable project rules

Follow these rules exactly.

1. Do not add Mutagen in this update.
2. Do not add any new metadata dependency in this update.
3. Do not mutate embedded tags.
4. Do not delete files.
5. Do not overwrite files.
6. Do not move without approval.
7. Do not reintroduce the spreadsheet episode editor.
8. Do not show every clean episode by default.
9. Do not treat this as a Shingeki-only fix.
10. Do not guess with AI metadata.

Archive Assistant v1 uses deterministic parsing, sidecar metadata, manual review, approval, and move logs. Embedded tag reading/writing can come later in a separate dedicated phase.

---

## 2. Current branch files that matter

Inspect and update these exact files.

Backend:

```text
backend/requirements.txt
backend/app/schemas/archive.py
backend/app/api/routes.py
backend/app/services/tv_review.py
backend/app/services/review_state.py
backend/app/services/mover.py
backend/app/services/scanner.py
```

Frontend:

```text
frontend/src/types/archive.ts
frontend/src/api/client.ts
frontend/src/components/TvMetadataEditor.tsx
frontend/src/components/TvEpisodeReviewPanel.tsx
frontend/src/components/BatchDetail.tsx
frontend/src/utils/batchDisplay.ts
frontend/src/style.css
```

Tests / scripts:

```text
scripts/check_tv_show_hardening.py
scripts/check_tv_review_move_sync.py        # create this if missing
scripts/check_tv_zero_byte_filter.py        # keep/update if already created
```

---

## 3. Remove Mutagen from this branch

### Problem

`backend/requirements.txt` currently contains:

```text
mutagen==1.47.0
```

This is out of scope.

### Required change

Remove this line from `backend/requirements.txt`:

```text
mutagen==1.47.0
```

Then search the whole repo:

```bash
rg -n "mutagen|Mutagen" backend frontend scripts
```

Expected result:

```text
No matches
```

If there are imports or helper functions using Mutagen, remove them entirely from this branch. Do not replace them with a different dependency.

### Why

TV episode review is based on filenames, folder paths, review UI, and sidecar metadata. Mutagen is mostly useful later for music embedded tags. It should not be introduced during a TV review consistency repair.

---

## 4. Root problem to fix

### Current broken pattern

The TV review endpoint updates only the batch-level metadata:

```python
metadata = apply_tv_episode_review_patches(metadata, batch.files, update.patches)
batch.metadata_json = metadata
```

But the mover uses per-file metadata:

```python
metadata = ingest_file.metadata_json or {}
season_number = metadata.get("season_number")
episode_code = metadata.get("episode_code")
is_special = bool(metadata.get("is_special"))
special_label = str(metadata.get("special_label") or "").strip()
destination_group = str(metadata.get("destination_group") or "").strip()
```

This means reviewed data and move data can drift apart.

### Required fix

When TV episode review is saved, update both:

1. `batch.metadata_json.seasons[].episodes[]`
2. each matching `IngestFile.metadata_json`

The reviewed metadata must be identical for each episode in both places for all move-critical fields.

---

## 5. Fields that must be synced to `IngestFile.metadata_json`

When a TV review patch is applied, the following fields must be written to the matching `IngestFile.metadata_json`:

```python
show_title
season_number
episode_number
episode_code
episode_title
raw_name
source_file
relative_source
include
preserve_source_filename
is_special
destination_group
special_label
reviewed
confidence
subtitle_count
```

Keep any existing unrelated file metadata fields unless they conflict.

Move-critical fields are:

```python
season_number
episode_number
episode_code
episode_title
include
preserve_source_filename
is_special
destination_group
special_label
relative_source
source_file
```

These must be consistent between batch metadata and file metadata.

---

## 6. Required backend helper: match reviewed episodes to files safely

Update `backend/app/services/tv_review.py`.

Add a helper that creates a stable key from source fields.

Use this exact logic or equivalent.

```python
def tv_episode_identity(source_file: str | None, relative_source: str | None) -> tuple[str, str]:
    return (
        str(source_file or "").replace("/", "\\").casefold().strip(),
        str(relative_source or "").replace("/", "\\").casefold().strip(),
    )
```

Why normalize slashes:

Windows paths may show `Season 1\\file.mkv`, while frontend/browser values may carry `/`. Matching must not fail because slash style changed.

Add helper:

```python
def ingest_file_identity(ingest_file) -> tuple[str, str]:
    meta = ingest_file.metadata_json or {}
    return tv_episode_identity(
        meta.get("source_file") or ingest_file.file_name,
        meta.get("relative_source"),
    )
```

Important: if `relative_source` is missing on the file row, fallback matching by source file alone is allowed only when it is unique inside the batch. Do not match by `episode_code` because duplicate episode codes are exactly what review is fixing.

---

## 7. Required backend helper: build file lookup without guessing

In `backend/app/services/tv_review.py`, add this helper:

```python
def build_ingest_file_lookup(ingest_files: list) -> dict[tuple[str, str], object]:
    lookup = {}
    source_only_counts = {}

    for item in ingest_files:
        meta = item.metadata_json or {}
        source_file = str(meta.get("source_file") or item.file_name or "")
        relative_source = str(meta.get("relative_source") or "")
        key = tv_episode_identity(source_file, relative_source)
        lookup[key] = item

        source_key = tv_episode_identity(source_file, None)
        source_only_counts[source_key] = source_only_counts.get(source_key, 0) + 1

    # Add source-only fallback only for unique source filenames.
    for item in ingest_files:
        meta = item.metadata_json or {}
        source_file = str(meta.get("source_file") or item.file_name or "")
        source_key = tv_episode_identity(source_file, None)
        if source_only_counts.get(source_key) == 1:
            lookup[source_key] = item

    return lookup
```

This prevents dangerous matching when two files share the same filename in different folders.

---

## 8. Required backend change: return reviewed episode list and sync files

Currently `apply_tv_episode_review_patches(...)` returns only metadata.

Change it so it either:

Option A, preferred:

```python
return metadata, reviewed_episodes
```

or Option B:

```python
metadata["_reviewed_episode_sync"] = reviewed_episodes
```

Preferred implementation:

```python
def apply_tv_episode_review_patches(
    metadata: dict,
    ingest_files: list,
    patches: list[TvEpisodeReviewPatch],
) -> tuple[dict, list[dict]]:
    ...
    return metadata, all_episodes
```

Then add a separate helper:

```python
def sync_tv_episode_metadata_to_ingest_files(
    ingest_files: list,
    reviewed_episodes: list[dict],
) -> list[str]:
    """Sync reviewed TV episode metadata into matching IngestFile rows.

    Returns a list of warning strings for episodes that could not be matched.
    """
```

Pseudo-code:

```python
def sync_tv_episode_metadata_to_ingest_files(ingest_files, reviewed_episodes):
    lookup = build_ingest_file_lookup(ingest_files)
    unmatched = []

    for episode in reviewed_episodes:
        key = tv_episode_identity(
            episode.get("source_file"),
            episode.get("relative_source"),
        )
        item = lookup.get(key)

        if item is None:
            fallback = tv_episode_identity(episode.get("source_file"), None)
            item = lookup.get(fallback)

        if item is None:
            unmatched.append(str(episode.get("relative_source") or episode.get("source_file") or "unknown"))
            continue

        existing = dict(item.metadata_json or {})
        existing.update({
            "show_title": episode.get("show_title"),
            "season_number": episode.get("season_number"),
            "episode_number": episode.get("episode_number"),
            "episode_code": episode.get("episode_code"),
            "episode_title": episode.get("episode_title"),
            "raw_name": episode.get("raw_name"),
            "source_file": episode.get("source_file"),
            "relative_source": episode.get("relative_source"),
            "include": episode.get("include", True),
            "preserve_source_filename": episode.get("preserve_source_filename", False),
            "is_special": episode.get("is_special", False),
            "destination_group": episode.get("destination_group"),
            "special_label": episode.get("special_label"),
            "reviewed": episode.get("reviewed", False),
            "confidence": episode.get("confidence"),
            "subtitle_count": episode.get("subtitle_count", 0),
        })
        item.metadata_json = existing

    return unmatched
```

Do not update files by episode code. Do not update files by list index. Do not update all files with the same code. Use source identity.

---

## 9. Required backend route change

Update `backend/app/api/routes.py`, route:

```python
@router.patch("/batches/{batch_id}/tv-episode-review", response_model=BatchSummary)
def update_tv_episode_review(...):
```

Change this section:

```python
metadata = apply_tv_episode_review_patches(metadata, batch.files, update.patches)
```

To this shape:

```python
metadata, reviewed_episodes = apply_tv_episode_review_patches(
    metadata,
    batch.files,
    update.patches,
)

unmatched = sync_tv_episode_metadata_to_ingest_files(
    batch.files,
    reviewed_episodes,
)

if unmatched:
    warnings = list(metadata.get("metadata_warnings", []))
    warnings.append("tv_review_file_sync_unmatched")
    metadata["metadata_warnings"] = list(dict.fromkeys(warnings))
    metadata["tv_review_file_sync_unmatched"] = unmatched
```

Import the new helper:

```python
from app.services.tv_review import (
    apply_tv_episode_review_patches,
    sync_tv_episode_metadata_to_ingest_files,
)
```

Important:

If unmatched exists, do not automatically approve. Keep the batch in `needs_metadata_review` until the mismatch is resolved.

Add this condition before status is set to pending:

```python
has_sync_errors = bool(unmatched)

if metadata.get("blocking_review_items") or has_sync_errors:
    batch.status = "needs_metadata_review"
    metadata["metadata_quality"] = "weak"
else:
    metadata["metadata_quality"] = "reviewed"
    metadata["review_confirmed"] = True
    if batch.status in {"needs_metadata_review", "pending_review"}:
        batch.status = "pending_review"
```

Then call:

```python
batch.metadata_json = metadata
```

Commit once at the end.

---

## 10. Required review state behavior for sync mismatch

Update `backend/app/services/review_state.py`.

Add `tv_review_file_sync_unmatched` as blocking.

In `BLOCKING_WARNING_TYPES`, include:

```python
"tv_review_file_sync_unmatched",
```

But also make the message useful.

Inside the TV section, if metadata has `tv_review_file_sync_unmatched`, add one blocking item per unmatched file or one grouped blocking item.

Preferred grouped item:

```python
unmatched = meta.get("tv_review_file_sync_unmatched") or []
if unmatched:
    blocking.append(_item(
        "tv_review_file_sync_unmatched",
        "Some reviewed TV episodes could not be matched back to source files. Move is blocked until review metadata and file metadata are synced.",
        files=unmatched,
        count=len(unmatched),
    ))
```

This prevents the UI from saying approved when move metadata is stale.

---

## 11. Required mover safety check before moving TV

Update `backend/app/services/mover.py`.

Before planning `_move_tv_batch`, validate that every included TV episode file has complete move metadata in `IngestFile.metadata_json`.

Add helper near `_move_tv_batch`:

```python
def _validate_tv_file_metadata_ready(batch: IngestBatch) -> list[str]:
    errors = []
    for ingest_file in batch.files:
        if ingest_file.detected_role != "tv_episode":
            continue
        meta = ingest_file.metadata_json or {}
        if not meta.get("include", True):
            continue

        source = ingest_file.file_name
        is_special = bool(meta.get("is_special"))
        preserve = bool(meta.get("preserve_source_filename"))
        destination_group = str(meta.get("destination_group") or "").strip()
        season_number = meta.get("season_number")
        episode_number = meta.get("episode_number")
        episode_code = str(meta.get("episode_code") or "").strip()
        special_label = str(meta.get("special_label") or "").strip()

        if preserve:
            if season_number is None and destination_group not in {"specials", "oad", "extras"}:
                errors.append(f"{source}: preserve original filename requires season number or special group")
            continue

        if is_special:
            if destination_group in {"specials", "oad", "extras"}:
                if not special_label and not episode_code:
                    errors.append(f"{source}: special item requires special_label or episode_code")
            elif destination_group in {"season", ""}:
                if season_number is None:
                    errors.append(f"{source}: season special requires season number")
                if not special_label and not episode_code:
                    errors.append(f"{source}: season special requires special_label or episode_code")
            else:
                errors.append(f"{source}: invalid destination group {destination_group}")
            continue

        if season_number is None:
            errors.append(f"{source}: missing season number")
        if episode_number is None:
            errors.append(f"{source}: missing episode number")
        if not episode_code:
            errors.append(f"{source}: missing episode code")

    return errors
```

Then call at the start of `_move_tv_batch` after destination exists check and before `planned = []`:

```python
metadata_errors = _validate_tv_file_metadata_ready(batch)
if metadata_errors:
    metadata = dict(batch.metadata_json or {})
    warnings = list(metadata.get("metadata_warnings", []))
    warnings.append("tv_file_metadata_not_ready")
    metadata["metadata_warnings"] = list(dict.fromkeys(warnings))
    metadata["tv_file_metadata_not_ready"] = metadata_errors
    batch.metadata_json = metadata
    batch.status = "needs_metadata_review"
    batch.updated_at = now_utc()
    db.commit()
    return [], metadata_errors
```

Add `tv_file_metadata_not_ready` to blocking review state too.

---

## 12. Required destination group behavior

The following destination groups are allowed:

```text
None / ""      normal episode
"season"      special that stays inside a season folder
"specials"    item goes to TV/Library/<Show>/Specials
"oad"         item goes to TV/Library/<Show>/Specials
"extras"      item goes to TV/Library/<Show>/Extras
```

Current `_tv_episode_destination` sends `extras` to Specials only in the preserve path but not in the standard special path. Fix this.

Update this current condition:

```python
if is_special and destination_group in {"specials", "oad"}:
```

To:

```python
if is_special and destination_group in {"specials", "oad", "extras"}:
```

Then folder should be:

```python
folder_name = "Extras" if destination_group == "extras" else "Specials"
return destination / folder_name / file_name
```

Also update preserve logic:

```python
elif destination_group in {"specials", "oad", "extras"}:
    folder = destination / ("Extras" if destination_group == "extras" else "Specials")
```

Do not place OAD items under a folder named `oad`. OAD should go to `Specials` unless we intentionally design a separate OAD folder later.

---

## 13. Required handling for S04P03 / S04P04 final chapters

These filenames appeared in the stress test:

```text
Shingeki no Kyojin - The Final Season - S04P03 - THE FINAL CHAPTERS - Special 1.mkv
Shingeki no Kyojin - The Final Season - S04P04 - THE FINAL CHAPTERS - Special 2.mkv
```

When manually reviewed as specials, a valid reviewed file metadata shape is:

```json
{
  "show_title": "Shingeki no Kyojin",
  "season_number": 4,
  "episode_number": null,
  "episode_code": "S04SP01",
  "episode_title": "Concluding episode (Part 1)",
  "is_special": true,
  "destination_group": "season",
  "special_label": "S04SP01",
  "preserve_source_filename": false,
  "include": true,
  "reviewed": true
}
```

or, if user wants them outside normal season:

```json
{
  "show_title": "Shingeki no Kyojin",
  "season_number": 4,
  "episode_number": null,
  "episode_code": "Special 1",
  "episode_title": "Concluding episode (Part 1)",
  "is_special": true,
  "destination_group": "specials",
  "special_label": "Special 1",
  "preserve_source_filename": false,
  "include": true,
  "reviewed": true
}
```

Both are valid if the UI and mover agree.

But do not use this bad shape:

```json
{
  "episode_code": "THE FINAL CHAPTERS",
  "special_label": "THE FINAL CHAPTERS"
}
```

That creates duplicate special labels for Special 1 and Special 2. The label must be unique if both files go to the same destination folder.

Recommended default for `S04P03` and `S04P04`:

```text
S04P03 -> destination_group: season, special_label: S04SP01
S04P04 -> destination_group: season, special_label: S04SP02
```

Destination preview:

```text
TV/Library/Shingeki no Kyojin/Season 04/S04SP01 - Concluding episode (Part 1).mkv
TV/Library/Shingeki no Kyojin/Season 04/S04SP02 - Concluding episode (Part 2).mkv
```

---

## 14. Required handling for OAD / OVA / OADE files

The stress test includes files like:

```text
OADs\Shingeki no Kyojin - OADE01 - Ilse's Notebook Memoirs of a Scout Regiment Member.mkv
OADs\Shingeki no Kyojin - OADE02 - The Sudden Visitor The Torturous Curse of Youth.mkv
```

These should not stay as vague parse warnings forever.

They should become actionable review cards in the guided TV review UI.

Recommended reviewed metadata for OADs:

```json
{
  "season_number": null,
  "episode_number": null,
  "episode_code": "OAD01",
  "episode_title": "Ilse's Notebook Memoirs of a Scout Regiment Member",
  "is_special": true,
  "destination_group": "oad",
  "special_label": "OAD01",
  "preserve_source_filename": false,
  "include": true,
  "reviewed": true
}
```

Destination:

```text
TV/Library/Shingeki no Kyojin/Specials/OAD01 - Ilse's Notebook Memoirs of a Scout Regiment Member.mkv
```

Pattern support to add or verify:

```text
OADE01 -> OAD01
OAD01  -> OAD01
OVA01  -> OVA01
SPECIAL 1 -> Special 1
Special 01 -> Special 01
```

Do not force OADs into Season 01 unless the user selects that.

---

## 15. Required handling for decimal episodes like S01E13.5

The stress test includes:

```text
Shingeki no Kyojin - S01E13.5 - Since That Day.mkv
```

Current parsing collapses this to:

```text
S01E13
```

That is wrong because it creates a duplicate with real S01E13.

Required behavior:

- Detect decimal episode files.
- Treat them as season specials by default.
- Preserve the decimal code or convert to a unique season special label.

Recommended default:

```json
{
  "season_number": 1,
  "episode_number": null,
  "episode_code": "S01E13.5",
  "episode_title": "Since That Day",
  "is_special": true,
  "destination_group": "season",
  "special_label": "S01E13.5",
  "preserve_source_filename": false,
  "include": true,
  "reviewed": true
}
```

Destination:

```text
TV/Library/Shingeki no Kyojin/Season 01/S01E13.5 - Since That Day.mkv
```

Do not strip `.5` from the code.

Update `_rebuild_episode_code` so if `is_special` and `special_label` is set, it returns `special_label` exactly after trimming.

This already happens in the branch, but the default patch builder must supply a good `special_label`.

---

## 16. Frontend: keep guided repair, but make warning actions concrete

The screenshot now shows:

```text
0 blocking items · 2 warnings
Tv episode parse failed
Tv episode titles missing
```

This is technically true, but not useful enough.

Update frontend review UI so warnings can show files when metadata provides them.

Expected UI sections:

```text
Fix required
  Only appears if blocking items exist.

Warnings
  Unresolved extras / specials
  Missing titles
  Parse warnings

Season overview
  S01 24 ep clean
  S02 12 ep clean
  S03 22 ep clean
  S04 30 ep clean

Extras / Specials
  OAD01 Ilse's Notebook ...
  OAD02 The Sudden Visitor ...
  S04SP01 Concluding episode Part 1
  S04SP02 Concluding episode Part 2

View all episodes
  collapsed by default
```

Important:

Do not show all normal clean episodes by default.

---

## 17. Frontend: save button wording

Current footer says:

```text
Save show info
```

That is too weak because the editor can save show info and episode repair patches.

Change button label based on state:

If there are patches:

```text
Save review
```

If only show title/year changed:

```text
Save show info
```

If no blockers and user is accepting warnings:

```text
Confirm review
```

Do not create multiple primary buttons. Use one primary button with correct label.

---

## 18. Frontend: patch payload must include only changed/problem files

Do not send all 88 episodes as patches.

`TvEpisodeReviewPanel` should only create patches for:

- files the user edited
- files the user marked as special/OAD/extra
- files the user excluded
- files the user marked preserve original filename
- files auto-normalized by a deliberate quick action

Do not generate a patch for every clean episode.

Why:

Sending all episodes increases risk of accidental overwrite or stale frontend state replacing backend state.

---

## 19. Backend: never approve if batch-level and file-level TV counts disagree

Add a safety check after syncing files.

Count included TV episode files from `batch.files`:

```python
included_file_count = sum(
    1
    for item in batch.files
    if item.detected_role == "tv_episode"
    and (item.metadata_json or {}).get("include", True)
)
```

Count included episodes from `metadata["seasons"]`:

```python
included_batch_count = sum(
    1
    for season in metadata.get("seasons", [])
    for episode in season.get("episodes", [])
    if episode.get("include", True)
)
```

If they differ:

```python
metadata["metadata_warnings"].append("tv_review_count_mismatch")
metadata["tv_review_count_mismatch"] = {
    "batch_episode_count": included_batch_count,
    "file_episode_count": included_file_count,
}
batch.status = "needs_metadata_review"
```

Add `tv_review_count_mismatch` as blocking in `review_state.py`.

---

## 20. Backend: move logs should include reviewed TV metadata

When `_move_tv_batch` writes move log sidecar JSON, include:

```json
{
  "media_type": "tv_show",
  "show_title": "Shingeki no Kyojin",
  "season_count": 4,
  "episode_count": 88,
  "review_confirmed": true,
  "metadata_quality": "reviewed",
  "warnings": ["tv_episode_parse_failed", "tv_episode_titles_missing"],
  "special_count": 10,
  "excluded_count": 0,
  "preserved_filename_count": 0
}
```

If this log already exists, extend it. Do not replace existing useful fields.

---

## 21. Required test script: `scripts/check_tv_review_move_sync.py`

Create this test script if missing.

Purpose:

Verify that a reviewed TV batch updates both batch metadata and file metadata before move.

The test does not need real video content. It can use tiny fake `.mkv` files, but avoid zero-byte for real test episodes because zero-byte is now treated as corrupt/test artifact.

Use files with at least 1 byte.

Test setup:

```text
data/_INGEST/Test Show/
  Season 01/
    Test Show - S01E01 - Pilot.mkv
    Test Show - S01E01.5 - Special Recap.mkv
  OADs/
    Test Show - OADE01 - Extra Story.mkv
```

Expected scan:

```text
video_tv_show
needs_metadata_review or pending_review depending parser
```

Then PATCH `/api/batches/{id}/tv-episode-review` with:

```json
{
  "show_title": "Test Show",
  "year": null,
  "confirm_non_blocking_warnings": true,
  "patches": [
    {
      "source_file": "Test Show - S01E01.5 - Special Recap.mkv",
      "relative_source": "Season 01\\Test Show - S01E01.5 - Special Recap.mkv",
      "include": true,
      "season_number": 1,
      "episode_number": null,
      "is_special": true,
      "special_label": "S01E01.5",
      "destination_group": "season",
      "episode_title": "Special Recap",
      "preserve_source_filename": false
    },
    {
      "source_file": "Test Show - OADE01 - Extra Story.mkv",
      "relative_source": "OADs\\Test Show - OADE01 - Extra Story.mkv",
      "include": true,
      "season_number": null,
      "episode_number": null,
      "is_special": true,
      "special_label": "OAD01",
      "destination_group": "oad",
      "episode_title": "Extra Story",
      "preserve_source_filename": false
    }
  ]
}
```

Assertions after save:

1. Batch has no blocking review items.
2. Batch status is `pending_review`.
3. Batch-level `S01E01.5` episode has `is_special: true`.
4. Matching `IngestFile.metadata_json` also has `is_special: true`.
5. Matching `IngestFile.metadata_json.special_label == "S01E01.5"`.
6. Matching OAD file has `destination_group == "oad"`.
7. No `tv_review_file_sync_unmatched` warning.
8. No `tv_review_count_mismatch` warning.

Then approve and move.

Expected final files:

```text
data/TV/Library/Test Show/Season 01/S01E01 - Pilot.mkv
data/TV/Library/Test Show/Season 01/S01E01.5 - Special Recap.mkv
data/TV/Library/Test Show/Specials/OAD01 - Extra Story.mkv
```

Move must not fail with:

```text
TV episode metadata missing
Destination file conflict
```

---

## 22. Regression tests to run

Run these after changes:

```bash
cd backend
python -m compileall app
```

```bash
cd frontend
npm run build
```

Then run relevant scripts:

```bash
python scripts/check_tv_show_hardening.py
python scripts/check_tv_review_move_sync.py
```

If `check_tv_zero_byte_filter.py` exists:

```bash
python scripts/check_tv_zero_byte_filter.py
```

Also manually test:

1. Reset test data.
2. Scan Shingeki folder.
3. Confirm zero-byte test files do not count as episodes.
4. Confirm normal seasons are clean.
5. Confirm OAD/Special files are surfaced as reviewable extras, not vague warnings only.
6. Save review.
7. Confirm batch-level and file-level metadata match.
8. Approve.
9. Move.
10. Verify destination structure.

---

## 23. Expected Shingeki outcome after this update

After rescan and review, a healthy Shingeki summary should look like this:

```text
TV Show | Shingeki no Kyojin | 4 seasons · 88 episodes | pending review or approved
```

Season overview:

```text
S01 24 ep clean
S02 12 ep clean
S03 22 ep clean
S04 30 ep clean
```

Special/OAD review should be specific, for example:

```text
OAD01 - Ilse's Notebook Memoirs of a Scout Regiment Member
OAD02 - The Sudden Visitor The Torturous Curse of Youth
OAD03 - Distress
OAD04 - No Regrets Part 1
OAD05 - No Regrets Part 2
OAD06 - Lost Girls Wall Sina, Goodbye Part 1
OAD07 - Lost Girls Wall Sina, Goodbye Part 2
OAD08 - Lost Girls Lost in the Cruel World
S04SP01 - Concluding episode (Part 1)
S04SP02 - Concluding episode (Part 2)
```

Final destination should be safe and predictable:

```text
TV/Library/Shingeki no Kyojin/
  Season 01/
  Season 02/
  Season 03/
  Season 04/
  Specials/
```

No fake duplicate blockers. No spreadsheet editor. No Mutagen. No deletion. No overwrite.

---

## 24. Acceptance criteria

This update is complete only when all of these are true:

1. `mutagen` is removed from `backend/requirements.txt`.
2. `rg -n "mutagen|Mutagen" backend frontend scripts` returns no matches.
3. TV review save updates `batch.metadata_json`.
4. TV review save updates matching `IngestFile.metadata_json`.
5. Matching is done by source file + relative source, not episode code.
6. Source-only fallback only applies when source filename is unique.
7. If a reviewed episode cannot sync to a file, batch stays `needs_metadata_review`.
8. If batch episode count and included file count disagree, batch stays `needs_metadata_review`.
9. Mover validates per-file TV metadata before moving.
10. S04P03/S04P04 reviewed specials can move safely.
11. OAD/OVA extras can move to `Specials` safely.
12. Decimal episodes like `S01E13.5` do not collapse into `S01E13`.
13. Clean episodes are not shown by default in the editor.
14. Warnings point to exact files when possible.
15. `python -m compileall app` passes.
16. `npm run build` passes.
17. A reviewed mixed TV show can approve and move without stale metadata errors.

---

## 25. Do not do these things

Do not do any of the following:

```text
Do not add Mutagen.
Do not add ffmpeg/ffprobe.
Do not add TMDB/TVDB API calls.
Do not use AI to guess episode metadata.
Do not update files by episode_code.
Do not update files by list index.
Do not send every episode as a patch from the frontend.
Do not move OADs into random season folders unless user chooses it.
Do not collapse S01E13.5 into S01E13.
Do not mark review confirmed if sync failed.
Do not approve if batch metadata and file metadata disagree.
Do not delete zero-byte files during normal scan.
Do not overwrite existing destination files.
```

---

## 26. Plain-English goal

The TV editor should not just make the UI look fixed. It must make the move worker safe.

When the user reviews a TV episode, that corrected metadata must travel all the way through:

```text
UI patch
-> API payload
-> batch.metadata_json
-> IngestFile.metadata_json
-> approval gate
-> mover destination planner
-> move log
-> final TV library folder
```

If any link in that chain is missing, the batch should stay in review instead of pretending it is ready.
