# Cleaner Boundary

Cleaner is a separate app (`C:\Dev\NAS\cleaner`). Archive Assistant never cleans up or deletes anything; it hands Cleaner evidence on disk.

## Cleaner Today

```text
Reports leftovers in ready, failed, staging, leftover-review and quarantine.
Waits until a leftover is 30 days old (MIN_AGE_DAYS).
Requires an Archive Assistant move manifest with verified destinations.
Removes reviewed empty folders only, and only when all production gates are on.
Logs every plan and every removal.
```

## Cleaner Later

```text
Read every move manifest per source folder and these disposition records.
Ask Archive Assistant whether a source folder still has pending batches.
Route deletions through a 14-day trash hold.
Clean approved quarantine discards and known junk only after that.
```

## Cleaner Must Not

```text
Delete quarantined files automatically.
Delete files that were never moved/classified.
Delete uncertain leftovers silently.
Treat missing metadata as trash.
Run while Archive Assistant is processing a batch.
Run without logs and rollback/audit trail.
```

Keep this document in step with Cleaner's README when Cleaner gains a new action.

## Disposition Records

Archive Assistant records human decisions about items that will not move into a final library. Cleaner should read these records instead of Archive Assistant internals.

Location: `_REPORTS/archive-assistant/dispositions/<timestamp>_<batch_id>_<action>.json`

Records are append-only. The newest record for a batch is its current disposition.

| Action | Meaning | Files are |
|---|---|---|
| `quarantined` | Moved out of ready for later review | In `_QUARANTINE` |
| `restored` | Sent back to ready for review | In `_INGEST/ready` |
| `discard_approved` | A person confirmed it is not needed | Still in `_QUARANTINE` |
| `discard_revoked` | The discard decision was undone | Still in `_QUARANTINE` |
| `rejected` | A person rejected the batch in review | Left where they were |

Key fields: `action`, `batch_id`, `status_before`, `status_after`, `reason`, `created_at`, `original_source_path`, `current_path`, and `inventory`. Paths are relative to the data root. `inventory` lists each file's relative path, size, and modified time at decision time.

Rejected records also carry `scope` and `shared_source_batch_ids`. When other batches share the same source folder, Cleaner must not treat the folder as rejected.

Cleaner should act on `discard_approved` only when it is still the newest record for that batch, and the live files still match `inventory`.

