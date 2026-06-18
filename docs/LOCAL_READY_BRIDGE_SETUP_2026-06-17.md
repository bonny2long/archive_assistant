# Local Ready-Folder Bridge Setup - 2026-06-17 Checkpoint

This dated checkpoint is kept for project history.

The current bridge documentation lives at:

```text
docs/INTAKE_WATCHER_BRIDGE.md
```

Current shared local path:

```env
DATA_ROOT=C:/Users/BonnyMakaniankhondo/Documents/GitHub/NAS/nas-data
INGEST_ROOT=C:/Users/BonnyMakaniankhondo/Documents/GitHub/NAS/nas-data/_INGEST/ready
```

Validate from the backend folder:

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

If it prints Archive Assistant's own `data/_INGEST`, `backend/.env` did not load or the backend was started from the wrong folder.
