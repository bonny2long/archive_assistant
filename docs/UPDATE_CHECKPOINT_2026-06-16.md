# Update Checkpoint - 2026-06-16

Use this before continuing app work. It captures the current known-good state
after the Severance reset recovery and TV folder title cleanup.

## Branch

Current branch:

`v2_tv_retry_clean`

Latest commit:

`7584bcc fix tv folder title cleanup`

At the time of this checkpoint, `git status --short --branch` showed the branch
clean against `origin/v2_tv_retry_clean`.

## Confirmed Recovery State

Severance recovery worked:

- Severance is back in `_INGEST`.
- Scan detects it as `video_tv_show`.
- 9 MP4 episodes are detected.
- 1 season is detected.
- 0 specials are detected.
- No quarantine row is created for the leftover `Read Me.txt`.

Important recovered source shape:

`data\_INGEST\Severance Season 1 Mp4 1080p`

Expected restored episode shape:

`Season 01\S01E01.mp4` through `Season 01\S01E09.mp4`

## Latest Fix

File changed:

`backend/app/services/video_metadata.py`

Scope:

- TV folder-name cleanup only.
- `parse_tv_folder_name()` now removes release/container tokens after removing
  season tokens.
- Added release-tag cleanup coverage for `mp4`, `mkv`, `10bit`, and `10bits`.
- Existing cleanup already covered tokens such as `1080p`, `720p`, `2160p`,
  `4k`, `WEBRip`, `BluRay`, `x264`, and `x265`.

Result:

- `Severance Season 1 Mp4 1080p` parses as show title `Severance`.
- Suggested destination becomes `data/TV/Library/Severance`.

## Regression Check Added

File added:

`scripts/check_tv_folder_title_cleanup.py`

What it verifies:

- `Severance Season 1 Mp4 1080p` scans as `show_title == "Severance"`.
- Suggested destination is `data/TV/Library/Severance`.
- 9 episodes are detected.
- 1 season is detected.
- 0 specials are detected.
- Missing episode titles remain a warning, not a blocking review item.
- `Read Me.txt` is counted as an ignored sidecar.
- No `unknown_type` or `unsupported_file` quarantine batch is created.
- No approval or move is performed.

## Verified Commands

These passed after the latest fix:

```powershell
.\backend\.venv\Scripts\python.exe .\scripts\check_tv_folder_title_cleanup.py
```

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

## Do Not Change Without Explicit Request

- Reset logic.
- TV move logic.
- Sidecar-only folder behavior.
- Frontend.
- Actual media files.

## Next Logical Step

Run a normal scan from the app or approved script path and confirm the UI/API
shows the Severance batch as:

- Type: `video_tv_show`
- Show title: `Severance`
- Destination: `TV/Library/Severance`
- Episodes: 9
- Seasons: 1
- Specials: 0

Do not approve or move until the scan output is reviewed.
