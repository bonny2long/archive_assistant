# Archive Assistant Scaffold

Local-first scaffold for Bonny's Archive Assistant.

V1 goal: scan copied music files in `data/_INGEST/music`, read metadata, create pending reports, wait for approval, then move files into a clean `data/Music/Library/...` folder structure.

Safety rules:

- Do not test on your only copy of a file.
- V1 never deletes files.
- V1 only moves files after approval.
- Rejected files stay in place or can be moved to quarantine later.

## Quick Start

### 1. Backend setup

```bash
cd backend
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\\Scripts\\activate
pip install -r requirements.txt
python -m app.db.init_db
uvicorn app.main:app --reload
```

Backend runs at:

```text
http://127.0.0.1:8000
```

API docs:

```text
http://127.0.0.1:8000/docs
```

### 2. Put copied music files into ingest

Use copies only.

```text
data/_INGEST/music/
```

### 3. Scan music

Use API:

```bash
curl -X POST http://127.0.0.1:8000/api/scan/music
```

Or script:

```bash
cd backend
python -m app.workers.scan_music_worker
```

### 4. Review pending batches

```bash
curl http://127.0.0.1:8000/api/batches/pending
```

### 5. Approve a batch

```bash
curl -X POST http://127.0.0.1:8000/api/batches/1/approve
```

Weak batches must be corrected before approval. Use the pencil button in the
dashboard, or update metadata directly:

```bash
curl -X PATCH http://127.0.0.1:8000/api/batches/1/metadata \
  -H "Content-Type: application/json" \
  -d '{"artist":"DJ Cinema & Lil Wayne","album":"Starring In Mardi Gras Bootleg","year":"2008","primary_genre":"Mixtape","format":"MP3"}'
```

Folder and track-tag suggestions are stored separately from detected metadata.
Saving confirms the correction, recalculates metadata quality and destination,
and moves a valid batch back to `pending_review`.

### 6. Move approved batches

```bash
curl -X POST http://127.0.0.1:8000/api/move/approved
```

Or script:

```bash
cd backend
python -m app.workers.move_approved_worker
```

### Reset music test data

Preview a reset:

```bash
python scripts/reset_music_test.py
```

Apply it:

```bash
python scripts/reset_music_test.py --apply
```

This restores moved tracks to their original `data/_INGEST/music` paths, removes
generated music reports and move logs, and clears music records without dropping
or recreating database tables.

## Local folder layout

```text
archive-assistant-scaffold/
  backend/
  frontend/
  data/
    _INGEST/music/
    _STAGING/
    _QUARANTINE/
    _REPORTS/
    Music/Library/FLAC/
    Music/Library/MP3/
  docs/
```

## V1 scope

Included:

- Music scan
- Metadata extraction using mutagen
- SQLite database
- Pending approval workflow
- Approved move workflow
- JSON reports
- Basic FastAPI backend
- Basic React dashboard scaffold

Not included yet:

- AI metadata recovery
- Movies/books/audiobooks
- PostgreSQL production schema
- TrueNAS container deployment
