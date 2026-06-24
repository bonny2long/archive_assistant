# Music Not Showing - IDE Handoff

Date: 2026-06-23

## What Is Happening

Music is not currently showing because the app only creates music review batches
from the configured ingest root. This checkout's local paths do not currently
contain any music files to scan:

- `data\_INGEST` is empty.
- `data\Music\Library` contains zero files.
- `data\Music\Discographies` contains zero files.

The music scanner does not use existing library folders as its intake source.
It scans direct children of `settings.ingest_root` and creates batches for
items classified as `music_album` or `music_discography`.

Relevant code:

- `backend/app/services/scanner.py`
  - `scan_music_ingest()` enumerates `settings.ingest_root`.
  - `classify_ingest_item()` classifies audio folders/files.
- `backend/app/api/routes.py`
  - `POST /scan/music` calls `scan_music_ingest()`.
  - `GET /batches/pending` only returns reviewable batch statuses.

## Important Path Rule

Do not put music under this path and expect it to scan:

`data\_INGEST\music\...`

The top-level name `music` is in `IGNORED_INGEST_NAMES`, so it is treated as an
ignored system folder. Music should instead be a direct, meaningful ingest item,
for example:

```text
<INGEST_ROOT>\Artist - Album\01 - Track.flac
<INGEST_ROOT>\Artist Discography\2001 - Album\01 - Track.flac
```

## Likely Configuration Mismatch

`docs/SETUP.md` documents two possible local configurations:

1. Project-local default:

```text
DATA_ROOT=../data
INGEST_ROOT=../data/_INGEST
```

2. Shared NAS ready-folder bridge:

```text
DATA_ROOT=C:/Users/BonnyMakaniankhondo/Documents/GitHub/NAS/nas-data
INGEST_ROOT=C:/Users/BonnyMakaniankhondo/Documents/GitHub/NAS/nas-data/_INGEST/ready
```

If music exists in the NAS folder but not in the UI, the backend may have been
started before `backend/.env` was updated, or from a directory where that `.env`
was not loaded. If the backend is using the project-local default, it will scan
the empty local `data/_INGEST` instead of the NAS ready folder.

## First Checks For The Next IDE Agent

Do not change scanner, mover, reset, TV behavior, or frontend before checking
runtime paths and input placement.

From `backend/`, run:

```powershell
.\.venv\Scripts\python.exe -c "from app.core.config import settings; print(settings.data_root); print(settings.ingest_root); print(settings.ingest_root.exists())"
```

Then list the actual configured intake folder:

```powershell
Get-ChildItem -Force <printed-ingest-root>
```

Confirm that each music drop is a direct child of that root and is not inside a
top-level folder named `music`, `library`, or `metadata`.

After confirming input placement, call or use:

```text
POST /scan/music
```

Then inspect:

```text
GET /batches/pending
GET /batches
```

## Current Boundaries

- Do not move or approve media while diagnosing why it is absent.
- Do not modify reset logic or the TV v2 parity work.
- Do not make the scanner recursively search arbitrary library folders; the
  ingest-root boundary is intentional.
