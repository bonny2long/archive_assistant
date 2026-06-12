# Archive Assistant Architecture

## Core principle

Deterministic extraction first. Human approval before write actions. AI metadata assist comes later.

## Services

- **FastAPI** backend (Python 3.12+)
- **SQLite** database (SQLAlchemy ORM); PostgreSQL target for NAS
- **React + TypeScript** dashboard (Vite)
- **Python workers** — scan worker, move worker (CLI scripts)

## Multi-media data flow

All supported media types follow the same pipeline:

```text
_INGEST/ → scan → classify → review → edit → approve → move → manifest + index + log
```

### 1. Scan (`services/scanner.py`)

The scanner iterates over `data/_INGEST/`, classifies each item by type (`music_album`, `music_discography`, `video_movie`, `video_tv_show`, `book`, `audiobook`, `unknown_type`, `unsupported_file`), and delegates to media-specific parsers:

- **Music**: `music_metadata.py` — folder name parsing, embedded tag extraction (mutagen), disc/track sorting, compilation detection, canonical key normalization
- **Movies**: `video_metadata.py` — movie name parsing, year/edition detection, subtitle/artwork identification
- **TV**: `video_metadata.py` + `tv_review.py` — season/episode parsing, special episode detection, episode-level review
- **Books**: `book_metadata.py` — format detection (EPUB, PDF), file grouping
- **Audiobooks**: `audiobook_metadata.py` — multi-disc detection, narrator/series metadata

### 2. Database models (`models/archive.py`)

| Table | Purpose |
|---|---|
| `ingest_batches` | Batch-level metadata, status, confidence, destination |
| `ingest_files` | Per-file records, checksum, detected role, track metadata |
| `move_actions` | Per-file move history (source, destination, status, error) |
| `archive_items` | Permanent archive records after move completion |

### 3. Review state system (`services/review_state.py`)

Each batch carries a `metadata_json` blob that the review system enriches with:

- **Blocking review items** — must be resolved before approval (missing required fields, parse failures)
- **Non-blocking review items** — warnings that can be accepted (missing optional fields, destination conflicts)
- **Metadata quality label** — `good` / `fair` / `weak` / `broken`
- **Confidence score** — 0.0–1.0 based on data completeness and source reliability
- **Metadata warnings** — specific flags like `album_tag_mismatch`, `movie_year_missing`, `tv_episode_parse_failed`

### 4. Metadata correction flow

Each media type has its own PATCH endpoint and editor component:

| Media Type | API Endpoint | Frontend Component |
|---|---|---|
| Music album | `PATCH /api/batches/{id}/metadata` | `MetadataEditor.tsx` |
| Music discography | `PATCH /api/batches/{id}/discography` | `DiscographyEditor.tsx` |
| Movie | `PATCH /api/batches/{id}/movie-metadata` | `MovieMetadataEditor.tsx` |
| Movie collection | `PATCH /api/batches/{id}/movie-collection-review` | `MovieCollectionEditor.tsx` |
| TV show | `PATCH /api/batches/{id}/tv-metadata` | `TvMetadataEditor.tsx` |
| TV episode review | `PATCH /api/batches/{id}/tv-episode-review` | `TvEpisodeReviewPanel.tsx` |
| Book | `PATCH /api/batches/{id}/book-metadata` | `BookMetadataEditor.tsx` |
| Book collection | `PATCH /api/batches/{id}/book-collection-review` | `BookCollectionEditor.tsx` |
| Audiobook | `PATCH /api/batches/{id}/audiobook-metadata` | `AudiobookMetadataEditor.tsx` |

The `MediaReviewRouter.tsx` component routes each batch to the correct editor based on `detected_type` and `review_type`.

### 5. Batch merge (`services/batch_merge.py`)

When metadata is saved, the system checks for merge candidates — batches matching by canonical artist, album, compatible year, and format. The smaller batch's files are reassigned to the largest batch, and the smaller batch becomes a `merged` audit row. Archived duplicate candidates are flagged but not merged.

### 6. Move pipeline (`services/mover.py`)

Approved batches are processed by the move worker:

1. Lock metadata for move (snapshot final values)
2. Recalculate canonical destination
3. For each file: verify checksum, create destination path, copy/move file
4. Write metadata manifest alongside moved media
5. Update or create library index at the media-type root
6. Log every action to `move_actions` table and filesystem move logs

### 7. Manifest and index (`services/library_manifest.py`)

- **Metadata manifest**: JSON file written inside each moved media folder containing scan metadata, correction history, confidence, timestamps, and checksums.
- **Library index**: updated at each media-type root (`Music/Library/`, `Movies/Library/`, etc.) listing all moved items with their paths.

### 8. Quarantine system (`services/quarantine.py`)

Files classified as `unknown_type` or `unsupported_file` route to quarantine instead of blocking the scan. Quarantine review allows: restore to `_INGEST`, discard from tracking, or permanent exclusion. Quarantined discography exclusions (`discography-excluded`) are tracked separately.

## Permissions design for NAS

Run the deployed app as an `archive-assistant` service user. Grant access only to:

- `_INGEST`, `_STAGING`, `_QUARANTINE`
- `_REPORTS`, `_METADATA_RECOVERY`
- `Music`, `Movies`, `TV`, `Books`, `Audiobooks`

Do not allow access to legal documents, financial documents, secrets, or TrueNAS system paths.

## Regression boundary

`check_core_v1_regression.py` validates all v1 contracts in isolated temp directories. It does not touch real ingest, library, or database paths. Filesystem-heavy checks (discography, audiobook, manifest integration) are targeted manual checks on Windows due to temp-directory cleanup behavior.
