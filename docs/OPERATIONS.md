# Operations Guide

## Day To Day

1. Wait for Intake Watcher to show Ready for Archive Assistant.
2. Open Archive Assistant.
3. Confirm the header shows the expected ready ingest path.
4. Scan ingest.
5. Review/edit metadata.
6. Approve.
7. Move approved.
8. Confirm final library folder and manifest/log.

## Before Scanning

Check:

- Intake Watcher says ready.
- Archive Assistant header says `Scanning ingest: .../_INGEST/ready`.
- Backend was restarted after `.env` changes.
- In bridge mode, the path should be `nas-data/_INGEST/ready`, not the project `data/_INGEST`.

## Safe To Approve

A batch is safe to approve when blocking review items are resolved, metadata looks right, and destination preview is correct.

## Needs Metadata

Recognized media with weak or incomplete metadata goes here for review.

## Quarantine Review

Unknown/unsupported items go here. Quarantine is review, not deletion.

## Moved

Moved in Archive Assistant means the approved media was written to the final library path and should have a manifest/log.

In shared-root local mode, final libraries should be under `nas-data/Music`, `nas-data/Movies`, `nas-data/TV`, `nas-data/Books`, or `nas-data/Audiobooks`.

## Manifests And Logs

Check final media metadata folders and `_REPORTS`.

## Empty Shells And Leftovers

Archive Assistant never cleans up. After a move, the download folder left in `ready` (empty shells, rip logs, cue sheets, `.nfo` files) is Cleaner's to report on. Cleaner waits 30 days, then lists it; it can remove reviewed empty folders only when its production gates are on.

## Quarantine

Open **Quarantine review**. Restore sends an item back to `ready` for another scan; Discard needs a reason and deletes nothing; Undo discard reverses it. Each decision writes a disposition record for Cleaner.
