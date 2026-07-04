# Archive Assistant Architecture

## Purpose

Archive Assistant is the controlled media organizer in Bonny's NAS workflow.
It scans stable ingest folders, creates review batches, supports metadata review, requires approval, moves approved media, and writes manifests/logs.


## Media-Wide Scoped Object Contract

AA-SYSTEM1 is the standing product architecture contract for Archive Assistant: every reconstructed or child media object must be built from scoped file evidence, not copied wholesale from a parent source folder or inherited metadata blob. This applies across music, audiobooks, books, comics, movies, TV, sidecars, subtitles, artwork, unknown files, and mixed-media folders.

See `docs/Archive_Assistant_AA-SYSTEM1_Media-Wide_Scoped_Object_Contract_2026-07-03.md` before adding new review, split, reconstruction, move-readiness, duplicate-detection, or modal-retirement work.

## Three-System Boundary

```text
Intake Watcher = Is the upload finished?
Archive Assistant = What is it, what needs review, and where should it go after approval?
Cleaner = After approved moves, what safe leftovers can be cleaned or sent to review?
```

Archive Assistant must scan stable ready folders. It should not watch active downloads directly in production.
Intake Watcher owns active upload completion detection.
Cleaner owns later conservative cleanup of empty shells/leftovers.

## Archive Assistant Responsibility

- Scan configured ingest root.
- Classify media.
- Build review batches.
- Show metadata candidates and review issues.
- Require human approval.
- Move approved media to final libraries.
- Write manifests/logs.

## What It Does Not Do

- No active download watching.
- No automatic deletion.
- No embedded tag mutation.
- No silent metadata edits.
- No Cleaner behavior in v2.

## Backend Module Map

```text
scanner.py              Classifies ingest items and builds batch records
review_state.py         Builds blocking/non-blocking review state
metadata_candidates.py  Candidate/suggestion contract for metadata assist
music_metadata.py       Albums/discographies and audio tag/folder parsing
video_metadata.py       Movies/TV video parsing
tv_review.py            TV episode/special review model
book_metadata.py        PDF/EPUB/book grouping metadata
audiobook_metadata.py   Audiobook and multi-disc parsing
mover.py                Approved final moves
move_manifest.py        Per-move audit manifests
library_manifest.py     Library index/manifest helpers
quarantine.py           Unknown/unsupported/rejected handling
report_writer.py        Reports/logs
dev_reset.py            Development reset only, not NAS media
```

## Frontend Module Map

```text
App.tsx
BatchTable.tsx
BatchRow.tsx
BatchDetail.tsx
MediaReviewRouter.tsx
MetadataSuggestionChips.tsx
ReviewIssuesPanel.tsx
MetadataEditor.tsx
DiscographyEditor.tsx
MovieMetadataEditor.tsx
MovieCollectionEditor.tsx
TvMetadataEditor.tsx
TvEpisodeReviewPanel.tsx
BookMetadataEditor.tsx
BookCollectionEditor.tsx
AudiobookMetadataEditor.tsx
LibrarySummary.tsx
StatusTabs.tsx
ActionBar.tsx
```

## Data Model Map

- `IngestBatch`: source-level review/move unit.
- `IngestFile`: files attached to a batch.
- `MoveAction`: source-to-destination move audit row.
- `ArchiveItem`: library item index row.

## Scan / Review / Approve / Move Pipeline

```text
scan ingest
  -> classify media
  -> create batch/files
  -> build review state
  -> user edits/confirms metadata
  -> approve
  -> move approved
  -> manifest/index/report
```

## Metadata Assist Model

Metadata assist produces candidates and review issues. It does not silently change final metadata.

Blocking issues stop approval until reviewed. Non-blocking issues can be accepted by the user.

## Manifest And Logging Model

Moves write audit manifests and media-type metadata manifests. Reports and logs are for traceability and rollback reasoning.

## Quarantine Model

Unknown and unsupported items go to quarantine review. Recognized media with weak metadata stays in metadata review.

## Intake Watcher Bridge

In bridge mode, `INGEST_ROOT` points to Intake Watcher's ready folder.

Archive Assistant scans ready, not incoming.

## Future Cleaner Boundary

Cleaner is not implemented in Archive Assistant v2.

Cleanup of empty shells, uncertain leftovers, rejected retention, and deletion review belongs to future Cleaner / v3.
