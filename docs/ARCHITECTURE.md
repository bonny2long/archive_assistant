# Archive Assistant Architecture

## Purpose

Archive Assistant is the controlled media organizer in Bonny's NAS workflow.
It scans stable ingest folders, creates review batches, supports metadata review, requires approval, moves approved media, and writes manifests/logs.


## Media-Wide Scoped Object Contract

AA-SYSTEM1 is the standing product architecture contract for Archive Assistant: every reconstructed or child media object must be built from scoped file evidence, not copied wholesale from a parent source folder or inherited metadata blob. This applies across music, audiobooks, books, comics, movies, TV, sidecars, subtitles, artwork, unknown files, and mixed-media folders.

See `docs/Archive_Assistant_AA-SYSTEM1_Media-Wide_Scoped_Object_Contract_2026-07-03.md` before adding new review, split, reconstruction, move-readiness, duplicate-detection, or modal-retirement work.


## AA-QA1 - All-Media Acceptance Gate

AA-QA1 verifies that Archive Assistant is being tested as a media-wide NAS ingestion and review system, not as a music-only or BM Radio-only tool.

The gate covers music, discographies, split child albums, audiobooks, books, comics, movies, TV, artwork, subtitles, sidecars, unknowns, mixed-media folders, quarantine review, destination preview, approval behavior, and move readiness.

AA-QA1 does not remove old editors. Old modal editors remain available until each media type is fully workspace-native and retired type-by-type.

See `docs/Archive_Assistant_AA-QA1_All-Media_Acceptance_Gate_2026-07-03.md` and `docs/AA-QA1_Manual_Test_Report_Template_2026-07-03.md`.

## System Boundary

```text
Intake Watcher = Is the upload finished?
Archive Assistant = What is it, what needs review, and where should it go after approval?
Cleaner = After approved moves, what safe leftovers can be cleaned or sent to review?
BM Radio = Plays the final Music and Audiobooks libraries.
```

Archive Assistant must scan stable ready folders. It should not watch active downloads directly in production.
Intake Watcher owns active upload completion detection.
Cleaner (a separate app) owns conservative cleanup of empty shells and leftovers.

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
- No cleanup or deletion. Cleaner is a separate app.

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

## Cleaner Boundary

Cleaner is a separate app. Archive Assistant never cleans up. It hands Cleaner evidence on disk: move manifests beside every moved release, and disposition records for quarantine, restore, discard, undo discard, and reject under `_REPORTS/archive-assistant/dispositions`. See [CLEANER_BOUNDARY.md](CLEANER_BOUNDARY.md).

## Multi-Disc Grouping

`services/disc_markers.py` recognises disc markers at the end of names ("Dune Disc 1", "Album (Disc 2)", "The Wall (1)" with an agreeing disc tag and CD folder). The scanner, universal ingestion grouping, audiobook metadata, and review routing all use it, so a multi-disc release is one batch, not one per disc.

## Database

SQLite (`backend/archive_assistant.db`) by design. Tables are created by `app.db.init_db` at startup; there are no Alembic migrations, so schema changes need a one-time manual step. Back up with the SQLite backup API and check `pragma integrity_check`.
