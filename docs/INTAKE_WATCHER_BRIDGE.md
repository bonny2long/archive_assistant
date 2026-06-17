# Intake Watcher Bridge

## Why The Bridge Exists

Intake Watcher answers whether an upload is finished.
Archive Assistant answers what the media is and where it should go after review/approval.

The bridge is the ready folder.

## Local Path Setup

Intake Watcher ready:

```text
C:/Users/BonnyMakaniankhondo/Documents/GitHub/NAS/intake-watccher/data/_INGEST/ready
```

Archive Assistant `backend/.env`:

```env
INGEST_ROOT=C:/Users/BonnyMakaniankhondo/Documents/GitHub/NAS/intake-watccher/data/_INGEST/ready
```

Bonny's local folder is currently spelled `intake-watccher` in some places. Use the actual folder name on disk.

## NAS Production Setup

Both apps mount:

```text
/mnt/rust-pool -> /app/data
```

Intake Watcher writes:

```text
/app/data/_INGEST/ready
```

Archive Assistant scans:

```text
/app/data/_INGEST/ready
```

## Verification Commands

```powershell
cd C:\Users\BonnyMakaniankhondo\Documents\GitHub\NAS\archive-assistant-scaffold\archive-assistant-scaffold\backend

python -c "from app.core.config import settings; print(settings.ingest_root); print(settings.ingest_root.exists())"
```

## Troubleshooting

```text
settings.ingest_root.exists() == False -> wrong path spelling or folder missing.
Archive Assistant still scans own data/_INGEST -> .env did not load or backend started from wrong folder.
Ready folder has items but scan finds none -> confirm INGEST_ROOT and restart backend.
```

## Ownership

- Intake Watcher owns active upload completion detection.
- Archive Assistant owns review, approval, final move, and manifests/logs.
- Cleaner owns future leftover cleanup review.

