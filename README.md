# Archive Assistant

Archive Assistant is Bonny's local-first media review and organization layer for the NAS.
It scans stable ingest folders, classifies media, presents metadata review, requires human approval, moves approved items into final library folders, and writes manifests/logs.
It does not watch active downloads directly and does not clean up leftovers in v2.

## What Archive Assistant Does

- Scans a configured ingest folder.
- Classifies media into review batches.
- Shows metadata candidates and review issues.
- Lets Bonny edit/confirm metadata.
- Requires approval before final moves.
- Moves approved media into final library folders.
- Writes move manifests, metadata manifests, reports, and logs.

## What Archive Assistant Does Not Do

- No active download watching in production.
- No automatic deletion in v1/v2.
- No embedded tag mutation.
- No silent metadata edits.
- No final move without approval.
- No Cleaner behavior.

## Current Status

```text
Core v1 is locked and tagged as archive-assistant-v1-core.
v2 Metadata Assist is complete and treated as the current locked local baseline.
Current local bridge to Intake Watcher is proven.
Future v3 / Cleaner cleanup is not active.
```

Local workflow proof completed:

- PDF/book files promoted by Intake Watcher into ready, scanned by Archive Assistant, reviewed, approved, moved, and manifest-written.
- Large Kanye West FLAC discography moved through Intake Watcher, scanned by Archive Assistant as `music_discography`, reviewed/approved, and moved into `Music/Discographies/Kanye West`.
- Lil Wayne discography/mixtape set moved through the same flow into `Music/Discographies/Lil Wayne Mixtapes`.

These are local workflow proof cases, not final NAS production certification.

## Safety Contract

```text
No deletion in v1/v2.
No overwrite.
No embedded tag mutation.
No final move without approval.
No silent metadata edits.
Metadata suggestions are candidates only.
Manual review/approval is authoritative.
Recognized weak metadata goes to review, not quarantine.
Unknown/unsupported items go to quarantine review.
Moved media gets manifests/logs.
Dev reset tools must not run on real NAS media.
Cleaner/v3 cleanup is future-only.
```

## How It Fits With Intake Watcher And Cleaner

```text
Intake Watcher = Is the upload finished?
Archive Assistant = What is it, what needs review, and where should it go after approval?
Cleaner = After approved moves, what safe leftovers can be cleaned or sent to review?
```

Archive Assistant should scan stable ready folders. It should not watch active downloads directly in production.

## Folder Flow

Standalone development flow:

```text
data/_INGEST
  -> scan
  -> review/edit
  -> approve
  -> move approved
  -> data/Music | data/Movies | data/TV | data/Books | data/Audiobooks
  -> metadata manifests + _REPORTS
```

Current local two-app bridge:

```text
nas-data/_INGEST/incoming
  -> Intake Watcher stable upload check
nas-data/_INGEST/ready
  -> Archive Assistant scans
  -> scan
  -> review/edit
  -> approve
  -> move approved
  -> nas-data/Music | Movies | TV | Books | Audiobooks
```

Future NAS production flow:

```text
/mnt/rust-pool/_INGEST/incoming
  -> Intake Watcher
/mnt/rust-pool/_INGEST/ready
  -> Archive Assistant
/mnt/rust-pool/Music | Movies | TV | Books | Audiobooks
  -> media apps read final libraries
  -> future Cleaner handles empty shells/leftovers later
```

## Local Quick Start

Backend on Windows PowerShell:

```powershell
cd C:\Users\BonnyMakaniankhondo\Documents\GitHub\NAS\archive-assistant-scaffold\archive-assistant-scaffold\backend

python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python -m app.db.init_db

uvicorn app.main:app --reload
```

Frontend on Windows PowerShell:

```powershell
cd C:\Users\BonnyMakaniankhondo\Documents\GitHub\NAS\archive-assistant-scaffold\archive-assistant-scaffold\frontend

npm install
npm run dev
```

Generic macOS/Linux backend:

```bash
cd backend
python -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python -m app.db.init_db
uvicorn app.main:app --reload
```

Generic macOS/Linux frontend:

```bash
cd frontend
npm install
npm run dev
```

## Local Shared Data Root Setup

Persistent local bridge:

```text
Create or edit:
backend/.env
```

For Bonny's current local shared NAS-style root:

```env
DATA_ROOT=C:/Users/BonnyMakaniankhondo/Documents/GitHub/NAS/nas-data
INGEST_ROOT=C:/Users/BonnyMakaniankhondo/Documents/GitHub/NAS/nas-data/_INGEST/ready
```

Archive Assistant's project `data/_INGEST` is not the normal scan lane in this bridged setup. Intake Watcher promotes stable items into `nas-data/_INGEST/ready`; Archive Assistant scans only that ready folder.

Validation:

```powershell
cd C:\Users\BonnyMakaniankhondo\Documents\GitHub\NAS\archive-assistant-scaffold\archive-assistant-scaffold\backend

python -c "from app.core.config import settings; print(settings.data_root); print(settings.ingest_root); print(settings.ingest_root.exists())"
```

Expected:

```text
C:\Users\BonnyMakaniankhondo\Documents\GitHub\NAS\nas-data
C:\Users\BonnyMakaniankhondo\Documents\GitHub\NAS\nas-data\_INGEST\ready
True
```

If this prints `False`, the path is wrong.
If it prints Archive Assistant's own `data/_INGEST`, `backend/.env` did not load.

## Shared Data Root Ownership

| Path | Owner / purpose |
| --- | --- |
| `nas-data/_INGEST/incoming` | Intake Watcher watches active copies/downloads. |
| `nas-data/_INGEST/intake-processing` | Intake Watcher temporary promotion lane. |
| `nas-data/_INGEST/ready` | Archive Assistant scan input. |
| `nas-data/_INGEST/failed` | Intake Watcher blocked/problem lane. |
| `nas-data/_INGEST/leftover-review` | Future Cleaner / human review. |
| `nas-data/_STAGING` | Archive Assistant working area. |
| `nas-data/_QUARANTINE` | Archive Assistant review/quarantine area. |
| `nas-data/_REPORTS/intake-watcher` | Intake Watcher logs. |
| `nas-data/_REPORTS/archive-assistant` | Archive Assistant scan/move/review logs. |
| `nas-data/_REPORTS/cleaner` | Future cleanup logs. |
| `nas-data/Music` | Archive Assistant final music output. |
| `nas-data/Movies` | Archive Assistant final movie output. |
| `nas-data/TV` | Archive Assistant final TV output. |
| `nas-data/Books` | Archive Assistant final book output. |
| `nas-data/Audiobooks` | Archive Assistant final audiobook output. |

## Dashboard Workflow

1. Confirm the header says `Scanning ingest: .../_INGEST/ready`.
2. Click Scan ingest.
3. Review/edit metadata.
4. Approve.
5. Click Move approved.
6. Confirm final library folder and metadata manifest.

## Supported Media Types

| Media type | Scan | Review | Approve | Move | Manifests |
| --- | --- | --- | --- | --- | --- |
| Music albums | Yes | Yes | Yes | Yes | Yes |
| Music discographies | Yes | Yes | Yes | Yes | Yes |
| Single movies | Yes | Yes | Yes | Yes | Yes |
| Movie collections/trilogies | Yes | Yes | Yes | Yes | Yes |
| TV shows | Yes | Yes | Yes | Yes | Yes |
| Anime/specials/OAD/OVA/OAV handling | Yes | Yes | Yes | Yes | Yes |
| Books/PDF/EPUB | Yes | Yes | Yes | Yes | Yes |
| Book collections | Yes | Yes | Yes | Yes | Yes |
| Audiobooks | Yes | Yes | Yes | Yes | Yes |
| Multi-disc audiobooks | Yes | Yes | Yes | Yes | Yes |

## Metadata Assist v2 Summary

v2 metadata assist provides candidate suggestions and review-state guidance across supported media types.

Metadata suggestions are candidates only. Manual review/approval is authoritative.

## Manifests And Logs

Moved media gets manifests/logs:

- Per-move audit manifests.
- Library metadata manifests.
- Library indexes.
- Reports under `_REPORTS`.

These are audit records. They are not cleanup instructions.

## Environment Variables

```env
DEBUG=true
DEV_TOOLS_ENABLED=false
API_DOCS_ENABLED=false
DATABASE_URL=sqlite:///./archive_assistant.db
DATA_ROOT=../data
INGEST_ROOT=../data/_INGEST
ARCHIVE_ASSISTANT_TIMEZONE=America/Chicago
```

- `DATA_ROOT`: app data root.
- `INGEST_ROOT`: folder Archive Assistant scans. In bridge mode this should be `nas-data/_INGEST/ready`.
- `DATABASE_URL`: SQLite local or PostgreSQL NAS.
- `DEV_TOOLS_ENABLED`: must stay false on NAS.
- `API_DOCS_ENABLED`: keep false unless debugging locally.
- `ARCHIVE_ASSISTANT_TIMEZONE`: app display/serialization timezone.

## API Summary

```text
GET  /api/health
GET  /api/batches
GET  /api/system/paths
POST /api/scan/music
PATCH /api/batches/{id}/metadata
PATCH /api/batches/{id}/discography
PATCH /api/batches/{id}/movie-metadata
PATCH /api/batches/{id}/movie-collection-review
PATCH /api/batches/{id}/tv-metadata
PATCH /api/batches/{id}/tv-episode-review
PATCH /api/batches/{id}/book-metadata
PATCH /api/batches/{id}/book-collection-review
PATCH /api/batches/{id}/audiobook-metadata
POST /api/batches/{id}/approve
POST /api/move/approved
```

## Regression And Testing

```bash
python -m compileall backend/app scripts
python scripts/check_core_v1_regression.py
python scripts/check_tv_anime_specials_regression.py
python scripts/check_root_ingest.py
PYTHONPATH=backend DEBUG=true python scripts/check_reset_safety.py
cd frontend
npm run build
cd ..
git diff --check
```

## NAS Deployment Summary

Archive Assistant should mount `/mnt/rust-pool` as `/app/data`.
It should scan `/app/data/_INGEST/ready`.
It should not scan `/app/data/_INGEST/incoming`.
Final media folders resolve under `DATA_ROOT` unless individually overridden.

Use LAN/Tailscale/VPN only. Do not expose Archive Assistant publicly.
Disable API docs and dev tools on NAS.

## Future Cleaner / v3 Boundary

Cleaner is future-only.

Archive Assistant v2 should leave empty shells and leftovers visible until Cleaner/v3 is built and proven.

## Documentation Map

- `docs/ARCHITECTURE.md`
- `docs/SETUP.md`
- `docs/USAGE.md`
- `docs/ROADMAP.md`
- `docs/INTAKE_WATCHER_BRIDGE.md`
- `docs/NAS_DEPLOYMENT.md`
- `docs/LOCAL_DEVELOPMENT.md`
- `docs/OPERATIONS.md`
- `docs/TESTING.md`
- `docs/SAFETY_CONTRACT.md`
- `docs/CLEANER_BOUNDARY.md`
- `docs/CHANGELOG.md`
- `docs/LOCAL_READY_BRIDGE_SETUP_2026-06-17.md`
