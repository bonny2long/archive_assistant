# Testing

All checks use temporary folders and in-memory SQLite databases. None touch `C:\NAS-Local\nas-data`.

## Standard suite

```powershell
Set-Location C:\Dev\NAS\archive_assistant
$env:DEBUG="true"; $env:PYTHONPATH="backend"; $env:PYTHONIOENCODING="utf-8"
backend\.venv\Scripts\python.exe -m compileall -q backend/app scripts
backend\.venv\Scripts\python.exe scripts\check_core_v1_regression.py
Set-Location frontend; npm.cmd run build; Set-Location ..
git diff --check
```

`check_core_v1_regression.py` runs 24 checks with a timeout each, including:

```text
check_quarantine_lifecycle.py        quarantine, restore, discard, undo, reject, recovery, dispositions
check_multidisc_disc_markers.py      disc-marker rules and multi-disc audiobook grouping
check_release_folder_noise.py        folder-name clean-up and Windows " - Copy" suffixes
check_universal_ingestion_m4d1.py    grouping, fragments, missing disc numbers
check_tv_show_hardening.py           TV subtitles, artwork, sidecars
check_tv_large_mixed_show_review.py  OAD/OVA/SP/part/fractional specials and routing
check_qa1_all_media_acceptance_gate.py and the other Core V1 contracts
```

## Targeted checks

Run on their own when touching the related area:

```text
scripts/check_discography_intake.py        discography split into child albums, move, reset
scripts/check_tv_anime_specials_regression.py
scripts/check_root_ingest.py
scripts/check_reset_safety.py
scripts/check_stale_quarantine_repair.py
scripts/check_audiobooks_foundation.py
scripts/check_library_metadata_manifests.py
```

## Manual proof

```text
Intake Watcher -> ready -> Scan ingest -> review -> approve -> move -> manifest
Multi-disc album and multi-disc audiobook land as one release
Unknown folder -> quarantine -> discard / undo / restore
Destination collision is refused, nothing overwritten
```

PASS means the behavior works without changing any safety rule.
