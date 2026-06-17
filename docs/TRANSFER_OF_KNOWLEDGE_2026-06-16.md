# Transfer Of Knowledge - Archive Assistant

Date: 2026-06-16

Use this file to start a fresh chat with context preserved. The current thread became long and repeated script runs were getting noisy.

## Project

Repository:

`C:\Users\BonnyMakaniankhondo\Documents\GitHub\NAS\archive-assistant-scaffold\archive-assistant-scaffold`

Main backend files involved recently:

- `backend/app/services/scanner.py`
- `backend/app/services/dev_reset.py`
- `scripts/check_root_ingest.py`
- `scripts/check_reset_safety.py`
- `backend/app/api/routes.py`

## Current User Constraints

Do not change these unless explicitly requested:

- TV parser logic
- TV move logic
- Frontend
- Actual media files, unless explicitly approved

Avoid rerunning scripts repeatedly if they appear stuck. Add diagnostics first, then run once.

## Known Media State

Severance was found and is not lost:

`data\TV\Library\Severance\Season 01`

It contained 9 MP4 files:

- `S01E01.mp4`
- `S01E02.mp4`
- `S01E03.mp4`
- `S01E04.mp4`
- `S01E05.mp4`
- `S01E06.mp4`
- `S01E07.mp4`
- `S01E08.mp4`
- `S01E09.mp4`

The original ingest leftover folder existed with only:

`data\_INGEST\Severance Season 1 Mp4 1080p\Read Me.txt`

The DB check at the time showed no Severance `ingest_batches` and no Severance `move_actions`, so reset could not restore it using tracked move rows.

## Root Cause Found

Reset restores moved files from `MoveAction` rows. If the DB rows are cleared but library files remain, reset sees those files as untracked library media.

That explains why reset did not move Severance back to ingest.

## Recent Intended Fixes

### Sidecar-only folder scan behavior

Goal:

- A folder containing only ignored sidecars like `.txt`, `.nfo`, `.url`, `.sfv`, `.md`, `.log`, `.m3u`, `.md5` should not create an `unknown_type` quarantine batch.
- It should be reported as `ignored_sidecar_only_folder`.

Relevant file:

`backend/app/services/scanner.py`

### Loose unsupported root file behavior

Goal:

- A loose unsupported file directly under `_INGEST`, such as `notes.txt`, should be skipped/report-only.
- It should not create an `unknown_type` or `unsupported_file` quarantine batch.
- Meaningful unknown folders should still be quarantined.

Current script expectation:

`scripts/check_root_ingest.py` expects `notes.txt` to be skipped safely.

### Reset safety diagnostics

Goal:

- Reset safety scripts must use temp roots only.
- They must not scan the real project `data` folder.
- They must clean temp roots in `finally`.
- They should print visible phase markers and use `faulthandler.dump_traceback_later(15, repeat=True)` while debugging.

Relevant files:

- `backend/app/services/dev_reset.py`
- `scripts/check_reset_safety.py`

## Script Runtime Problem

The user reported this command looked stuck:

```powershell
.\backend\.venv\Scripts\python.exe .\scripts\check_root_ingest.py
```

Do not keep rerunning it blindly.

Expected diagnostic behavior now:

- It should print phase markers immediately.
- If it hangs for 15 seconds, faulthandler should print a stack trace.
- The next useful evidence is the faulthandler stack trace.

Important: In this environment, command output may not stream until process exit, so local terminal output is more useful for diagnosing hangs.

## Commands The User Wants Run Only After Guardrails

Run only these, in this scope:

```powershell
.\backend\.venv\Scripts\python.exe .\scripts\check_root_ingest.py
```

```powershell
$env:PYTHONPATH='backend'; $env:DEBUG='true'; .\backend\.venv\Scripts\python.exe .\scripts\check_reset_safety.py
```

```powershell
python -m compileall backend/app scripts
```

```powershell
git diff --check
```

Do not run:

```powershell
python -m compileall backend scripts
```

That walks `backend/.venv` and produces huge output.

## Current Next Step

Start by inspecting current diffs and the current versions of:

- `scripts/check_root_ingest.py`
- `scripts/check_reset_safety.py`
- `backend/app/services/scanner.py`
- `backend/app/services/dev_reset.py`

Then verify:

- `check_root_ingest.py` has no DB setup, no full scan, no reset call.
- `check_root_ingest.py` deletes only `C:\tmp\archive-root-ingest-*`.
- `check_reset_safety.py` deletes only `C:\tmp\archive-reset-safety-*`.
- `check_reset_safety.py` sets a temp root before calling reset.
- `dev_reset.py` refuses script reset if any guarded reset path is outside the temp root.

If `check_root_ingest.py` still hangs, use the faulthandler stack trace to identify the exact line before making more changes.

## Addendum - 2026-06-17 local Intake Watcher bridge proof

Intake Watcher MVP was created as a separate app. It promotes stable uploads from incoming to ready. Archive Assistant was configured to scan Intake Watcher's ready folder by setting INGEST_ROOT. Local proof cases passed for PDFs/books and large music discographies. Cleaner remains future-only.
