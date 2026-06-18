# Changelog

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
