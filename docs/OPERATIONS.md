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

## Safe To Approve

A batch is safe to approve when blocking review items are resolved, metadata looks right, and destination preview is correct.

## Needs Metadata

Recognized media with weak or incomplete metadata goes here for review.

## Quarantine Review

Unknown/unsupported items go here. Quarantine is review, not deletion.

## Moved

Moved in Archive Assistant means the approved media was written to the final library path and should have a manifest/log.

## Manifests And Logs

Check final media metadata folders and `_REPORTS`.

## Empty Shells And Leftovers

Empty shells and leftovers are not Archive Assistant v2 cleanup work.
Leave them visible until Cleaner/v3 is built and proven.

