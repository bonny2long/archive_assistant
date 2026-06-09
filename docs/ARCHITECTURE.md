# Archive Assistant Architecture

## V1 principle

Deterministic tools first. AI later. Human approval before write actions.

## Local services

- FastAPI backend
- SQLite database
- React dashboard
- Python scan worker
- Python approved-move worker

## V1 data flow

1. Copy test music files into `data/_INGEST/music`.
2. Scanner reads files and metadata.
3. Scanner creates `ingest_batches` and `ingest_files` rows.
4. Scanner writes JSON reports to `data/_REPORTS/ingest-reports`.
5. Dashboard shows pending batches.
6. Bonny approves, rejects, or sends to recovery.
7. Mover moves only approved files.
8. Mover writes sidecar metadata and move logs.
9. Database creates permanent `archive_items` records.

## Permissions design for NAS later

Run the deployed app as `archive-assistant` service user.

Allow access only to:

- `_INGEST`
- `_STAGING`
- `_QUARANTINE`
- `_REPORTS`
- `_METADATA_RECOVERY`
- `Music`
- `Movies`
- `TV`
- `Books`
- `Audiobooks`

Do not allow access to legal documents, financial documents, secrets, or TrueNAS system paths.
