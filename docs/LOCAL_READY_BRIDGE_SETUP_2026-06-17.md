> **Historical (2026-06-17).** This records the system as it was on that date. Paths, versions and behavior may be out of date. For the current state see [README.md](../README.md) and the NAS runbook v12.

# Local Ready-Folder Bridge Setup - 2026-06-17 Checkpoint

This dated checkpoint is kept for project history.

The current bridge documentation lives at:

```text
docs/INTAKE_WATCHER_BRIDGE.md
```

Current shared local path:

```env
DATA_ROOT=C:/NAS-Local/nas-data
INGEST_ROOT=C:/NAS-Local/nas-data/_INGEST/ready
```

Validate from the backend folder:

```powershell
cd C:\Dev\NAS\archive_assistant\backend

python -c "from app.core.config import settings; print(settings.data_root); print(settings.ingest_root); print(settings.ingest_root.exists())"
```

Expected:

```text
C:\NAS-Local\nas-data
C:\NAS-Local\nas-data\_INGEST\ready
True
```

If it prints Archive Assistant's own `data/_INGEST`, `backend/.env` did not load or the backend was started from the wrong folder.
