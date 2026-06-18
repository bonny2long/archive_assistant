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
DATA_ROOT=C:/Users/BonnyMakaniankhondo/Documents/GitHub/NAS/nas-data
INGEST_ROOT=C:/Users/BonnyMakaniankhondo/Documents/GitHub/NAS/nas-data/_INGEST/ready
```

In bridge mode, the project `data/_INGEST` folder is not the normal scan lane. Intake Watcher promotes stable files into `nas-data/_INGEST/ready`, and Archive Assistant scans that ready folder.

## Reset Safety

Reset test data is development-only. Never run reset against real NAS media.
In bridged mode, reset sends test data back to the stored source path, which may be the shared ready folder.

## Test Media Rules

Do not use your only copy of media for tests. Use copies.
