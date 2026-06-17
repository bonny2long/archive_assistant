# Setup

## Local Setup

Archive Assistant repo may be nested:

```text
archive-assistant-scaffold/archive-assistant-scaffold
```

Backend:

```powershell
cd C:\Users\BonnyMakaniankhondo\Documents\GitHub\NAS\archive-assistant-scaffold\archive-assistant-scaffold\backend

python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python -m app.db.init_db
python -m uvicorn app.main:app --reload
```

Frontend:

```powershell
cd C:\Users\BonnyMakaniankhondo\Documents\GitHub\NAS\archive-assistant-scaffold\archive-assistant-scaffold\frontend

npm install
npm run dev
```

## Local `.env`

Create or edit:

```text
backend/.env
```

Typical local defaults:

```env
DEBUG=true
DEV_TOOLS_ENABLED=true
API_DOCS_ENABLED=false
DATA_ROOT=../data
INGEST_ROOT=../data/_INGEST
ARCHIVE_ASSISTANT_TIMEZONE=America/Chicago
```

## Intake Watcher Ready-Folder Bridge

In local bridge mode, Archive Assistant scans Intake Watcher's ready folder, not its own `data/_INGEST`.

```env
INGEST_ROOT=C:/Users/BonnyMakaniankhondo/Documents/GitHub/NAS/intake-watccher/data/_INGEST/ready
```

Validate:

```powershell
cd C:\Users\BonnyMakaniankhondo\Documents\GitHub\NAS\archive-assistant-scaffold\archive-assistant-scaffold\backend

python -c "from app.core.config import settings; print(settings.ingest_root); print(settings.ingest_root.exists())"
```

If it prints Archive Assistant's own `data/_INGEST`, `backend/.env` did not load or the backend was started from the wrong folder.

## Docker Compose

The local `docker-compose.yml` is for app wiring. For NAS deployment, use production-safe env values and disable dev tools/API docs.

## TrueNAS Notes

Archive Assistant should scan:

```text
/app/data/_INGEST/ready
```

It should not scan:

```text
/app/data/_INGEST/incoming
```

## Common Path Mistakes

- Missing the nested `archive-assistant-scaffold/archive-assistant-scaffold` folder.
- Using `intake-watcher` when the local folder is still spelled `intake-watccher`.
- Starting the backend before updating `.env`.
- Starting the backend from a folder where `.env` is not loaded.
