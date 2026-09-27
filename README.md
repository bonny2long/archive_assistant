# Archive Assistant

Archive Assistant is the review-and-organize step of Bonny's NAS. It scans finished downloads in `_INGEST/ready`, works out what each item is, shows you the metadata to confirm, and, only after you approve, moves it into the final library with a manifest recording every file.

```text
Intake Watcher     Is the upload finished?                          -> _INGEST/ready
Archive Assistant  What is it, and where should it go after approval? -> final libraries
Cleaner            After approved moves, what leftovers are safe to clean?
BM Radio           Plays the final Music and Audiobooks libraries.
```

Photos are not Archive Assistant's job. They belong to the future Immich deployment.

## Where it lives

| What | Local | NAS (planned) |
|---|---|---|
| Code | `C:\Dev\NAS\archive_assistant` | container image |
| Data root | `C:\NAS-Local\nas-data` | `/mnt/rust-pool` mounted at `/app/data` |
| Scans | `C:\NAS-Local\nas-data\_INGEST\ready` | `/app/data/_INGEST/ready` |
| Database | SQLite, `backend\archive_assistant.db` | SQLite on the fast NVMe pool |
| Backend API | http://127.0.0.1:8001 | private LAN or Tailscale only |
| Dashboard | http://127.0.0.1:5173 | private LAN or Tailscale only |

Archive Assistant stays on **SQLite** by design; only BM Radio uses PostgreSQL. There are no Alembic migrations: tables are created at startup, so a schema change needs a one-time manual step.

## Workflow

1. Intake Watcher promotes a finished download into `_INGEST/ready`.
2. Click **Scan ingest**. Nothing is scanned automatically, and ordinary review actions never trigger a hidden rescan.
3. Each download becomes a **batch**. Mixed or multi-release downloads become a parent batch whose groups you approve in the **Review Workspace**, then **Create child batches**, one per release.
4. Check and correct the metadata. Suggestions come from tags and folder names; your edits always win.
5. **Approve**, then **Move approved** or move a single batch.
6. Files move into the final library with a `move_manifest.json` and `.md` next to them. Nothing is overwritten.
7. What's left in `ready` is Cleaner's to review.

Final library layout:

```text
Music/Library/FLAC/<Artist>/<Year - Album>/
Music/Library/MP3/<Artist>/<Year - Album>/
Audiobooks/Library/<Author>/<Year - Title>/        (disc folders are kept inside)
Books/EPUB/<Author>/<Year - Title>/
Books/PDF/<Author>/<Year - Title>/
Movies/Library/<Year - Title>/
TV/Library/<Show>/Season NN/  and  TV/Library/<Show>/Specials/
```

A discography download is a source container: each album becomes its own child batch and moves into `Music/Library`, not into one giant discography folder.

## Multi-disc releases

Multi-disc albums and audiobooks are grouped as **one** release:

- Names ending in a disc marker, such as `Dune Disc 1`, `Album (Disc 2)` or `Album - CD 3`, have the marker removed before grouping. Folders like that are treated as disc folders.
- A bare `(1)` ending, as in `The Wall (1)`, counts as a disc only when the disc-number tag says 1 **and** the file sits in a `CD 1` style folder.
- A multi-disc audiobook without disc tags uses each disc folder's number. One stray title or author tag on a single disc (for example `Dune Dics 4` or `Frank Herber`) does not split the book, as long as a clear majority agrees. The stray value stays visible in review.
- Music with repeated track numbers and **no** disc tags is flagged `disc_number_missing` for review, because the files would collide in one album folder.

## Quarantine

Unknown and unsupported items land in **Quarantine review**.

| Action | What happens |
|---|---|
| Move to quarantine | Files move to `_QUARANTINE/unknown-type` or `_QUARANTINE/unsupported-file` |
| Restore to ingest | Files move back to `ready` and the item returns to Quarantine review. Run Scan ingest to re-classify anything you fixed |
| Discard | Needs a reason. **Nothing is deleted**: the item stays in quarantine, marked for discard, for Cleaner to handle later |
| Undo discard | Returns the item to plain quarantine |

Every quarantine, restore, discard, undo discard and reject writes an append-only **disposition record** to `_REPORTS/archive-assistant/dispositions/`. See [docs/CLEANER_BOUNDARY.md](docs/CLEANER_BOUNDARY.md).

**Send to recovery** returns an unknown item to Quarantine review, as long as its files are still in `ready`. It refuses moved, merged, quarantined and discard-marked batches. Scans retire stuck unknown rows whose files no longer exist.

Only unknown and unsupported items can be quarantined today. Damaged recognized media is rejected instead.

## Safety contract

```text
No deletion.
No overwrite of existing destinations.
No embedded tag changes.
No final move without approval.
No hidden rescans from review actions.
Suggestions are candidates; your review is authoritative.
Weak metadata goes to review, not quarantine.
Every move writes manifests and logs.
Dev reset tools never run against real NAS media.
```

## Setup

Backend:

```powershell
Set-Location C:\Dev\NAS\archive_assistant\backend
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
Copy-Item .env.example .env
.\.venv\Scripts\python.exe -m app.db.init_db
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8001
```

Frontend:

```powershell
Set-Location C:\Dev\NAS\archive_assistant\frontend
npm.cmd install
npm.cmd run dev -- --host 127.0.0.1 --port 5173
```

`backend/.env`:

```env
DATA_ROOT=C:/NAS-Local/nas-data
INGEST_ROOT=C:/NAS-Local/nas-data/_INGEST/ready
DATABASE_URL=sqlite:///C:/Dev/NAS/archive_assistant/backend/archive_assistant.db
DEBUG=true
DEV_TOOLS_ENABLED=false
API_DOCS_ENABLED=false
ARCHIVE_ASSISTANT_TIMEZONE=America/Chicago
```

Check the paths loaded:

```powershell
.\.venv\Scripts\python.exe -c "from app.core.config import settings; print(settings.data_root, settings.ingest_root, settings.ingest_root.exists())"
```

## Useful API routes

```text
GET  /api/health
GET  /api/batches
POST /api/scan/music                     start a scan of ready
GET  /api/scan/status
GET  /api/batches/{id}/universal-ingestion
GET  /api/batches/{id}/review-routing
POST /api/batches/{id}/materialize-approved-candidates
POST /api/batches/{id}/approve
POST /api/batches/{id}/move
POST /api/move/approved
POST /api/batches/{id}/reject
POST /api/batches/{id}/recovery
POST /api/batches/{id}/quarantine
POST /api/batches/{id}/restore-quarantine
POST /api/batches/{id}/discard-quarantine   {"reason": "..."}
POST /api/batches/{id}/undo-discard
GET  /api/quarantine/reports
```

## Testing

```powershell
Set-Location C:\Dev\NAS\archive_assistant
$env:DEBUG="true"; $env:PYTHONPATH="backend"; $env:PYTHONIOENCODING="utf-8"
backend\.venv\Scripts\python.exe scripts\check_core_v1_regression.py
Set-Location frontend; npm.cmd run build
```

The Core V1 suite runs 24 checks against temporary folders and in-memory databases. See [docs/TESTING.md](docs/TESTING.md).

## Maintenance scripts

- `scripts/repair_foreign_root_batches.py` hides rows left by test runs against another data root. Dry run by default; `--apply` takes a verified SQLite backup first.

## Known limitations

- Only unknown or unsupported items can be quarantined.
- Scans run only when you click Scan ingest.
- Very noisy release names (for example uploader tags mixed into the title) still need a manual edit.
- Folders with no media never leave Intake Watcher's `incoming`, so they don't reach quarantine.

## More docs

[ARCHITECTURE](docs/ARCHITECTURE.md) · [SAFETY_CONTRACT](docs/SAFETY_CONTRACT.md) · [CLEANER_BOUNDARY](docs/CLEANER_BOUNDARY.md) · [TESTING](docs/TESTING.md) · [OPERATIONS](docs/OPERATIONS.md) · [NAS_DEPLOYMENT](docs/NAS_DEPLOYMENT.md) · [ROADMAP](docs/ROADMAP.md) · [CHANGELOG](docs/CHANGELOG.md)
