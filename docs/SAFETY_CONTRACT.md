# Safety Contract

## Rules

```text
No deletion (discard only marks quarantined items for Cleaner).
No overwrite.
No duplicate content: a file whose exact bytes already exist in the library or in an earlier batch is never moved.
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

- No deletion: prevents loss of source media. Cleaner, a separate app, is the only future deletion authority.
- No overwrite: prevents replacing good files with bad ones.
- No duplicate content: this NAS is storage, not only a player. Two copies of one file can get different folder names (one has a year, one does not), so names cannot catch them. Archive Assistant compares SHA-256 of every audio, video and book file at approval, in the move pre-check, and inside the mover. Cover art, subtitles, sidecars and empty files are ignored. A duplicate stays where it was and the batch goes back to review; reject it or remove the other copy.
- One move at a time: a move renames files and then records the result, so two overlapping runs mislabel finished batches. A second request is refused with "a move is already running".
- No embedded tag mutation: preserves source files.
- Approval before move: keeps Bonny in control.
- No silent metadata edits: candidates must be reviewed.
- No automatic cleanup: leftovers may still matter.
- No active download watching: Intake Watcher owns upload completion.
- No public exposure: this is a local/NAS admin tool.
- No reset on NAS media: reset is for development fixtures only.
- No media-app ownership of ingest: media apps should read libraries, not mutate ingest.

Before real NAS installation, reset UI/API behavior must be removed or hard-disabled. In bridged local development, reset sends test data back to the stored source path, which may be the shared ready folder.
