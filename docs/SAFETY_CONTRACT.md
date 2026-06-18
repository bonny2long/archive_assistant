# Safety Contract

## Rules

```text
No deletion in v1/v2.
No overwrite.
No embedded tag mutation.
No final move without approval.
No silent metadata edits.
No automatic cleanup.
No active download watching.
No public internet exposure.
No dev reset on real NAS media.
No media-app ownership of ingest.
```

## Why These Rules Exist

- No deletion: prevents loss of source media.
- No overwrite: prevents replacing good files with bad ones.
- No embedded tag mutation: preserves source files.
- Approval before move: keeps Bonny in control.
- No silent metadata edits: candidates must be reviewed.
- No automatic cleanup: leftovers may still matter.
- No active download watching: Intake Watcher owns upload completion.
- No public exposure: this is a local/NAS admin tool.
- No reset on NAS media: reset is for development fixtures only.
- No media-app ownership of ingest: media apps should read libraries, not mutate ingest.

Before real NAS installation, reset UI/API behavior must be removed or hard-disabled. In bridged local development, reset sends test data back to the stored source path, which may be the shared ready folder.
