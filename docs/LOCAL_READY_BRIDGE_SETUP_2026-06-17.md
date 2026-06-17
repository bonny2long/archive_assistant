# Local Ready-Folder Bridge Setup - 2026-06-17 Checkpoint

This dated checkpoint is kept for project history.

The current bridge documentation lives at:

```text
docs/INTAKE_WATCHER_BRIDGE.md
```

Current proven local path:

```env
INGEST_ROOT=C:/Users/BonnyMakaniankhondo/Documents/GitHub/NAS/intake-watccher/data/_INGEST/ready
```

Validate from the backend folder:

```powershell
cd C:\Users\BonnyMakaniankhondo\Documents\GitHub\NAS\archive-assistant-scaffold\archive-assistant-scaffold\backend

python -c "from app.core.config import settings; print(settings.ingest_root); print(settings.ingest_root.exists())"
```

Expected:

```text
...\intake-watccher\data\_INGEST\ready
True
```

If it prints Archive Assistant's own `data/_INGEST`, `backend/.env` did not load or the backend was started from the wrong folder.
