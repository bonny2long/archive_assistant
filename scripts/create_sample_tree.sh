#!/usr/bin/env bash
set -euo pipefail
mkdir -p data/_INGEST
mkdir -p data/_STAGING
mkdir -p data/_QUARANTINE/metadata-recovery data/_QUARANTINE/duplicate-suspects data/_QUARANTINE/delete-review
mkdir -p data/_REPORTS/ingest-reports data/_REPORTS/move-logs
mkdir -p data/Music/Library/FLAC data/Music/Library/MP3 data/Music/Discographies data/Music/Metadata
printf "Sample tree ready. Copy intake folders directly into data/_INGEST.\n"
