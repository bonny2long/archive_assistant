# Local Ready-Folder Bridge Setup

This local setup lets Archive Assistant scan Intake Watcher's completed handoff folder while the two projects remain separate.

Archive Assistant should scan only Intake Watcher's ready folder:

```text
C:/Users/BonnyMakaniankhondo/Documents/GitHub/NAS/intake-watcher/data/_INGEST/ready
```

Do not point Archive Assistant at Intake Watcher's `incoming` folder.

## Backend Startup

Run this in the same PowerShell session that starts the Archive Assistant backend. The environment variable must be set before `uvicorn` starts.

```powershell
cd C:\Users\BonnyMakaniankhondo\Documents\GitHub\NAS\archive-assistant-scaffold\backend

$env:INGEST_ROOT="C:/Users/BonnyMakaniankhondo/Documents/GitHub/NAS/intake-watcher/data/_INGEST/ready"

python -c "from app.core.config import settings; print('INGEST_ROOT=', settings.ingest_root)"

uvicorn app.main:app --reload
```

## Frontend Startup

Start the frontend separately:

```powershell
cd C:\Users\BonnyMakaniankhondo\Documents\GitHub\NAS\archive-assistant-scaffold\frontend
npm run dev
```

## Verification Command

Before opening the UI, verify the backend sees the intended ingest path:

```powershell
cd C:\Users\BonnyMakaniankhondo\Documents\GitHub\NAS\archive-assistant-scaffold\backend

$env:INGEST_ROOT="C:/Users/BonnyMakaniankhondo/Documents/GitHub/NAS/intake-watcher/data/_INGEST/ready"

python -c "from app.core.config import settings; print(settings.ingest_root); print(settings.ingest_root.exists())"
```

Expected output:

```text
C:\Users\BonnyMakaniankhondo\Documents\GitHub\NAS\intake-watcher\data\_INGEST\ready
True
```

If it prints `False`, the path is wrong or the folder does not exist.

If it prints Archive Assistant's own `data/_INGEST`, the environment variable was not loaded by the backend process.

## UI Check

Archive Assistant now exposes:

```text
GET /api/system/paths
```

The dashboard header shows:

```text
Scanning ingest: ...
```

Confirm this line points to Intake Watcher's `ready` folder before clicking Scan.

