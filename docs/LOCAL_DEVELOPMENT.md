# Local Development

## Backend Setup

```powershell
cd C:\Users\BonnyMakaniankhondo\Documents\GitHub\NAS\archive-assistant-scaffold\archive-assistant-scaffold\backend

python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python -m app.db.init_db
uvicorn app.main:app --reload
```

## Frontend Setup

```powershell
cd C:\Users\BonnyMakaniankhondo\Documents\GitHub\NAS\archive-assistant-scaffold\archive-assistant-scaffold\frontend

npm install
npm run dev
```

## Local Env File

Use `backend/.env` for local settings.

```env
DEBUG=true
DEV_TOOLS_ENABLED=true
INGEST_ROOT=../data/_INGEST
```

## Intake Watcher Bridge Mode

```env
INGEST_ROOT=C:/Users/BonnyMakaniankhondo/Documents/GitHub/NAS/intake-watccher/data/_INGEST/ready
```

## Reset Safety

Reset test data is development-only. Never run reset against real NAS media.

## Test Media Rules

Do not use your only copy of media for tests. Use copies.

