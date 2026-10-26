# NAS Deployment

## NAS Paths

```text
/mnt/rust-pool/_INGEST/ready
/mnt/rust-pool/_STAGING
/mnt/rust-pool/_QUARANTINE
/mnt/rust-pool/_REPORTS
/mnt/rust-pool/Movies
/mnt/rust-pool/TV
/mnt/rust-pool/Music
/mnt/rust-pool/Books
/mnt/rust-pool/Audiobooks
/mnt/fast-pool/apps/archive-assistant
/mnt/fast-pool/apps/archive-assistant/postgres
/mnt/fast-pool/apps/archive-assistant/backups
```

Everything under `/mnt/rust-pool` that the apps move between (`_INGEST`, `_STAGING`, `_QUARANTINE`, `_TRASH`, `_REPORTS` and the libraries) must be one dataset; see the next section. `fast-pool/apps/...` holds app state and is never part of a move.

## Storage layout: one filesystem

Archive Assistant, Intake Watcher and Cleaner move files by **rename**, which is instant and atomic but only works inside one filesystem. Put the whole data root on a single dataset/mount and use plain folders inside it:

```text
nas-data/                      one dataset (or one bind mount in Docker)
  _INGEST/ _STAGING/ _QUARANTINE/ _TRASH/ _REPORTS/
  Music/ Movies/ TV/ Audiobooks/ Books/    plain folders, NOT child datasets
```

Do not create a child dataset (or a separate Docker mount) per media type or per `_INGEST`/`_TRASH`. On ZFS a child dataset is a different filesystem, so a move from `_INGEST` into `Music/Library` could not be a rename. Archive Assistant refuses such a move (it never copies then deletes) and Cleaner refuses a `_TRASH` on another disk, so the symptom would be blocked batches, not damaged files. Snapshots and quotas still work on the one dataset.

Before real data goes in, run this on the NAS as the user the apps run as:

```bash
python scripts/nas_storage_preflight.py --data-root /mnt/<pool>/nas-data
```

It checks that every NAS folder is on one filesystem, that there are no child mounts inside the data root, that a real file can be renamed between the folders, that the user can write, and reports case sensitivity and Unicode filename handling. Exit code 1 means fix the layout first.

## Environment Example

```env
POSTGRES_DB=archive_assistant
POSTGRES_USER=archive_assistant
POSTGRES_PASSWORD=CHANGE_THIS
DATABASE_URL=postgresql+psycopg://archive_assistant:CHANGE_THIS@archive-postgres:5432/archive_assistant
DATA_ROOT=/app/data
INGEST_ROOT=/app/data/_INGEST/ready
ARCHIVE_ASSISTANT_TIMEZONE=America/Chicago
API_DOCS_ENABLED=false
DEV_TOOLS_ENABLED=false
DEBUG=false
```

## Compose Notes

Archive Assistant should mount `/mnt/rust-pool` as `/app/data`.
It should scan `/app/data/_INGEST/ready`.
It should not scan `/app/data/_INGEST/incoming`.

`DATA_ROOT` controls the final library roots. When `DATA_ROOT=/app/data`, Archive Assistant writes final outputs under `/app/data/Music`, `/app/data/Movies`, `/app/data/TV`, `/app/data/Books`, and `/app/data/Audiobooks` unless a specific destination folder env var overrides one of those paths.

## Security

Use LAN/Tailscale/VPN only.
Do not expose Archive Assistant publicly.
Disable API docs/dev tools on NAS.
Changing requests (approve, move, quarantine, edit) are rejected with 403 unless their `Origin` header is a loopback address or is listed in `ALLOWED_ORIGINS`. A web page on another site therefore cannot drive the API through your browser. To use the dashboard from a LAN or Tailscale address, set `ALLOWED_ORIGINS` to that exact address, for example `ALLOWED_ORIGINS=http://192.168.1.50:5173`. Plain scripts such as `curl` send no `Origin` header and are not affected.
Do not use reset test data on real NAS media. Before real NAS installation, remove or hard-disable reset UI/API behavior.
