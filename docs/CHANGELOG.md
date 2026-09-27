# Changelog

## 2026-09-27 - Docs brought up to date

- README, architecture, testing, roadmap, operations, safety, and Cleaner boundary rewritten for the current system and the runbook v12 layout.
- Added `backend/.env.example`.
- Dated handoff and audit documents are marked historical.

## 2026-09-27 - Pre-existing failures fixed

- Fixed: OVA specials had no move destination because the episode mover only routed specials, OAD, and extras groups. OVAs now go to `Specials/` with the others.
- Fixed: a new TV or movie folder with the same name as a quarantined item took over the quarantined row, losing track of the quarantined files.
- Fixed: missing music disc tags were hidden by a default of disc 1, so untagged CD1/CD2 folders were reported as plain duplicates instead of "disc numbers missing". Track evidence now records `disc_source` (filename, tag, or default).
- Release folder names: uploader handles and bitrate numbers after the last bracket ("[FLAC] 88", "[FLAC]-Sc4r3cr0w"), trailing emoji, and remaster/reissue/anniversary years no longer leak into the suggested album or release year. Tag years are used instead.
- Windows " - Copy" suffixes are ignored when parsing folder and file names.
- Updated stale checks to the current contracts: discographies split into child album batches before moving, zero-byte videos are ignored as corrupt, TV `video_file_count` is episodes plus specials. `check_tv_large_mixed_show_review.py` could never fail before; its check helper now counts failures.
- Added `check_release_folder_noise.py`, `check_universal_ingestion_m4d1.py`, `check_tv_show_hardening.py`, and `check_tv_large_mixed_show_review.py` to the Core V1 regression suite. `check_discography_intake.py` passes again and remains a targeted run.

## 2026-09-26 - Multi-disc releases and workflow dead ends

- Multi-disc releases are now grouped as one release. Album or book names ending in a disc marker ("Dune Disc 1", "Album (Disc 2)", "Album - CD 3") have the marker removed before grouping. A bare "(1)" is only treated as a disc when the disc-number tag and a "CD 1" style folder agree.
- Folders such as "Dune Disc 1" are recognised as disc folders, not separate books or releases.
- A multi-disc audiobook with no disc tags uses its disc folder number, and one stray album tag on a single disc no longer blocks single-book grouping. The stray value is kept as `title_outliers` evidence.
- An approved single audiobook candidate no longer demands child batches because of per-disc album tags, matching the existing music rule. Before this, a correctly grouped multi-disc audiobook could never be approved.
- The approve message no longer says "multiple candidate groups" when the only issue is differing album tags.
- Send to recovery now refuses moved, merged, and quarantine-held batches. Unknown items go back to quarantine review instead of the metadata recovery dead end.
- Scans retire rejected or recovery-state unknown rows whose files no longer exist.
- Added `scripts/repair_foreign_root_batches.py` to hide rows left by test runs against another data root, with a verified backup and a dry run by default.
- Added `scripts/check_multidisc_disc_markers.py` to the Core V1 regression suite.

## 2026-09-26 - Quarantine lifecycle and disposition records

- Quarantined items can now be restored, discarded, or have a discard undone.
- Restore moves the item back into ready and returns it to Quarantine review. Run Scan ingest afterwards to re-classify anything fixed while it sat in quarantine.
- Discard requires a reason and deletes nothing. The item stays in quarantine as `discard_approved` until Cleaner's waiting period passes.
- Every quarantine, restore, discard, undo discard, and reject writes an append-only record to `_REPORTS/archive-assistant/dispositions`.
- Fixed: restoring grouped loose files always failed because the restore target was the ingest root itself.
- Fixed: retired quarantine rows blocked an unknown folder or audiobook with the same path from ever being classified again.
- Unsupported files now land in `_QUARANTINE/unsupported-file` instead of `unknown-type`.
- Reject now refuses items that are in quarantine or marked for discard.
- Added `scripts/check_quarantine_lifecycle.py` to the Core V1 regression suite.

## 2026-06-18 - Shared NAS-style local data root

- Configured Archive Assistant local bridge mode around shared `NAS/nas-data`.
- Documented `DATA_ROOT` plus `INGEST_ROOT` so scans and final moves use the same shared root.
- Clarified that project `data/_INGEST` is not the normal scan lane in bridge mode.
- Added shared folder ownership notes for Intake Watcher, Archive Assistant, and future Cleaner.

## 2026-06-17 - Local multi-app bridge proven

- Documented Intake Watcher -> Archive Assistant ready-folder bridge.
- Confirmed Archive Assistant can scan Intake Watcher's ready folder via `INGEST_ROOT`.
- Confirmed PDF/book flow from ready -> scan -> review -> approve -> move -> manifest.
- Confirmed large music discography flow into `Music/Discographies/Kanye West`.
- Confirmed Lil Wayne discography/mixtape flow into `Music/Discographies/Lil Wayne Mixtapes`.
- Clarified Cleaner remains future-only.
- Refreshed docs for the two-app workflow and NAS deployment direction.
