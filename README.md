# Archive Assistant Scaffold

Local-first scaffold for Bonny's Archive Assistant -- a self-hosted, NAS-friendly tool for managing personal media archives starting with music.

**V1 goal**: scan copied media placed directly in `data/_INGEST`, classify supported music, create pending reports, wait for approval, then move files into a clean library structure.

**Design philosophy**: deterministic tools with human approval gates. AI metadata recovery comes later.

### Safety rules

- Do not test on your only copy of a file.
- V1 never deletes files.
- V1 only moves files after approval.
- Rejected files stay in place or can be moved to quarantine later.

---

## Table of Contents

- [Quick Start](#quick-start)
- [Usage Flow](#usage-flow)
- [Metadata Quality](#metadata-quality)
- [Configuration](#configuration)
- [Project Structure](#project-structure)
- [Frontend Overview](#frontend-overview)
- [API Endpoints](#api-endpoints)
- [Docker Compose](#docker-compose)
- [Reset Test Data](#reset-test-data)
- [Project Status](#project-status)
- [Development](#development)
- [License](#license)

---

## Quick Start

### Backend setup

**One-time setup:**

```bash
cd backend
python -m venv .venv
pip install -r requirements.txt
python -m app.db.init_db
```

**Every session** (start the server):

```bash
cd backend
source .venv/bin/activate        # Windows: .venv\Scripts\Activate.ps1
uvicorn app.main:app --reload
```

Backend runs at: `http://127.0.0.1:8000`

API docs (`/docs`) are **disabled by default** — use the React frontend for normal work.
To temporarily enable Swagger docs, set `API_DOCS_ENABLED=true` in `backend/.env` and restart.

### Frontend setup

```bash
cd frontend
npm install
npm run dev
```

Frontend runs at: `http://localhost:5173` (proxies `/api` to the backend).

### Put copied music files into ingest

Use copies only -- never place your only copy of a file in the ingest folder.

```text
data/_INGEST/
```

### Scan ingest

```bash
curl -X POST http://127.0.0.1:8000/api/scan/music
```

Or run the worker directly:

```bash
cd backend
python -m app.workers.scan_music_worker
```

### Review pending batches

Open the dashboard at `http://localhost:5173` or use:

```bash
curl http://127.0.0.1:8000/api/batches/pending
```

### Approve a batch

```bash
curl -X POST http://127.0.0.1:8000/api/batches/1/approve
```

Weak or broken batches must be corrected before approval. Use the pencil button in the dashboard, or update metadata via API:

```bash
curl -X PATCH http://127.0.0.1:8000/api/batches/1/metadata \
  -H "Content-Type: application/json" \
  -d '{"artist":"DJ Cinema & Lil Wayne","album":"Starring In Mardi Gras Bootleg","year":"2008","primary_genre":"Mixtape","format":"MP3"}'
```

Folder and track-tag suggestions are stored separately from detected metadata. Saving confirms the correction, recalculates metadata quality and destination, and moves a valid batch back to `pending_review`.

### Move approved batches

```bash
curl -X POST http://127.0.0.1:8000/api/move/approved
```

Or run the worker directly:

```bash
cd backend
python -m app.workers.move_approved_worker
```

---

## Usage Flow

1. Copy album or discography folders directly into `data/_INGEST/`.
2. Click **Scan ingest** on the dashboard or POST `/api/scan/music`.
3. Review batches in the dashboard tabs (All / Pending / Needs Metadata / Approved / Moved).
4. Edit metadata via the pencil icon if needed.
5. Approve batches (checkmark icon or bulk approve).
6. Click **Move approved** to relocate files.
7. Monitor move logs in `data/_REPORTS/move-logs/`.

---

## Metadata Quality

Each scanned album is classified into one of four quality levels:

| Level | Criteria |
|---|---|
| **good** | Artist, album title, and year are all present and valid. |
| **fair** | Some metadata present but missing one or more fields. |
| **weak** | Artist or album is missing; derived from folder name fallback. |
| **broken** | No usable metadata could be extracted. |

- **good / fair** batches are placed in `pending_review` immediately.
- **weak / broken** batches are placed in `needs_metadata_review` and require metadata correction before they can be approved.

---

## Configuration

Settings are defined in `backend/app/core/config.py` using `pydantic-settings`. Loaded from environment variables or a `.env` file (gitignored).

| Setting | Default | Description |
|---|---|---|
| `app_name` | `"Archive Assistant"` | FastAPI application title |
| `debug` | `True` | Enable debug mode |
| `dev_tools_enabled` | `True` | Show local reset tools when debug mode is also enabled |
| `data_root` | `project_root / "data"` | Root data directory |
| `ingest_root` | `data/_INGEST/` | Root intake zone for unclassified media |
| `reports_dir` | `data/_REPORTS/ingest-reports/` | JSON scan reports |
| `move_logs_dir` | `data/_REPORTS/move-logs/` | Move action logs |
| `music_flac_dir` | `data/Music/Library/FLAC/` | FLAC library destination |
| `music_mp3_dir` | `data/Music/Library/MP3/` | MP3 library destination |
| `music_discographies_dir` | `data/Music/Discographies/` | Multi-album artist collection destination |
| `archive_assistant_timezone` | `America/Chicago` | Frontend display and server-local diagnostics timezone |
| `database_url` | `sqlite:///.../archive_assistant.db` | SQLite connection string |

---

## Project Structure

```text
archive-assistant-scaffold/
  backend/
    app/
      main.py                  # FastAPI entry point
      core/config.py           # App settings
      api/routes.py            # REST API endpoints
      db/                      # SQLAlchemy session, init, migrations
      models/                  # SQLAlchemy ORM models
      schemas/                 # Pydantic request/response schemas
      services/                # Scanner, metadata extractor, mover, checksum
      workers/                 # CLI worker scripts
    Dockerfile
    requirements.txt
  frontend/
    src/
      api/                     # HTTP client
      components/              # React components (ActionBar, BatchTable, MetadataEditor, etc.)
      types/                   # TypeScript interfaces
      App.tsx                  # Root component
      main.tsx                 # Entry point
      style.css                # Dark theme via CSS custom properties
    package.json
    vite.config.ts
  data/
    _INGEST/                   # Root drop zone for copied intake items
    _STAGING/                  # Reserved for future use
    _QUARANTINE/               # Rejected / unclear files
    _REPORTS/                  # JSON scan reports and move logs
    Music/Library/FLAC/        # Organized FLAC output
    Music/Library/MP3/         # Organized MP3 output
    Music/Discographies/       # Artist discographies with child album folders
  docs/
    ARCHITECTURE.md            # System architecture and permission design
    ROADMAP.md                 # Future milestones
  scripts/
    reset_music_test.py        # Test data reset utility
    check_metadata_parser.py   # PASS/FAIL checks for ugly folder names
    check_release_grouping.py  # Folder-first and loose-file grouping checks
    check_destination_guard.py # Canonical destination conflict checks
    check_batch_merge.py       # Manual-confirm duplicate merge checks
    check_track_order.py       # Canonical track sorting and filename checks
    check_bulk_approve.py      # Safe bulk approval skip-reason checks
    check_discography_intake.py # Discography detection, move, and reset checks
    check_root_ingest.py        # Root intake classification checks
    create_ugly_music_test_pack.py # Copies local audio into ugly ingest folders
    create_sample_tree.sh      # Creates empty data directory structure
  docker-compose.yml
```

---

## Frontend Overview

The dashboard is a **React + TypeScript** SPA built with **Vite**. Features:

- **Status tabs**: filter batches by All, Pending, Needs Metadata, Approved, Moved.
- **Batch table**: selectable rows, expandable detail panels, inline status badges.
- **Moved library detail**: final destination, metadata used, timeline, move counts, and per-file move history.
- **Library summary**: moved albums, moved tracks, failed moves, and review counts.
- **Dev reset**: restores moved or quarantined test media and clears all ingest/archive test rows from the frontend in local debug mode.
- **Bulk actions**: select all / approve multiple / reject multiple.
- **Metadata editor**: modal form with artist, album, year, genre fields and live destination preview.
- **Discography intake**: deterministic collection detection, album summary table, artist correction, and guarded moves.
- **Dark theme**: fully customizable via CSS custom properties in `style.css`.

Icons: [Tabler Icons](https://tabler.io/icons) (loaded from CDN).

Available scripts (`cd frontend`):

| Command | Description |
|---|---|
| `npm run dev` | Start Vite dev server with hot-reload |
| `npm run build` | Type-check and production build |
| `npm run preview` | Preview production build |

---

## API Endpoints

| Method | Path | Description |
|---|---|---|
| `GET` | `/api/batches` | List all batches |
| `GET` | `/api/batches/pending` | List pending batches |
| `GET` | `/api/batches/needs-metadata-review` | List batches needing metadata review |
| `GET` | `/api/batches/{id}` | Get batch details |
| `GET` | `/api/batches/{id}/moves` | Get per-file move history and completion summary |
| `GET` | `/api/library/summary` | Get library and workflow totals |
| `PATCH` | `/api/batches/{id}/metadata` | Update batch metadata |
| `PATCH` | `/api/batches/{id}/discography` | Correct a discography artist and recalculate its destination |
| `POST` | `/api/batches/{id}/approve` | Approve a batch |
| `POST` | `/api/batches/{id}/send-to-recovery` | Send batch to metadata recovery |
| `POST` | `/api/batches/{id}/reject` | Reject a batch |
| `POST` | `/api/batches/bulk-approve` | Bulk approve by IDs |
| `POST` | `/api/scan/music` | Trigger scan and report created/skipped duplicate counts |
| `POST` | `/api/move/approved` | Move all approved batches |
| `POST` | `/api/dev/reset/test-data` | Reset all local media test data; debug/dev mode only |
| `POST` | `/api/dev/reset/music-test` | Compatibility alias for older reset clients |

Interactive docs are disabled by default. Enable with `API_DOCS_ENABLED=true` in `backend/.env`.

---

## Docker Compose

```bash
docker-compose up
```

Starts two services:

- **archive-backend** (port 8000): Python 3.12-slim, runs `init_db` then `uvicorn`.
- **archive-frontend** (port 5173): Node 22-alpine, runs `npm install && npm run dev -- --host 0.0.0.0`.

For NAS deployment, set both `TZ` and `ARCHIVE_ASSISTANT_TIMEZONE` to the
desired IANA timezone. The container uses the NAS/server clock; TrueNAS remains
responsible for NTP synchronization.

The `./data` directory and SQLite database file are mounted as volumes for persistence.

---

## Reset Test Data

Preview what will be reset (dry run):

```bash
python scripts/reset_music_test.py
```

Apply the reset:

```bash
python scripts/reset_music_test.py --apply
```

This restores moved tracks to their original `data/_INGEST` paths, removes generated music reports and move logs, and clears music records without dropping or recreating database tables.

In local debug mode, the same guarded all-media reset is available from the dashboard using
**Reset test data**. It restores completed library/quarantine moves to `_INGEST`,
clears batches, archive rows, reports, and move logs, and preserves database
tables. The button asks for confirmation and is hidden when debug
tools are disabled.

### Worse metadata test folders

Check the deterministic folder parser:

```bash
backend/.venv/Scripts/python.exe scripts/check_metadata_parser.py
backend/.venv/Scripts/python.exe scripts/check_release_grouping.py
backend/.venv/Scripts/python.exe scripts/check_destination_guard.py
backend/.venv/Scripts/python.exe scripts/check_batch_merge.py
backend/.venv/Scripts/python.exe scripts/check_track_order.py
backend/.venv/Scripts/python.exe scripts/check_bulk_approve.py
backend/.venv/Scripts/python.exe scripts/check_discography_intake.py
backend/.venv/Scripts/python.exe scripts/check_root_ingest.py
```

Create the five ugly ingest folders using existing local test audio:

```bash
python scripts/create_ugly_music_test_pack.py
```

If the repository data folders do not contain at least five audio files, provide
another local test source:

```bash
python scripts/create_ugly_music_test_pack.py --source-root "C:\path\to\test-audio"
```

The pack script copies files only. It does not download content, modify embedded
tags, delete source files, or overwrite existing test targets.

Release folders are grouped as one batch even when individual tracks contain
conflicting embedded album tags. Files dropped directly into the music ingest
root still use embedded artist/album grouping. Before moving, canonical
artist/album comparison blocks obvious duplicate destinations or artist aliases
for manual review instead of silently creating another library folder.

When a manual metadata correction matches another active batch by canonical
artist, album, compatible year, and format, the smaller batch is retained as a
`merged` audit row and its files are reassigned to the largest batch. Confirmed
artist aliases reuse an existing canonical library folder, while existing target
filenames still block the move to prevent overwrites.

Expanded review rows use `GET /api/batches/{batch_id}/review` to show album
facts, warnings, destination preview, and canonical track order before approval.
The same resilient disc/track sorter is used for merge rebuilding, destination
filenames, moves, and move logs.

---

## Project Status

**Current phase**: V1 scaffold -- music-only, SQLite, deterministic tools.

See [docs/ROADMAP.md](docs/ROADMAP.md) for future milestones including:

- Milestone 2: Movies / TV support
- Milestone 3: Full-text search
- Milestone 4: PostgreSQL migration and NAS deployment
- Milestone 5: AI-assisted metadata recovery
- Milestone 6: Plugin system

See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for system architecture details.

---

## Development

### Prerequisites

- **Python** 3.12+
- **Node.js** 22+ (for frontend)
- **npm** (comes with Node.js)

### Backend

```bash
# One-time setup
cd backend
python -m venv .venv
pip install -r requirements.txt
python -m app.db.init_db

# Every session
source .venv/bin/activate        # Windows: .venv\Scripts\Activate.ps1
uvicorn app.main:app --reload   # Omit --reload in production
```

### Frontend

```bash
cd frontend
npm install
npm run dev
```

### Creating the data directory structure

```bash
bash scripts/create_sample_tree.sh
```

### Troubleshooting

| Issue | Likely fix |
|---|---|
| Port 8000 already in use | Change port: `uvicorn app.main:app --reload --port 8001` |
| Port 5173 already in use | Vite will auto-switch to next available port |
| Database errors on startup | Run `python -m app.db.init_db` to create/update tables |
| Files not appearing in ingest | Ensure album or discography folders are direct children of `data/_INGEST/` |
| CORS errors in browser | Check backend is running on port 8000 and frontend on port 5173 |

---

## V1 scope

**Included:**
- Music scan
- SQLite database
- Pending approval workflow
- Approved move workflow
- JSON reports
- Basic FastAPI backend
- Basic React dashboard scaffold

**Not included yet:**
- AI metadata recovery
- Movies / books / audiobooks
- PostgreSQL production schema
- TrueNAS container deployment
