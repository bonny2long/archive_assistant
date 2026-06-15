# Archive Assistant

Local-first media archive manager for personal NAS — a self-hosted tool for scanning, reviewing, approving, and organizing music, movies, TV shows, books, and audiobooks.

**Core v1 is complete, regression-locked, and tagged** [`archive-assistant-v1-core`](https://github.com/anomalyco/archive-assistant). All supported media types follow the same deterministic pipeline:

```text
scan → classify → review → edit → approve → move → manifest → index → log
```

**Design philosophy**: deterministic extraction with human approval gates. No silent writes, no deletion, no embedded tag mutation. AI-assisted metadata comes in v2.

### v2 Status

**v2.066 adds functional single-movie and movie-collection metadata-assist
parity to the book, audiobook, and music checkpoints. Full v2 remains open
until TV metadata assist reaches parity.**

### Safety rules

- Do not test on your only copy of a file.
- V1 never deletes files.
- Files only move after explicit approval.
- Rejected or unknown files go to quarantine review.

---

## Table of Contents

- [Quick Start](#quick-start)
- [Usage Flow](#usage-flow)
- [Supported Media Types](#supported-media-types)
- [Metadata Quality](#metadata-quality)
- [Configuration](#configuration)
- [Project Structure](#project-structure)
- [Frontend Overview](#frontend-overview)
- [API Endpoints](#api-endpoints)
- [Docker Compose](#docker-compose)
- [Regression Testing](#regression-testing)
- [Development](#development)
- [License](#license)

---

## Quick Start

### Backend setup

```bash
# One-time
cd backend
python -m venv .venv
pip install -r requirements.txt
python -m app.db.init_db

# Every session
source .venv/bin/activate           # Windows: .venv\Scripts\Activate.ps1
uvicorn app.main:app --reload       # Omit --reload in production
```

Backend at `http://127.0.0.1:8000`. API docs (`/docs`) are disabled by default — set `API_DOCS_ENABLED=true` in `backend/.env` to enable Swagger.

### Frontend setup

```bash
cd frontend
npm install
npm run dev
```

Frontend at `http://localhost:5173` (proxies `/api` to backend).

### Basic workflow

```bash
# 1. Scan whatever is in data/_INGEST/ (music, movies, TV, books, audiobooks)
curl -X POST http://127.0.0.1:8000/api/scan/music

# 2. Open the dashboard to review batches
#    http://localhost:5173

# 3. Approve a batch (once review is confirmed)
curl -X POST http://127.0.0.1:8000/api/batches/1/approve

# 4. Move all approved batches to their library destinations
curl -X POST http://127.0.0.1:8000/api/move/approved
```

Metadata correction is available via API:

```bash
curl -X PATCH http://127.0.0.1:8000/api/batches/1/metadata \
  -H "Content-Type: application/json" \
  -d '{"artist":"DJ Cinema & Lil Wayne","album":"Starring In Mardi Gras Bootleg","year":"2008","primary_genre":"Mixtape","format":"MP3"}'
```

---

## Usage Flow

1. Drop media folders into `data/_INGEST/` (albums, discographies, movies, TV seasons, books, audiobooks — or just loose files).
2. Click **Scan ingest** on the dashboard or POST `/api/scan/music`.
3. Review batches in the dashboard tabs (All / Pending / Needs Metadata / Approved / Moved).
4. Edit metadata via the pencil icon (uses a media-type-specific editor: music, discography, movie, movie collection, TV, book, book collection, audiobook).
5. Approve batches (individual checkmark or bulk approve).
6. Click **Move approved** to relocate files to their library destinations.
7. Monitor move logs in `data/_REPORTS/move-logs/`.
8. Each moved folder receives a metadata manifest; each media type root receives or updates a library index.

---

## Supported Media Types

| Type | Detection | Review | Move | Manifest | Index |
|---|---|---|---|---|---|---|
| Music album | Yes | Yes | Yes | Yes | Yes |
| Music discography | Yes | Yes | Yes | Yes | Yes |
| Movie | Yes | Yes | Yes | Yes | Yes |
| Movie collection | Yes | Yes | Yes | Yes | Yes |
| TV show (season) | Yes | Yes | Yes | Yes | Yes |
| Book | Yes | Yes | Yes | Yes | Yes |
| Book collection | Yes | Yes | Yes | Yes | Yes |
| Audiobook | Yes | Yes | Yes | Yes | Yes |

Unknown or unsupported files route to quarantine review instead of blocking the scan.

---

## Metadata Quality

Each scanned batch is classified into quality levels. The criteria vary by media type, but the principle is the same:

| Level | Meaning |
|---|---|
| **good** | All required fields present and valid |
| **fair** | Some metadata present, one or more fields missing |
| **weak** | Required fields missing; derived from folder-name fallback |
| **broken** | No usable metadata could be extracted |

- **good / fair** → placed in `pending_review` immediately
- **weak / broken** → placed in `needs_metadata_review` or `metadata_recovery`; correction required before approval

---

## Configuration

Settings are defined in `backend/app/core/config.py` using `pydantic-settings`. Loaded from environment or a `.env` file (gitignored).

| Setting | Default | Description |
|---|---|---|
| `app_name` | `"Archive Assistant"` | FastAPI application title |
| `debug` | `True` | Enable debug mode |
| `dev_tools_enabled` | `True` | Show reset tools when debug is also on |
| `data_root` | `project_root / "data"` | Root data directory |
| `ingest_root` | `data/_INGEST/` | Root intake zone |
| `reports_dir` | `data/_REPORTS/ingest-reports/` | JSON scan reports |
| `move_logs_dir` | `data/_REPORTS/move-logs/` | Move action logs |
| `music_flac_dir` | `data/Music/Library/FLAC/` | FLAC music destination |
| `music_mp3_dir` | `data/Music/Library/MP3/` | MP3 music destination |
| `music_discographies_dir` | `data/Music/Discographies/` | Discography destination |
| `movies_dir` | `data/Movies/Library/` | Movie destination |
| `tv_dir` | `data/TV/Library/` | TV show destination |
| `books_dir` | `data/Books/` | Book destination |
| `audiobooks_dir` | `data/Audiobooks/Library/` | Audiobook destination |
| `quarantine_reports_dir` | `data/_REPORTS/quarantine-reports/` | Quarantine reports |
| `archive_assistant_timezone` | `America/Chicago` | Display timezone |
| `database_url` | `sqlite:///.../archive_assistant.db` | SQLite connection string |

---

## Project Structure

```text
archive-assistant/
  backend/
    app/
      main.py                  # FastAPI entry point
      core/config.py           # App settings (pydantic-settings)
      core/time.py             # Timezone helpers
      api/routes.py            # REST API endpoints (all media types)
      db/                      # SQLAlchemy session, init, migrations
      models/archive.py        # ORM models (IngestBatch, IngestFile, MoveAction, ArchiveItem)
      schemas/archive.py       # Pydantic request/response schemas
      services/
        scanner.py             # Multi-media scan/dispatch (2163 lines)
        music_metadata.py      # Music folder parse, tag extraction, sorting
        video_metadata.py      # Movie/TV folder parse, naming
        book_metadata.py       # Book metadata & destination logic
        audiobook_metadata.py  # Audiobook metadata & destination logic
        tv_review.py           # TV episode review patch logic
        review_state.py        # Build review state, blocking/non-blocking items
        review_items.py        # Movie collection review item builder
        mover.py               # Lock metadata, move approved batches
        quarantine.py          # Batch quarantine/restore
        batch_display.py       # Batch display field builder
        batch_merge.py         # Duplicate detection and batch merge
        metadata_candidates.py # Metadata suggestion chip system (v2 foundation)
        library_manifest.py    # Metadata manifest writer per moved folder
        checksum.py            # SHA-256 file hashing
        report_writer.py       # JSON scan report writer
        dev_reset.py           # Test data reset
      workers/
        scan_music_worker.py   # CLI scan worker
        move_approved_worker.py # CLI move worker
    Dockerfile
    requirements.txt
  frontend/
    src/
      api/client.ts            # HTTP client
      components/              # React components
        ActionBar.tsx           # Scan / Move / Reset buttons
        BatchTable.tsx          # Paginated batch table
        BatchRow.tsx            # Individual batch row
        BatchDetail.tsx         # Expandable detail panel
        StatusTabs.tsx          # All / Pending / Needs Metadata / Approved / Moved
        LibrarySummary.tsx      # Library stats card
        MetadataEditor.tsx      # Music album metadata editor
        DiscographyEditor.tsx   # Discography artist/album editor
        MovieMetadataEditor.tsx # Single movie metadata editor
        MovieCollectionEditor.tsx # Movie collection review editor
        TvMetadataEditor.tsx    # TV show metadata editor
        TvEpisodeReviewPanel.tsx # TV episode-by-episode review
        BookMetadataEditor.tsx  # Book metadata editor
        BookCollectionEditor.tsx # Book collection review editor
        AudiobookMetadataEditor.tsx # Audiobook metadata editor
        MediaReviewRouter.tsx   # Routes to correct editor by media type
        BulkApproveModal.tsx    # Bulk approve UI
        ReviewIssuesPanel.tsx   # Blocking/non-blocking issues display
        MetadataSuggestionChips.tsx # Suggestion chips (v2)
        Toast.tsx               # Notification toast
      types/archive.ts          # TypeScript interfaces
      utils/archiveTime.ts      # Timezone display utilities
      App.tsx                   # Root component
      main.tsx                  # Entry point
      style.css                 # Dark theme via CSS custom properties
    package.json
    vite.config.ts
  data/
    _INGEST/                   # Root drop zone for intake items
    _STAGING/                  # Reserved for future use
    _QUARANTINE/               # Rejected / unclear files
    _REPORTS/                  # Scan reports, move logs, quarantine reports
    Music/Library/FLAC/        # Organized FLAC output
    Music/Library/MP3/         # Organized MP3 output
    Music/Discographies/       # Artist discographies
    Movies/Library/            # Organized movie output
    TV/Library/                # Organized TV show output
    Books/                     # Organized book output
    Audiobooks/Library/        # Organized audiobook output
  docs/
    ARCHITECTURE.md            # System architecture and data flow
    ROADMAP.md                 # Future milestones
    CORE_V1_ACCEPTANCE.md      # Core v1 acceptance criteria
  scripts/
    reset_music_test.py        # Test data reset utility
    create_ugly_music_test_pack.py # Creates ugly ingest folders for testing
    check_core_v1_regression.py    # Full core v1 regression suite
    check_metadata_parser.py   # Ugly folder name parser checks
    check_release_grouping.py  # Folder-first and loose-file grouping
    check_destination_guard.py # Canonical destination conflict checks
    check_batch_merge.py       # Duplicate merge checks
    check_track_order.py       # Track sorting and filename checks
    check_bulk_approve.py      # Bulk approval skip-reason checks
    check_discography_intake.py # Discography intake checks
    check_root_ingest.py       # Root intake classification checks
    (plus other media-type-specific check scripts)
  docker-compose.yml
```

---

## Frontend Overview

The dashboard is a **React + TypeScript** SPA built with **Vite**. Features:

- **Status tabs**: filter batches by All, Pending, Needs Metadata, Approved, Moved.
- **Batch table**: selectable rows, expandable detail panels, inline status badges.
- **Media-type-aware editors**: each batch opens the correct editor — music album, discography, movie, movie collection, TV show (with episode-level review), book, book collection, or audiobook.
- **Moved library detail**: final destination, metadata used, timeline, move counts, per-file move history.
- **Library summary**: moved albums, moved tracks, failed moves, review counts.
- **Dev reset**: restores moved/quarantined test media in local debug mode.
- **Bulk actions**: select all / approve multiple / reject multiple.
- **Metadata suggestion chips**: candidate system for v2 metadata assist (EPUB/PDF reading, audiobook chapter help, optional online lookup).
- **Dark theme**: fully customizable via CSS custom properties in `style.css`.

Icons: [Tabler Icons](https://tabler.io/icons) (CDN).

Available scripts (`cd frontend`):

| Command | Description |
|---|---|
| `npm run dev` | Vite dev server with hot-reload |
| `npm run build` | Type-check and production build |
| `npm run preview` | Preview production build |

---

## API Endpoints

| Method | Path | Description |
|---|---|---|
| `GET` | `/api/health` | Service health check |
| `GET` | `/api/system/time` | Server timezone and clock |
| `GET` | `/api/batches` | List all batches (paginated) |
| `GET` | `/api/batches/pending` | List pending-review batches |
| `GET` | `/api/batches/needs-metadata-review` | Batches needing metadata review |
| `GET` | `/api/batches/{id}` | Get batch details |
| `GET` | `/api/batches/{id}/files` | Get batch files |
| `GET` | `/api/batches/{id}/review` | Expanded review (tracks, warnings, destination) |
| `GET` | `/api/batches/{id}/moves` | Per-file move history |
| `GET` | `/api/library/summary` | Library and workflow totals |
| `PATCH` | `/api/batches/{id}/metadata` | Update music album metadata |
| `PATCH` | `/api/batches/{id}/movie-metadata` | Update movie metadata |
| `PATCH` | `/api/batches/{id}/movie-collection-review` | Review movie collection |
| `PATCH` | `/api/batches/{id}/book-metadata` | Update book metadata |
| `PATCH` | `/api/batches/{id}/book-collection-review` | Review book collection |
| `PATCH` | `/api/batches/{id}/audiobook-metadata` | Update audiobook metadata |
| `PATCH` | `/api/batches/{id}/tv-metadata` | Update TV show metadata |
| `PATCH` | `/api/batches/{id}/tv-episode-review` | Episode-level TV review |
| `PATCH` | `/api/batches/{id}/discography` | Update discography artist |
| `PATCH` | `/api/batches/{id}/review-confirmation` | Confirm/remove review |
| `POST` | `/api/batches/{id}/approve` | Approve a batch |
| `POST` | `/api/batches/{id}/send-to-recovery` | Send to metadata recovery |
| `POST` | `/api/batches/{id}/reject` | Reject a batch |
| `POST` | `/api/batches/bulk-approve` | Bulk approve by IDs |
| `POST` | `/api/approve-selected` | Approve selected batches with skip reporting |
| `POST` | `/api/batches/{id}/merge` | Merge batches |
| `POST` | `/api/scan/music` | Scan all ingest media |
| `POST` | `/api/move/approved` | Move all approved batches |
| `POST` | `/api/dev/reset/test-data` | Reset test data (debug mode only) |
| `POST` | `/api/dev/reset/music-test` | Legacy alias |

Interactive docs are disabled by default. Enable with `API_DOCS_ENABLED=true` in `backend/.env`.

---

## Docker Compose

```bash
docker-compose up
```

Two services:

- **archive-backend** (port 8000): Python 3.12-slim, runs `init_db` then `uvicorn`.
- **archive-frontend** (port 5173): Node 22-alpine, serves the dashboard.

For NAS deployment, set `TZ` and `ARCHIVE_ASSISTANT_TIMEZONE` to your IANA timezone. The `./data` directory and SQLite database are mounted as volumes.

---

## Regression Testing

Run the full core v1 regression before any major changes:

```bash
python scripts/check_core_v1_regression.py
```

This validates v1 contracts for music, discographies, movies, movie collections, TV, books, book collections, audiobooks, bulk approval, and manifest integration. Each check has a bounded timeout and uses isolated temp directories — no risk to real data.

Manual UI testing is still recommended for large real-media drops. Filesystem move/manifest checks are targeted manual checks on Windows (temp-directory cleanup can stall).

### Per-feature check scripts

```bash
# Deterministic folder parser checks
backend/.venv/Scripts/python.exe scripts/check_metadata_parser.py
backend/.venv/Scripts/python.exe scripts/check_release_grouping.py
backend/.venv/Scripts/python.exe scripts/check_destination_guard.py
backend/.venv/Scripts/python.exe scripts/check_batch_merge.py
backend/.venv/Scripts/python.exe scripts/check_track_order.py
backend/.venv/Scripts/python.exe scripts/check_bulk_approve.py
backend/.venv/Scripts/python.exe scripts/check_discography_intake.py
backend/.venv/Scripts/python.exe scripts/check_root_ingest.py
```

Create ugly ingest test folders:

```bash
python scripts/create_ugly_music_test_pack.py
python scripts/create_ugly_music_test_pack.py --source-root "C:\path\to\test-audio"
```

### Test data reset

```bash
# Dry run
python scripts/reset_music_test.py

# Apply
python scripts/reset_music_test.py --apply
```

From the dashboard (debug mode): click **Reset test data** — restores moved/quarantined files to `_INGEST`, clears batches, archive rows, reports, and move logs. Preserves database tables.

---

## Development

### Prerequisites

- **Python** 3.12+
- **Node.js** 22+ (for frontend)
- **npm** (comes with Node.js)

### Backend

```bash
cd backend
python -m venv .venv
pip install -r requirements.txt
python -m app.db.init_db
source .venv/bin/activate   # Windows: .venv\Scripts\Activate.ps1
uvicorn app.main:app --reload
```

### Frontend

```bash
cd frontend
npm install
npm run dev
```

### Troubleshooting

| Issue | Likely fix |
|---|---|
| Port 8000 already in use | `uvicorn app.main:app --reload --port 8001` |
| Port 5173 already in use | Vite auto-switches to next available port |
| Database errors on startup | Run `python -m app.db.init_db` |
| Files not appearing in ingest | Ensure folders are direct children of `data/_INGEST/` |
| CORS errors in browser | Backend on 8000, frontend on 5173 |

---

## Project Status

**Current phase**: Core v1 complete, regression-locked, tagged [`archive-assistant-v1-core`](https://github.com/anomalyco/archive-assistant).

**Current v2 work**: bring music, movie, and TV metadata assist to parity with
the functionally passing book/audiobook workflow, then run the final mixed-media
v2 regression and release lock. No silent edits, no deletion, and manual
approval remains authoritative.

See [docs/ROADMAP.md](docs/ROADMAP.md) and [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for details.

---

## License

MIT © Bonny Makaniankhondo
