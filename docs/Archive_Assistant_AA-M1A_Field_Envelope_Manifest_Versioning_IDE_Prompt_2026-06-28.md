# Archive Assistant — AA-M1A Field Envelope + Manifest Versioning IDE Prompt

Owner: Bonny Makaniankhondo  
Project: NAS System / Archive Assistant / Media Metadata Contract  
Date: 2026-06-28  
Status: First implementation slice after AA-M0 spec  

---

## 1. Context

We are continuing Archive Assistant after AA-M0.

AA-M0 is a design/spec phase that defines a media-wide metadata contract for music, audiobooks/books, movies, and TV. The immediate pressure came from BM Radio, but the contract must stay useful for Jellyfin and future media apps too.

Archive Assistant currently works as a safe local media organizer:

- scans ready media
- classifies media
- lets Bonny review/edit metadata
- approves batches
- moves approved media
- writes move/library manifests and logs

Current safety posture must remain unchanged:

- no deletion
- no overwrite
- no embedded tag mutation
- no cloud AI calls
- no internet metadata calls
- no silent metadata acceptance
- no final move without approval

AA-M1A is not the full metadata automation phase. Do not add Llama, MusicBrainz, Mutagen, audio analysis, or external metadata engines yet.

This is a small foundation phase: add a reusable metadata field envelope and versioned manifest helpers so later phases can store source/confidence/approval information cleanly.

---

## 2. Current Code Notes

Latest inspected Archive Assistant code has:

```text
backend/app/models/archive.py
backend/app/schemas/archive.py
backend/app/services/library_manifest.py
backend/app/services/move_manifest.py
backend/app/services/music_metadata.py
backend/app/services/metadata_candidates.py
backend/app/services/scanner.py
backend/app/api/routes.py
```

Current DB model already stores flexible JSON:

```text
IngestBatch.metadata_json
IngestBatch.suggested_metadata
IngestFile.metadata_json
```

Current manifest behavior:

```text
library_manifest.py uses schema_version = 1
move_manifest.py uses MANIFEST_VERSION = "v1"
move_manifest.py writes confirmed_metadata, accepted_unknowns, tracks, files_moved, etc.
```

Do not break existing manifest consumers or regression scripts.

---

## 3. Goal

Implement the first version of the metadata contract foundation.

Add a reusable field envelope format so important metadata values can carry:

```text
value
source
confidence
reason
approval_state
approved
approved_at
approved_by
updated_at
```

Add manifest metadata/version helpers so future manifests can consistently expose:

```text
metadata_contract_version
manifest_version
metadata_version
metadata_generated_at
metadata_sources_summary
```

This phase should be additive and backward-compatible.

Existing scalar metadata fields should continue to work.

---

## 4. Non-Goals

Do not implement:

```text
Mutagen extraction
MusicBrainz import
local AI helper
local Llama calls
internet API calls
audio feature analysis
embedded tag writing
new destructive actions
large UI redesign
BM Radio changes
Jellyfin DB changes
```

Do not rewrite scanner logic.

Do not change destination path logic.

Do not change approval/move behavior.

---

## 5. New Backend Helper

Create a new helper module:

```text
backend/app/services/metadata_contract.py
```

Recommended constants:

```python
METADATA_CONTRACT_VERSION = "aa-m0.1"
DETAILED_FIELD_ENVELOPE_VERSION = 1
```

Required source values:

```text
embedded_tag
folder_inference
filename_inference
path_context
archive_assistant_rule
artist_profile
release_profile
series_profile
show_profile
movie_profile
manual
local_metadata_db
local_audio_analysis
local_ai_suggestion
unknown
```

Required approval states:

```text
pending
approved
rejected
needs_review
inherited
stale
unknown
```

Implement helper functions similar to:

```python
def now_metadata_timestamp() -> str: ...

def metadata_field(
    value,
    *,
    source: str = "unknown",
    confidence: float | None = None,
    reason: str | None = None,
    approval_state: str = "pending",
    approved: bool | None = None,
    approved_at: str | None = None,
    approved_by: str | None = None,
    updated_at: str | None = None,
) -> dict: ...

def is_field_envelope(value: object) -> bool: ...

def field_value(value, default=None): ...

def field_source(value, default="unknown") -> str: ...

def field_confidence(value, default=None): ...

def approve_field(field_or_value, *, approved_by="bonny", reason=None) -> dict: ...

def inherit_field(field_or_value, *, source, reason=None, confidence=None) -> dict: ...

def compact_metadata_value(value): ...

def detailed_metadata_value(value): ...
```

Design rule:

- `field_value()` must work with both scalar old metadata and new envelope metadata.
- `metadata_field()` must clamp confidence to 0.0–1.0 when provided.
- unknown or invalid source values should normalize to `unknown`.
- unknown or invalid approval states should normalize to `unknown` or `pending`.

---

## 6. Manifest Version Helper

In the same helper or a separate small module, add functions to make manifest headers consistent:

```python
def metadata_manifest_header(
    *,
    manifest_type: str,
    manifest_version: str | int,
    media_type: str | None = None,
    metadata_version: str | None = None,
    sources_summary: dict | None = None,
) -> dict: ...
```

The returned object should include:

```text
metadata_contract_version
manifest_type
manifest_version
metadata_version
metadata_generated_at
metadata_sources_summary
```

`metadata_version` can be a simple stable string for now. Options:

- provided value
- generated timestamp string
- or lightweight deterministic hash of compact metadata if easy

Do not over-engineer hashing in this phase.

---

## 7. Integrate With Existing Manifests Additively

### 7.1 library_manifest.py

Update `write_library_manifest()` so every library manifest includes the new contract header fields, while preserving current fields.

Current output has:

```text
schema_version
generated_at
library_path
```

Keep those.

Add fields such as:

```text
metadata_contract_version
manifest_type
manifest_version
metadata_version
metadata_generated_at
metadata_sources_summary
```

Default `manifest_type` may be inferred from filename when not supplied:

```text
music-album.json -> music_album
music-release.json -> music_release
book.json -> book
audiobook.json -> audiobook
movie.json -> movie
tv-show.json -> tv_show
discography.json -> music_discography
```

Do not break existing call sites.

### 7.2 move_manifest.py

Update move manifest output additively.

Keep:

```text
manifest_version
archive_assistant_version
created_at
batch_id
confirmed_metadata
accepted_unknowns
tracks
files_moved
```

Add:

```text
metadata_contract_version
metadata_version
metadata_generated_at
metadata_sources_summary
```

Do not rename current keys.

Do not change the markdown move manifest unless you can add one small line safely, such as:

```text
Metadata contract: aa-m0.1
```

If markdown change risks existing tests, skip markdown.

---

## 8. Add Minimal Detailed Metadata Without Breaking Flat Fields

For this phase, do not convert every metadata field to envelopes.

Instead, add a new optional object where detailed metadata can live:

```text
metadata_json["metadata_contract"]
metadata_json["field_sources"]
metadata_json["field_confidence"]
```

or preferably:

```json
"metadata_contract": {
  "version": "aa-m0.1",
  "fields": {
    "artist": {
      "value": "Nipsey Hussle",
      "source": "manual",
      "confidence": 1.0,
      "reason": "Saved by review editor.",
      "approval_state": "approved",
      "approved": true
    }
  }
}
```

Keep top-level legacy fields like:

```text
artist
album
year
genre
primary_genre
title
show_title
```

Existing UI and move logic should continue reading top-level scalar values.

This phase is foundation, not migration.

---

## 9. Where To Apply Minimal Field Envelopes

Add detailed field envelopes only in safe, obvious places:

### Music album metadata save

When `/batches/{batch_id}/metadata` saves music album metadata, add field envelopes for:

```text
artist / album_artist
album
year
genre or primary_genre
format
```

Source should be:

```text
manual
```

Approval state:

```text
approved
```

Reason examples:

```text
Saved from music album metadata review.
```

### Movie metadata save

When movie metadata is manually saved, add envelopes for:

```text
title
year
edition
format
```

### Book/audiobook metadata save

When manually saved, add envelopes for safe fields already in the UI:

```text
title
author
year
narrator
series
series_index
format
```

Only touch update endpoints if the change is low-risk.

If full multi-media endpoint integration gets too large, implement music first and leave TODO comments for movie/book/audiobook. But do not break the media-wide contract design.

---

## 10. Metadata Sources Summary

Implement a small helper that can summarize field sources in a metadata object.

Example output:

```json
{
  "manual": 4,
  "embedded_tag": 2,
  "folder_inference": 1,
  "unknown": 0
}
```

This can be used in manifests as:

```text
metadata_sources_summary
```

For legacy scalar fields, source can be `unknown` unless a field envelope exists.

---

## 11. Tests / Verification

Add a small test script if practical:

```text
scripts/check_metadata_contract_envelope.py
```

It should verify:

- `metadata_field()` returns the expected shape.
- invalid source normalizes safely.
- confidence clamps or validates safely.
- `field_value()` works for scalar values and envelope dicts.
- `approve_field()` marks approved state.
- manifest header includes required contract/version fields.

Run existing safety checks that are practical:

```bash
cd backend
python -m compileall app
cd ..
python scripts/check_metadata_contract_envelope.py
python scripts/check_core_v1_regression.py
python scripts/check_v2_metadata_candidates.py
python scripts/check_v2_review_acceptance_flags.py
python scripts/check_v2_move_manifest.py
```

If some regression scripts require local fixtures that are unavailable, report which ones could not be run and why.

Frontend build if touched:

```bash
cd frontend
npm run build
```

Do not touch frontend unless needed.

---

## 12. Acceptance Criteria

AA-M1A is done when:

- `backend/app/services/metadata_contract.py` exists.
- Metadata field envelope helpers work with both scalar and envelope values.
- Library manifests include metadata contract/version fields without removing existing keys.
- Move manifests include metadata contract/version fields without removing existing keys.
- Manual metadata saves can store detailed field-source information without breaking legacy scalar metadata.
- Existing scan/review/approve/move behavior still works.
- Backend compile passes.
- Existing relevant regressions pass or documented fixture limitations are reported.
- No embedded tags are mutated.
- No files are deleted.
- No internet/cloud metadata calls are added.

---

## 13. Senior Engineering Notes

Keep this phase small.

The point is not to solve metadata automation yet. The point is to create the contract foundation that later phases can use.

Do not create a complicated database migration unless absolutely needed. The current JSON fields are enough for M1A.

Do not force the UI to display every envelope yet.

Do not convert the whole codebase to the new format in one pass.

This should be a safe additive layer that makes AA-M1B, AA-M2, and the future local metadata database easier.
