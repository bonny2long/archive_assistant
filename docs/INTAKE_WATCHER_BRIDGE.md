# Intake Watcher Bridge

## Why The Bridge Exists

Intake Watcher answers whether an upload is finished.
Archive Assistant answers what the media is and where it should go after review/approval.

The bridge is the shared ready folder under `nas-data`.

## Local Path Setup

Shared local root:

```text
C:/NAS-Local/nas-data
```

Archive Assistant `backend/.env`:

```env
DATA_ROOT=C:/NAS-Local/nas-data
INGEST_ROOT=C:/NAS-Local/nas-data/_INGEST/ready
```

Archive Assistant's project `data/_INGEST` is not the normal scan lane in bridge mode.

## Shared Folder Contract

| Path | Owner / purpose |
| --- | --- |
| `nas-data/_INGEST/incoming` | Intake Watcher watches active copies/downloads. |
| `nas-data/_INGEST/intake-processing` | Intake Watcher temporary promotion lane. |
| `nas-data/_INGEST/ready` | Archive Assistant scan input. |
| `nas-data/_INGEST/failed` | Intake Watcher blocked/problem lane. |
| `nas-data/_INGEST/leftover-review` | Cleaner / human review. |
| `nas-data/_STAGING` | Archive Assistant working area. |
| `nas-data/_QUARANTINE` | Archive Assistant review/quarantine area. |
| `nas-data/_REPORTS/intake-watcher` | Intake Watcher logs. |
| `nas-data/_REPORTS/archive-assistant` | Archive Assistant scan/move/review logs. |
| `nas-data/_REPORTS/cleaner` | Cleaner plan and execution reports. |
| `nas-data/Music` | Archive Assistant final music output. |
| `nas-data/Movies` | Archive Assistant final movie output. |
| `nas-data/TV` | Archive Assistant final TV output. |
| `nas-data/Books` | Archive Assistant final book output. |
| `nas-data/Audiobooks` | Archive Assistant final audiobook output. |

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
cd C:\Dev\NAS\archive_assistant\backend

python -c "from app.core.config import settings; print(settings.data_root); print(settings.ingest_root); print(settings.ingest_root.exists())"
```

## Troubleshooting

```text
settings.ingest_root.exists() == False -> wrong path spelling or folder missing.
Archive Assistant still scans own data/_INGEST -> .env did not load or backend started from wrong folder.
Ready folder has items but scan finds none -> confirm INGEST_ROOT and restart backend.
Moves still write to project data folders -> DATA_ROOT was not set or a specific destination folder env var overrides it.
```

## Ownership

- Intake Watcher owns active upload completion detection.
- Archive Assistant owns review, approval, final move, and manifests/logs.
- Cleaner owns future leftover cleanup review.
