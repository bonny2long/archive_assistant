# Archive Assistant AA-QA1 — All-Media Acceptance Gate

Date: 2026-07-03  
Project: NAS / Archive Assistant  
Phase: AA-QA1  
Status: IDE implementation prompt / QA gate  
Depends on: AA-SYSTEM1 Media-Wide Scoped Object Contract, AA-M4D.5.2 Split Child File-Scoped Metadata Rebuild

---

## 0. Product framing

Archive Assistant is not a music-only tool and not a BM Radio helper app. Archive Assistant is the NAS-wide ingestion, reconstruction, review, approval, manifest, and move-planning authority for all non-photo media.

AA-QA1 is the acceptance gate that proves the Archive Assistant system behaves consistently across supported media classes before the project moves into move-readiness UI, duplicate guard expansion, downstream event logs, or old-modal retirement.

This phase is deliberately a gate, not a feature expansion.

The purpose is to answer one question:

```text
Can Archive Assistant safely process every supported non-photo media class using the same core safety contract?
```

The answer must be proven by automated checks, manual smoke tests, and a written QA result report.

---

## 1. Standing system rule from AA-SYSTEM1

Every media object created by Archive Assistant must be built from scoped file evidence, not blindly copied from a parent folder, source dump, inherited metadata blob, or downloader folder name.

A media object may only claim a file, artwork item, subtitle, sidecar, chapter, track, episode, book, comic issue, movie, or release when that item is proven by at least one of these:

1. Direct file membership in the candidate or batch.
2. Path locality inside the object folder.
3. Embedded metadata that matches the object identity.
4. Explicit user correction or approval.
5. Existing deterministic parser evidence that is written into metadata with source/confidence.

Parent metadata is evidence, not truth.

---

## 2. What this phase does

AA-QA1 adds a media-wide validation gate for Archive Assistant.

It should:

1. Inventory all current media classes Archive Assistant supports.
2. Verify that current regression scripts cover the media classes they claim to cover.
3. Add one umbrella QA script that checks the presence of media-wide contracts, existing media-specific checks, and no known anti-patterns.
4. Add a written QA checklist for manual acceptance.
5. Produce a QA report template that can be filled after manual testing.
6. Identify gaps without adding product behavior.

---

## 3. What this phase does not do

Do not implement any of the following in AA-QA1:

- No new move execution UI.
- No duplicate-detection feature expansion.
- No BM Radio integration.
- No Jellyfin, Navidrome, Audiobookshelf, Calibre, Kavita, or Immich integration.
- No local Llama assistant.
- No Cleaner behavior.
- No deletion.
- No embedded tag mutation.
- No removal of old modals.
- No automatic Intake Watcher handoff changes.
- No schema migration unless absolutely required for a test fixture, which should be avoided.

AA-QA1 is proof and guardrails only.

---

## 4. Files to create

Create:

```text
scripts/check_qa1_all_media_acceptance_gate.py
docs/Archive_Assistant_AA-QA1_All-Media_Acceptance_Gate_2026-07-03.md
docs/AA-QA1_Manual_Test_Report_Template_2026-07-03.md
```

---

## 5. Files to modify

Modify:

```text
scripts/check_core_v1_regression.py
docs/ARCHITECTURE.md
```

Do not modify production behavior files unless the validation reveals a compile/import problem that prevents the gate from running. If that happens, fix only the minimal import/test issue and document it.

---

## 6. Required media classes for the gate

The gate must treat these as first-class Archive Assistant categories:

```text
music_album
music_discography
split_child_music_album
audiobook
multi_disc_audiobook
audiobook_series_or_collection
ebook
pdf_book
book_collection
comic_or_cbz_cbr
movie
movie_collection
tv_show
tv_episode
tv_special_or_anime_special
artwork
subtitle
sidecar_metadata
unknown
mixed_media_folder
quarantine_review_item
```

The gate does not require every class to be fully workspace-native yet. It must clearly distinguish:

```text
covered_by_workspace
covered_by_old_modal_fallback
covered_by_regression_only
known_gap_not_yet_implemented
```

Old modal fallback is acceptable during QA1. Silent behavior is not acceptable.

---

## 7. Automated gate requirements

### 7.1 Create `scripts/check_qa1_all_media_acceptance_gate.py`

This script should be a deterministic guardrail, similar in style to the existing check scripts.

It should verify:

1. AA-SYSTEM1 contract doc exists.
2. AA-QA1 doc exists.
3. Core regression runner includes the AA-SYSTEM1 guard.
4. Core regression runner includes this AA-QA1 guard.
5. The repo contains regression scripts for these domains:
   - universal review contract
   - scan runtime contract
   - movie parsing/final polish
   - movie collection review
   - TV review contract
   - TV final polish
   - discography album review
   - discography singles bucket
   - multi-artist split
   - split child metadata scope
   - books parse/collection review
   - audiobook detection/review display
   - bulk approve
6. `batch_split.py` does not deep-copy parent album metadata into child batches.
7. `batch_split.py` contains file partition logic for split children.
8. Known destructive behaviors remain absent from Archive Assistant production code:
   - no production deletion authority
   - no embedded tag mutation workflow
   - no overwrite-by-default behavior
   - no move without approval
9. Old modal fallback files still exist until replaced type-by-type.
10. The QA1 manual report template exists.

The script should print:

```text
PASS - AA-QA1 all-media acceptance gate verified
```

on success.

### 7.2 Suggested implementation skeleton

Use this skeleton, but adapt paths to the actual repo if needed:

```python
#!/usr/bin/env python3
"""AA-QA1 all-media Archive Assistant acceptance gate."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / "docs"
SCRIPTS = ROOT / "scripts"
BACKEND = ROOT / "backend"
FRONTEND = ROOT / "frontend"

QA1_DOC = DOCS / "Archive_Assistant_AA-QA1_All-Media_Acceptance_Gate_2026-07-03.md"
QA1_REPORT = DOCS / "AA-QA1_Manual_Test_Report_Template_2026-07-03.md"
SYSTEM1_DOC = DOCS / "Archive_Assistant_AA-SYSTEM1_Media-Wide_Scoped_Object_Contract_2026-07-03.md"
ARCHITECTURE = DOCS / "ARCHITECTURE.md"
CORE_REGRESSION = SCRIPTS / "check_core_v1_regression.py"
BATCH_SPLIT = BACKEND / "app" / "services" / "batch_split.py"

REQUIRED_SCRIPTS = [
    "check_universal_review_contract.py",
    "check_scan_runtime_contract.py",
    "check_movie_final_polish.py",
    "check_movie_collection_split_review.py",
    "check_movie_collection_approval_fix.py",
    "check_tv_review_contract_no_regression.py",
    "check_tv_final_polish.py",
    "check_discography_album_editor.py",
    "check_discography_singles_bucket.py",
    "check_multi_artist_split_m4d5.py",
    "check_split_child_metadata_scope_m4d5_2.py",
    "check_books_parse_and_collection_review.py",
    "check_audiobook_detection_and_review_display.py",
    "check_bulk_approve.py",
    "check_system1_scoped_object_contract.py",
]

OLD_MODAL_FALLBACKS = [
    "frontend/src/components/MediaReviewRouter.tsx",
    "frontend/src/components/DiscographyEditor.tsx",
    "frontend/src/components/TvMetadataEditor.tsx",
    "frontend/src/components/MovieCollectionEditor.tsx",
    "frontend/src/components/BookCollectionEditor.tsx",
    "frontend/src/components/AudiobookMetadataEditor.tsx",
]


def read(path: Path) -> str:
    if not path.exists():
        raise AssertionError(f"Missing required file: {path}")
    return path.read_text(encoding="utf-8")


def assert_contains(path: Path, needle: str) -> None:
    text = read(path)
    if needle not in text:
        raise AssertionError(f"Missing required text in {path}: {needle}")


def assert_file(path: Path) -> None:
    if not path.exists():
        raise AssertionError(f"Missing required file: {path}")


def main() -> None:
    assert_file(SYSTEM1_DOC)
    assert_file(QA1_DOC)
    assert_file(QA1_REPORT)
    assert_file(ARCHITECTURE)
    assert_file(CORE_REGRESSION)
    assert_file(BATCH_SPLIT)

    for script_name in REQUIRED_SCRIPTS:
        assert_file(SCRIPTS / script_name)
        assert_contains(CORE_REGRESSION, f"scripts/{script_name}")

    for fallback in OLD_MODAL_FALLBACKS:
        assert_file(ROOT / fallback)

    assert_contains(SYSTEM1_DOC, "Parent metadata is evidence, not truth")
    assert_contains(QA1_DOC, "All-Media Acceptance Gate")
    assert_contains(QA1_DOC, "music_album")
    assert_contains(QA1_DOC, "audiobook")
    assert_contains(QA1_DOC, "book_collection")
    assert_contains(QA1_DOC, "movie_collection")
    assert_contains(QA1_DOC, "tv_show")
    assert_contains(QA1_DOC, "unknown")
    assert_contains(ARCHITECTURE, "Media-Wide Scoped Object Contract")

    split_source = read(BATCH_SPLIT)
    if "metadata = deepcopy(album)" in split_source:
        raise AssertionError("Split children must not deep-copy parent album metadata")
    for phrase in [
        "def _partition_child_files",
        "audio_files",
        "artwork_files",
        "sidecar_files",
        "tracks = [_track_from_audio_file(file) for file in audio_files]",
    ]:
        if phrase not in split_source:
            raise AssertionError(f"Missing split child scoped metadata phrase: {phrase}")

    print("PASS - AA-QA1 all-media acceptance gate verified")


if __name__ == "__main__":
    main()
```

If any required script has a different exact name, keep the actual existing name and document the change in the QA1 report.

---

## 8. Update `scripts/check_core_v1_regression.py`

Add the new QA1 guardrail to the core regression runner.

Required include:

```text
scripts/check_qa1_all_media_acceptance_gate.py
```

The AA-SYSTEM1 guard must remain included.

Do not remove any existing regression script.

---

## 9. Update `docs/ARCHITECTURE.md`

Add a short section:

```markdown
## AA-QA1 — All-Media Acceptance Gate

AA-QA1 verifies that Archive Assistant is being tested as a media-wide NAS ingestion and review system, not as a music-only or BM Radio-only tool.

The gate covers music, discographies, split child albums, audiobooks, books, comics, movies, TV, artwork, subtitles, sidecars, unknowns, mixed-media folders, quarantine review, destination preview, approval behavior, and move readiness.

AA-QA1 does not remove old editors. Old modal editors remain available until each media type is fully workspace-native and retired type-by-type.
```

Add a link to the QA1 doc and report template.

---

## 10. Create `docs/AA-QA1_Manual_Test_Report_Template_2026-07-03.md`

Use this template:

```markdown
# AA-QA1 Manual Test Report

Date:
Tester:
Commit hash:
Environment:
Data root:
Ingest root:

## Summary

Status: PASS / PASS WITH GAPS / FAIL

## Automated validation

- [ ] python -m compileall backend/app
- [ ] python scripts/check_system1_scoped_object_contract.py
- [ ] python scripts/check_qa1_all_media_acceptance_gate.py
- [ ] python scripts/check_core_v1_regression.py
- [ ] cd frontend && npm run build
- [ ] git diff --check

## Media class results

| Media class | Test fixture | Scan | Review | Destination preview | Approval | Move readiness | Result | Notes |
|---|---|---:|---:|---:|---:|---:|---|---|
| music_album |  |  |  |  |  |  |  |  |
| music_discography |  |  |  |  |  |  |  |  |
| split_child_music_album |  |  |  |  |  |  |  |  |
| audiobook |  |  |  |  |  |  |  |  |
| multi_disc_audiobook |  |  |  |  |  |  |  |  |
| ebook |  |  |  |  |  |  |  |  |
| pdf_book |  |  |  |  |  |  |  |  |
| book_collection |  |  |  |  |  |  |  |  |
| comic_or_cbz_cbr |  |  |  |  |  |  |  |  |
| movie |  |  |  |  |  |  |  |  |
| movie_collection |  |  |  |  |  |  |  |  |
| tv_show |  |  |  |  |  |  |  |  |
| tv_special_or_anime_special |  |  |  |  |  |  |  |  |
| artwork |  |  |  |  |  |  |  |  |
| subtitle |  |  |  |  |  |  |  |  |
| sidecar_metadata |  |  |  |  |  |  |  |  |
| unknown |  |  |  |  |  |  |  |  |
| mixed_media_folder |  |  |  |  |  |  |  |  |

## Scoped object checks

- [ ] No child object inherited parent/sibling tracks.
- [ ] No artwork became a track/chapter/episode/book.
- [ ] No sidecar became a primary media object.
- [ ] Subtitles attach only to the correct movie/episode/show.
- [ ] Artwork attaches only to the correct album/book/movie/show unless classified as parent-level artwork.
- [ ] Unknown files require review.
- [ ] Mixed media does not silently move.

## Safety checks

- [ ] No deletion.
- [ ] No overwrite.
- [ ] No embedded tag mutation.
- [ ] No final move without approval.
- [ ] Quarantine remains review-only.
- [ ] Reset/dev tools cannot touch real NAS media.

## Known gaps accepted for now

List each gap and why it is acceptable before UX7.

## Blockers before UX7

List anything that must be fixed before Move Readiness Panel work.
```

---

## 11. Manual acceptance checklist

### 11.1 Music

Test cases:

```text
single album, MP3
single album, FLAC
album with local cover art
music discography
multi-artist discography
split child music_album
single/EP bucket if applicable
```

Pass conditions:

```text
artist/album/year are not taken from drive-download folder names
tracks are audio only
artwork is scoped to the album
sidecars are scoped to the album/release
split child albums do not inherit parent/sibling metadata
FLAC routes to FLAC library when configured
MP3 routes to MP3 library when configured
approval does not move without explicit move command
```

### 11.2 Audiobooks

Test cases:

```text
single audiobook
multi-disc audiobook
audiobook with narrator
series audiobook
book/audiobook mixed folder
```

Pass conditions:

```text
author/title/year are reviewable
narrator is preserved when available
series/order fields are visible in fallback or workspace
chapters/parts do not become separate books unless intended
cover art is scoped to the audiobook
unknown/mixed items require review
```

### 11.3 Books and comics

Test cases:

```text
single EPUB
single PDF
book collection
book series
CBZ/CBR comic if supported
mixed ebook/comic folder
```

Pass conditions:

```text
author/title/series/order are reviewable
cover/artwork does not become a separate book
sidecars remain sidecars
collection items can be included/excluded or sent to fallback editor
unknown files require review
```

### 11.4 Movies

Test cases:

```text
single movie
movie with subtitles
movie with poster/fanart/NFO
movie collection/trilogy
movie with edition tags
existing destination conflict
```

Pass conditions:

```text
title/year/edition parse correctly or require review
subtitle attaches to correct movie
poster/fanart/NFO are scoped to correct movie
movie collection items do not inherit sibling sidecars
existing destination blocks or warns
no overwrite
```

### 11.5 TV

Test cases:

```text
normal season folder
multi-season show
anime specials
OVA/OAD/OAV
S01E13.5-style special
subtitles per episode
show-level artwork/NFO
```

Pass conditions:

```text
show title/season/episode are correct or require review
episode specials do not silently become normal episodes if ambiguous
subtitles attach to correct episode
show-level artwork remains show-level unless explicitly scoped
destination preview uses TV/Show/Season XX pattern
```

### 11.6 Mixed, unknown, quarantine

Test cases:

```text
mixed folder with music + books
folder with only artwork
folder with only sidecars
unknown extension
malformed folder name
source fragment folder
```

Pass conditions:

```text
mixed media does not silently move
artwork-only does not become a fake album/book/movie
sidecar-only does not become a media object
unknown files require review/quarantine
source fragment names are evidence only
```

---

## 12. Validation commands

Run from repo root unless noted:

```powershell
backend\.venv\Scripts\python.exe -m compileall backend\app
backend\.venv\Scripts\python.exe scripts\check_system1_scoped_object_contract.py
backend\.venv\Scripts\python.exe scripts\check_qa1_all_media_acceptance_gate.py
backend\.venv\Scripts\python.exe scripts\check_core_v1_regression.py
cd frontend
npm run build
cd ..
git diff --check
```

Expected:

```text
PASS - AA-SYSTEM1 media-wide scoped object contract guard verified
PASS - AA-QA1 all-media acceptance gate verified
CORE V1 REGRESSION PASSED
frontend build passes
no whitespace errors
```

---

## 13. Product acceptance rules

AA-QA1 is accepted when:

1. The QA1 doc exists.
2. The QA1 manual report template exists.
3. The QA1 automated guard script exists.
4. The QA1 guard is included in core regression.
5. Existing core regression still passes.
6. Frontend build still passes.
7. No destructive behavior was added.
8. No old modal was removed.
9. Gaps are documented, not hidden.
10. The manual QA report is filled for at least the available local fixtures.

AA-QA1 may pass with documented gaps if the gaps are not safety-critical and are explicitly scheduled before move-readiness or modal removal.

AA-QA1 fails if any of these occur:

```text
unscoped child object creation
parent metadata copied as truth
artwork becomes track/book/episode/chapter
sidecar becomes primary media
move allowed without approval
overwrite allowed silently
deletion added to AA
unknown/mixed media silently accepted
old fallback removed before workspace replacement
```

---

## 14. What comes after QA1

If QA1 passes, move to:

```text
AA-UX7 — Move Readiness Panel
```

UX7 should not simply add a dangerous move button. It should show:

```text
approved batches
files to move
destination preview
duplicate/destination conflict status
artwork/sidecars included
manifest/log plan
blocked items
final move action
```

After UX7, move to:

```text
AA-M5 — Destination Duplicate Guard
AA-M6 — Library Event Log
AA-UX8+ — Workspace-native panels by media type
AA-CLEAN1 — Dead modal removal, type by type only
```

