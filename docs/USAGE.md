# Usage

## Normal Workflow With Intake Watcher

1. Download/copy media into Intake Watcher incoming.
2. Wait for Intake Watcher to show Ready for Archive Assistant.
3. Open Archive Assistant.
4. Confirm header says `Scanning ingest: .../_INGEST/ready`.
5. Click Scan ingest.
6. Review/edit metadata.
7. Approve.
8. Move approved.
9. Confirm final library folder and metadata manifest.

The dashboard shows the current ingest path. Confirm this path before scanning.

## Standalone Development Workflow

Place test copies in Archive Assistant's own `data/_INGEST`, then scan/review/approve/move.

Do not use your only copy of media for tests.

This standalone folder is not the normal scan lane when the Intake Watcher bridge is enabled. In bridge mode, scan `nas-data/_INGEST/ready`.

## Dashboard Buttons

- Refresh: reload batches.
- Scan ingest: scan the configured ingest path.
- Move approved: move approved batches.
- Reset test data: development-only. Never run reset against real NAS media.

## Status Tabs

- All: every active non-merged batch.
- Pending: ready for approval.
- Needs Metadata: recognized media needing review.
- Quarantine: unknown/unsupported/rejected review.
- Approved: waiting to move.
- Moved: completed moves.

## Reviewing Metadata

Use the media-specific editors. Suggestions are candidates only.

Manual edits and confirmation are authoritative.

## Approving Batches

Approve only after blocking review issues are resolved and the destination looks correct.

## Moving Approved

Move approved writes final files, move rows, manifests, and library metadata.

## Checking Manifests And Logs

Check media folder metadata and `_REPORTS` for move manifests/logs.

## Handling Weak Metadata

Weak metadata stays in metadata review. It is not quarantine by default when the media type is recognized.

## Handling Quarantine

Unknown/unsupported items go to quarantine review. Do not delete them manually as cleanup.

## What Not To Do

- Do not scan active downloads.
- Do not approve without review.
- Do not run dev reset on real NAS media.
- Do not use reset as a shared NAS restore tool; it is local-development only.
- Do not treat empty shells/leftovers as safe deletion targets in v2.
