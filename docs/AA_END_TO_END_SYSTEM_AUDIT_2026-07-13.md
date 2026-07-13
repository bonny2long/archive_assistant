# Archive Assistant End-to-End System Audit

Date: 2026-07-13

Scope: Archive Assistant from `_INGEST/ready` discovery through review, approval, and move readiness.

This audit compares the short path for correctly named media with the guarded path for mixed folders, discographies, fragments, duplicates, and reconstructed parent containers.

## Audit verdict

The core state model is sound:

1. Intake discovery is explicit.
2. Review actions operate on saved database rows.
3. Logical media objects own exact scoped files.
4. Parent containers cannot be approved or moved as normal media.
5. Approval does not move files.
6. Move execution only selects approved batches.
7. Destination conflicts block instead of overwrite.
8. Archive Assistant does not delete media or mutate embedded tags.

The edge-case work has not replaced the ordinary path. Correctly named music albums, multi-disc music albums, audiobooks, EPUB/PDF books, movies, and TV shows still use their direct media-specific review path unless the scanner finds real mixed identity, multiple candidates, duplicate/fragment, or ownership evidence.

Two important limitations remain:

- Standalone CBZ/CBR comics and MOBI/AZW books are not complete first-class scan-to-move flows.
- Dashboard list loading still performs full duplicate/fragment analysis synchronously. Per-row file and candidate lookups were reduced during this audit, but duplicate analysis remains the main scaling risk.

## Authoritative lifecycle

```text
Intake Watcher or manual copy
  -> _INGEST/ready
  -> explicit Scan ingest
  -> filesystem discovery and read-only metadata extraction
  -> IngestBatch and IngestFile database rows
  -> normal media editor OR universal Review Workspace
  -> candidate decisions and scoped child materialization when required
  -> metadata confirmation
  -> approval
  -> Move approved
  -> final media library plus manifests
  -> Cleaner may handle reviewed leftovers later
```

### Discovery boundary

Only an explicit scan operation should inspect `_INGEST/ready`.

The following operations must remain database-only:

- Refresh dashboard
- Open batch detail
- Open Review Workspace
- Save metadata
- Approve a batch
- Split or materialize candidates
- Merge or resolve duplicate fragments
- Load child batches
- Build destination preview

The ready-folder boundary regression passes.

### Review boundary

A normal media batch is one logical object with scoped files.

A source folder becomes a review container only when there is evidence such as:

- multiple candidate identities
- multiple embedded album or book values
- mixed media classes
- source fragments
- a source folder name leaking into media identity
- a blocking reconstruction conflict

Candidate approval confirms a proposed child object. It does not make the parent container move-ready.

### Approval boundary

Single and bulk approval now apply the same major guards:

- unknown or unsupported media cannot approve
- parent containers cannot approve
- required universal review cannot be bypassed
- duplicate or fragment review cannot be bypassed
- incomplete or conflicting music track sets cannot approve
- discography sources require child objects
- blocking metadata review items cannot approve
- weak metadata must be confirmed

Approval only changes database state and locks reviewed metadata for the move plan.

### Move boundary

Move approved only processes rows with status `approved`.

Before moving, the mover rechecks:

- parent/container state
- duplicate/fragment blockers
- music track completeness
- metadata confirmation
- destination conflicts
- destination filename conflicts
- missing source files

Movie, TV, audiobook, book, discography, and music batches have separate move planners. Move actions and manifests preserve source-to-destination evidence.

## Normal media path audit

| Input | Expected classification | Expected review path | Current audit |
| --- | --- | --- | --- |
| One MP3 or FLAC album folder | `music_album` | Music album editor | Pass |
| Music album with Disc 1 / Disc 2 | `music_album` | Music album editor | Pass |
| Explicit audiobook folder or multi-disc book | `audiobook` | Audiobook editor | Pass |
| One EPUB or PDF book | `book` | Book editor | Pass |
| One movie with subtitle/artwork | `video_movie` | Movie editor | Pass |
| TV season with parseable episodes | `video_tv_show` | TV editor | Pass |
| Sidecar-only folder | ignored safely | No media batch | Pass |
| Unsupported loose file | unknown/quarantine boundary | No normal approval | Pass |
| Standalone CBZ/CBR comic | unknown today | Missing first-class comic flow | Gap |
| Standalone MOBI/AZW/AZW3 book | unknown today | Missing first-class alternate ebook flow | Gap |

## Edge and container path audit

### Discography

A discography source is a parent review container. Releases must become scoped child batches. The parent remains non-moveable, and support-only leftovers remain attached to the parent for later Cleaner review.

### Mixed folder

Universal ingestion classifies each file, builds candidates, and records candidate membership. Music, audiobook, ebook, comic, movie, TV, artwork, and sidecar evidence can coexist without converting the entire source batch to one media type.

Candidate-level media type overrides remain candidate-scoped. Whole-batch conversion is a separate explicit action and requires one candidate to own all primary audio files.

### Duplicate and fragment groups

Duplicate/fragment analysis groups logical batches by canonical identity and destination. Resolution requires verified file ownership. Merge and append reassign database ownership without moving final library files, preserve audit history, and rebuild canonical metadata and destinations.

### Parent remainder

Unowned artwork, playlists, sidecars, and other support files remain on the parent. Archive Assistant does not guess ownership and does not delete them. A drained parent is a processed intake container, not active review work.

## Findings

### High: standalone comic and alternate ebook support is incomplete

The universal classifier recognizes CBZ, CBR, CB7, CBT, MOBI, AZW, and AZW3 evidence inside mixed sources. The root scanner and final media-specific model do not provide an equivalent complete standalone flow.

Current effects:

- A pure CBZ/CBR folder can become unknown/quarantine.
- A comic candidate materializes as detected type `book`.
- Comic destination preview can say `Comics/Library`, while the book mover is authoritative later.
- MOBI/AZW files are recognized as document evidence in some services but are not primary root book files.

Do not use a comic as a required acceptance item until a dedicated comic/book alternate-format phase closes this gap.

### Medium: duplicate analysis remains on the dashboard critical path

Every batch-list request still builds the complete active duplicate/fragment view. This keeps dashboard labels truthful but can make a large saved database slow.

This audit removed repeated visible-row file counts and candidate-ID queries by preloading them. Actual parent/container calculations now remain concentrated on real parent rows. A later performance phase should move duplicate analysis to an indexed snapshot or explicitly invalidated cache without weakening review truth.

### Low: pending pagination totals need a larger-data check

The pending endpoint filters drained parents after fetching a page and then reports the visible page length as total. This is harmless for the current frontend request size in small tests, but it is not a truthful total for multiple pages.

### Test tooling: two broad scripts did not terminate promptly

The focused regressions passed. `check_audiobooks_foundation.py` and `check_v2_move_manifest.py` did not terminate within the bounded audit window and their child processes were stopped. Their focused replacement checks and the existing core regression cover the relevant behavior, but these scripts should be profiled before being used as routine smoke tests.

## Changes made during this audit

1. Bulk approval now checks universal review routing, matching single approval.
2. The bulk regression proves a normal clean album still approves.
3. The bulk regression proves a mixed source with two embedded album identities cannot bypass Review Workspace.
4. Batch-list queries preload visible file ownership and candidate IDs, removing repeated normal-row lookups.

## Recommended manual acceptance set

Use small copies. Do not start with the large historical drive-download folders.

### 1. Normal music album

Example:

```text
Artist - Album (2020)
  01 - First Track.flac
  02 - Second Track.flac
  cover.jpg
```

Expected:

- one music album batch
- no Review Workspace requirement
- cover attached to the album
- FLAC destination
- approve after metadata confirmation

### 2. Multi-disc music album

```text
Artist - Album (2020)
  Disc 1
  Disc 2
```

Expected:

- one music album, not a discography
- disc count greater than one
- no false source-fragment block

### 3. Audiobook

Use one clearly named book with two disc folders and one cover.

Expected:

- one audiobook candidate
- all book audio remains grouped
- cover follows the audiobook only when ownership is provable
- unrelated audio becomes another candidate or remains on the parent

### 4. Movie

Use one movie file, one subtitle, and one poster.

Expected:

- one movie batch
- subtitle and poster attached
- existing destination blocks overwrite

### 5. TV

Use one small season with two parseable episodes and an optional subtitle.

Expected:

- one TV batch
- episode codes remain unique
- season destination is correct

### 6. EPUB or PDF book

Use one book and one cover.

Expected:

- one book batch
- correct author/title review
- cover attached only to that book

### 7. Small discography

Use one artist with two albums, two or three tracks each.

Expected:

- one parent review container
- two candidate releases
- two child batches after materialization
- parent cannot approve or move

### 8. Small mixed folder

Use one two-track music album, one short audiobook sample with explicit book naming, one EPUB/PDF, and one unrelated image.

Expected:

- separate candidate groups
- candidate-specific editors
- no whole-parent media type conversion
- only approved candidates materialize
- unowned support remains on parent

### 9. Unsupported and sidecar-only inputs

Expected:

- unsupported media cannot approve
- sidecar-only folders do not become fake music albums
- no deletion

## Test procedure

1. Start backend and frontend manually.
2. Copy only the selected small fixtures into `_INGEST/ready`.
3. Click Scan ingest once.
4. Use Refresh for all later DB reloads.
5. Record the batch ID, classification, file count, editor, destination, and blockers.
6. Review and approve one item at a time.
7. Verify Approved before running Move approved.
8. Confirm destination previews and existing-folder conflict behavior.
9. Keep Debug JSON for any failure before resetting the database.
10. Do not combine comic acceptance with the current pass; track it as a separate implementation phase.

## Bounded validation completed

Passed:

- root ingest classification
- audiobook detection and review display
- audiobook multi-disc candidate collapse
- movie final polish
- TV final polish
- book parsing and collection review
- destination no-overwrite guard
- internal actions do not scan ready
- bulk approval including mixed-source routing guard
- parent candidate materialization
- duplicate/fragment review
- media type correction and nested release repair
- multi-candidate music routing
- backend compileall

The full frontend build and final diff checks are required after this document and code changes.
