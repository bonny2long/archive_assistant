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
Do not use reset test data on real NAS media. Before real NAS installation, remove or hard-disable reset UI/API behavior.
