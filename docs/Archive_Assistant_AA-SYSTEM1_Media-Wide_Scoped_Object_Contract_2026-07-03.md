# Archive Assistant AA-SYSTEM1 — Media-Wide Scoped Object Contract

Date: 2026-07-03  
Project: Bonny NAS / Archive Assistant  
Status: System contract and implementation guardrail  
Phase type: Product architecture checkpoint before further AA implementation

---

## 0. Purpose

Archive Assistant is not a music-only tool and not a BM Radio helper app.

Archive Assistant is the NAS-wide ingestion, reconstruction, review, approval, manifest, and move-planning authority for all non-photo media.

This document defines the system contract Archive Assistant must follow before future features are added, before move execution becomes user-facing, and before old editor paths are removed.

The immediate reason for this contract is the split-child metadata issue discovered during multi-artist discography work. The deeper lesson is larger than music:

> A media object created by Archive Assistant must be built from scoped file evidence, not blindly copied from a parent folder, source dump, or inherited metadata blob.

This rule applies to music, audiobooks, books, comics, movies, TV, artwork, subtitles, sidecars, unknown files, and future media classes.

---

## 1. Archive Assistant’s role in the larger NAS system

Archive Assistant sits between Intake Watcher and final NAS libraries.

```text
Intake Watcher
  -> detects and stabilizes incoming uploads/downloads
  -> hands stable folders to Archive Assistant ready intake

Archive Assistant
  -> scans stable folders
  -> classifies media
  -> reconstructs logical media objects
  -> separates source evidence from final identity
  -> requires review where confidence is weak
  -> previews destinations
  -> blocks unsafe moves
  -> writes manifests, logs, and move plans
  -> moves approved media only when move execution is explicitly triggered

Cleaner
  -> later handles safe cleanup of leftovers, empty shells, and reviewed cleanup targets
  -> Cleaner is the only production deletion authority

Downstream apps
  -> BM Radio reads clean music output
  -> Jellyfin reads clean movie/TV output
  -> Audiobookshelf reads clean audiobook output
  -> Calibre/Kavita or similar apps read clean book/comic output
  -> Immich handles photos outside Archive Assistant
```

Archive Assistant must be designed as a media-wide NAS ingestion system. BM Radio is only one downstream consumer.

---

## 2. Media scope

Archive Assistant owns all non-photo media ingestion and review.

In scope:

```text
music albums
music discographies
multi-artist music dumps
audiobooks
multi-disc audiobooks
multi-book audiobook series
ebooks / EPUB
PDF books
book collections
comics / CBZ / CBR
comic collections
single movies
movie collections / trilogies
TV shows
TV seasons
TV episodes
anime specials / OVA / OAD / named specials
artwork / cover images / posters
subtitles
NFO/XML/JSON sidecars
playlists / cue/log/text sidecars
unknown files
mixed-media folders
quarantine/review cases
manifests
move plans
```

Out of scope:

```text
photos as a primary media class
photo library organization
Immich ingestion
production deletion
embedded tag mutation
AI-only identity decisions
BM Radio station logic
Jellyfin playback management
Cleaner deletion scheduling
```

Photos go to Immich and should not be routed through Archive Assistant except as incidental artwork evidence for another media object.

---

## 3. Core product principle

Archive Assistant must separate four different concepts:

```text
Source container
  The folder/drop/download/archive where files arrived.
  Example: drive-download-20260628T012539Z-3-001

Logical media object
  The actual library item being reviewed.
  Example: Late Registration, Dawn FM, Dune, The Matrix, S01E01

Evidence
  File paths, embedded metadata, folder names, sidecars, artwork, hashes, manifests.
  Evidence can support identity but must not automatically become identity.

Final library object
  The approved destination object that will exist in the NAS library.
  Example: Music/Library/FLAC/Kanye West/2005 - Late Registration
```

A source folder may contain many logical media objects. A logical media object may need multiple files. Archive Assistant must not confuse the source container with the final object.

---

## 4. Source-of-truth hierarchy

When Archive Assistant builds or rebuilds a media object, evidence should be trusted in this order:

```text
1. Exact scoped file membership
   Files explicitly attached to the candidate or child object.

2. Path locality
   Whether artwork, subtitles, sidecars, or supporting files live inside the same album/book/movie/episode folder.

3. Embedded metadata
   Tags such as artist, album, title, author, narrator, year, episode number, track number, duration, codec.

4. Strong structured sidecars
   NFO, XML, JSON, OPF, cue files, manifests, or known metadata formats.

5. User-approved corrections
   Manual identity or media-class decisions saved through the review system.

6. Parent collection metadata
   Evidence only. It may suggest identity, but must not be copied wholesale into child objects.

7. Source folder names
   Weak evidence only, especially for download chunks, drive dumps, torrents, or archive folders.
```

Source folder names such as `drive-download-*`, `part-001`, `chunk-003`, release-group tags, torrent names, and archive dump names must never become final artist/title/author/show identity without explicit review.

---

## 5. File-scoped object contract

Every logical object created by Archive Assistant must obey this contract:

> A media object cannot claim a file, artwork item, subtitle, sidecar, chapter, track, episode, book, or movie unless that item is scoped to the object by exact membership, path locality, embedded metadata, structured sidecar evidence, or explicit user approval.

This applies to all media types.

### 5.1 Required behavior

For every reconstructed object, Archive Assistant must:

```text
1. Determine the object’s actual member files.
2. Partition files by role.
3. Build metadata from scoped files.
4. Treat parent metadata as evidence, not truth.
5. Recompute counters from scoped files only.
6. Preview destination from approved identity only.
7. Preserve source evidence for audit.
8. Block or review uncertain cases.
```

### 5.2 Forbidden behavior

Archive Assistant must not:

```text
copy parent metadata wholesale into a child object
attach sibling artwork to a child item
attach sibling subtitles to a movie/episode
attach parent-level sidecars to every child item
let image files become tracks
let text/log/m3u files become tracks
let source folder names become identity without review
move unknown files silently
overwrite existing final destinations
mutate embedded tags during ingestion/review
perform production deletion
```

---

## 6. Universal file-role partitioning

Every candidate or child object should classify its member files into role buckets before metadata is built.

Minimum role buckets:

```text
primary_media
artwork
subtitle
metadata_sidecar
playlist_or_cue
log_or_report
book_support_file
unknown_support_file
unscoped_file
```

Media-specific examples:

```text
Music:
  primary_media = mp3/flac/m4a/wav/aac/ogg/wma audio tracks
  artwork = jpg/png/webp cover images scoped to album
  metadata_sidecar = cue/nfo/json/xml if scoped to album
  playlist_or_cue = m3u/cue scoped to album only
  log_or_report = log/txt/DR/auCDtect scoped to album only

Audiobooks:
  primary_media = audiobook audio parts/chapters
  artwork = cover image scoped to audiobook/book
  metadata_sidecar = nfo/json/xml/opf if scoped
  unscoped_file = unrelated music/book files in same dump

Books:
  primary_media = epub/pdf/mobi/azw/azw3 depending supported types
  artwork = cover images scoped to book only
  metadata_sidecar = opf/json/xml/nfo scoped to book

Comics:
  primary_media = cbz/cbr/pdf comic files
  artwork = cover/poster files scoped to comic item or series
  metadata_sidecar = comicinfo.xml/json/nfo scoped to comic

Movies:
  primary_media = mkv/mp4/avi/mov/etc.
  subtitle = srt/ass/vtt/sub/idx scoped to movie
  artwork = poster/fanart/cover scoped to movie
  metadata_sidecar = nfo/json/xml scoped to movie

TV:
  primary_media = episode video files
  subtitle = subtitle files matched to episode or season/show
  artwork = show/season/episode art scoped by folder/name
  metadata_sidecar = show/season/episode nfo/json/xml
```

Files that cannot be scoped must remain with the parent/source object, be marked as unscoped, or be routed to review/quarantine. They must not be silently attached to a child object.

---

## 7. Parent and child object rules

Collections, dumps, discographies, seasons, and archives often produce child objects.

Examples:

```text
music discography -> music albums
multi-artist dump -> artist/album children
movie collection -> individual movie children
TV show folder -> season/episode children
book collection -> book children
comic collection -> comic volume/issue children
audiobook series -> audiobook/book children
mixed folder -> multiple media candidates and unknowns
```

Rules:

```text
Parent object:
  preserves source evidence
  records split/reconstruction history
  retains unscoped leftovers
  should not be moved as final media if child objects own the actual media
  may become split_complete / reconstructed_complete / review_complete

Child object:
  owns only scoped files
  rebuilds metadata from scoped files
  inherits only safe identity hints from parent
  records parent provenance
  has its own destination preview
  has its own approval state
  has its own manifest/move result
```

A child object should never inherit counters/lists from the parent unless they are recomputed from the child’s actual scoped files.

---

## 8. Artwork, subtitles, and sidecar policy

Artwork, subtitles, and sidecars must follow the same scoping rule as media files.

### 8.1 Artwork

Artwork may be attached to a child object only if:

```text
it is inside the child object’s folder
it is explicitly tied to the child by metadata
its file name/path clearly matches the child object
user explicitly approves it
```

Parent-level artist/show/collection artwork must not be copied into every child object. It should stay parent-level or be classified separately as artist/show/collection artwork.

### 8.2 Subtitles

Subtitles may be attached only if:

```text
they are in the same folder as the movie/episode
file name matches the movie/episode base name
season/episode pattern matches the episode
user explicitly approves the match
```

A season-level subtitle file must not be attached to the wrong episode.

### 8.3 Sidecars

Sidecars may be attached only if:

```text
they are local to the object folder
naming strongly matches the object
structured sidecar metadata identifies the object
user explicitly approves it
```

Parent-level `.m3u`, `.txt`, `.log`, `.nfo`, `.json`, `.xml`, `.cue`, `.opf`, or report files must not be copied into every child object.

---

## 9. Move-readiness contract

Archive Assistant should not move a candidate until it can answer:

```text
What object is this?
Which files belong to it?
Which supporting files belong to it?
Where will it move?
Does the destination already exist?
What manifest will be written?
What source evidence will remain?
What is blocked or unresolved?
```

Minimum move-readiness checks:

```text
identity approved or safe enough
media class confirmed
destination preview available
file membership known
duplicate/destination conflict checked
artwork/subtitle/sidecar scope checked
unknown/unscoped files excluded or reviewed
no overwrite risk
no deletion action
manifest path available
move log path available
```

A move button is not enough. Archive Assistant needs a move-readiness panel before large production moves.

---

## 10. Duplicate and overwrite policy

Archive Assistant must avoid silent duplicates and overwrites.

Before moving, it should detect:

```text
exact destination folder already exists
same artist/album/year already exists
same book author/title/year already exists
same movie title/year already exists
same show/season/episode already exists
same file hash already exists
same basename and similar size already exists
same logical object with different format already exists
```

Default behavior:

```text
Exact destination exists -> block or require explicit review
Same logical object exists -> review required
Same hash exists -> duplicate warning/block
Different format of same object -> review/merge policy, not silent overwrite
```

---

## 11. Quarantine and unknown policy

Unknown and uncertain files must not be forced into final libraries.

Rules:

```text
unknown files stay review-required or quarantine
mixed-media folders are split into candidates where possible
unscoped leftovers remain with parent/source object
Cleaner may later handle reviewed cleanup targets
Archive Assistant does not delete production media
```

Quarantine is not trash. It is a review area.

---

## 12. Relationship with Intake Watcher

Intake Watcher’s job is to deliver stable source folders to Archive Assistant.

Archive Assistant must not depend on Intake Watcher for identity quality. Intake Watcher only answers:

```text
Is the upload complete?
Has the folder stopped changing?
Is it ready to scan?
```

Archive Assistant answers:

```text
What media is inside?
What objects should be created?
What needs review?
What can move?
```

AA should preserve enough source metadata to trace each object back to the Intake handoff.

---

## 13. Relationship with Cleaner

Cleaner is not part of Archive Assistant’s review/move logic.

Archive Assistant may produce cleanup evidence, but Cleaner owns cleanup/deletion decisions later.

Archive Assistant may write:

```text
leftover source folders
unscoped sidecars
empty source shells after successful move
reviewed cleanup candidates
move manifests
move logs
```

Cleaner may later evaluate those with age thresholds and safety rules.

Archive Assistant must not perform production deletion.

---

## 14. Relationship with downstream apps

Archive Assistant should produce clean final libraries and neutral event data.

Downstream apps are readers, not ingestion authorities.

```text
BM Radio:
  reads clean Music/Library output
  does not organize or delete media
  should not shape Archive Assistant around music only

Jellyfin:
  reads Movies/TV output
  needs stable movie/TV naming and subtitles/artwork scoped correctly

Audiobookshelf:
  reads Audiobooks output
  needs author/title/series/narrator/chapter structure

Calibre/Kavita or similar:
  reads Books/Comics output
  needs author/title/series/issue/volume structure
```

Archive Assistant should eventually write a neutral library event log such as:

```json
{"event_type":"media_moved","media_type":"music_album","destination":"...","batch_id":123,"timestamp":"..."}
```

Downstream apps can consume this later without Archive Assistant becoming tightly coupled to any one app.

---

## 15. Media-wide acceptance gate

Before old modals are removed or move execution is expanded, Archive Assistant must pass an all-media acceptance gate.

Minimum test matrix:

### Music

```text
single album
single album with artwork
MP3 album
FLAC album
music discography
multi-artist discography
split child album
album-local artwork only
album-local sidecars only
source folder not used as artist/title
```

### Audiobooks

```text
single audiobook
multi-part audiobook
multi-disc audiobook
multi-book/series audiobook
narrator preserved
series order preserved
artwork scoped to audiobook
old audiobook editor fallback still works
```

### Books and comics

```text
single EPUB
single PDF
book collection
comic CBZ/CBR
series/order preserved
cover scoped to item
metadata sidecar scoped to item
old book/comic editor fallback still works
```

### Movies

```text
single movie
movie collection/trilogy
subtitle scoped to movie
poster/fanart scoped to movie
destination preview correct
old movie editor fallback still works
```

### TV

```text
single season
multi-season show
special episode
anime OVA/OAD/special naming
subtitle scoped to episode
season/show artwork scoped correctly
old TV editor fallback still works
```

### Mixed and unknown

```text
mixed-media folder does not silently move as one object
unknown files require review
unscoped leftovers stay with parent/source object
quarantine remains review-only
```

---

## 16. Dead-code removal policy

Do not remove old modals or fallback editors until the workspace fully replaces a media type.

Retirement must be type-by-type:

```text
When music_album is fully workspace-native:
  hide pencil icon for music_album only
  keep old modal file until no imports/routes depend on it

When music_discography is fully workspace-native:
  hide pencil icon for music_discography only

When audiobook is fully workspace-native:
  hide audiobook modal only after fallback is no longer needed

Repeat for books, comics, movies, TV
```

A modal is dead only when:

```text
workspace covers the full review path
manual fallback is no longer needed
regression tests cover that media type
no route/import references the modal
user acceptance is complete
```

---

## 17. Future implementation order

Recommended order after this contract:

```text
AA-QA1 — All-Media Archive Assistant Acceptance Gate
AA-UX7 — Move Readiness Panel
AA-M5 — Destination Duplicate Guard
AA-M6 — Neutral Library Event Log
AA-UX8 — Music Workspace Completion and type-specific pencil retirement
AA-UX9 — Audiobook Workspace Panel
AA-UX10 — Book/Comic Workspace Panel
AA-UX11 — Movie/TV Workspace Panel
AA-CLEAN1 — Dead Modal Removal, type by type
```

Do not add local Llama/AI assistance until deterministic classification, scoping, review, move readiness, and duplicate protection are trustworthy.

---

## 18. Acceptance criteria for AA-SYSTEM1

AA-SYSTEM1 is accepted when future planning and implementation follow these rules:

```text
Archive Assistant is treated as media-wide, not music-only.
Every child/reconstructed object is file-scoped.
Parent metadata is evidence, not truth.
Artwork/subtitles/sidecars are scoped before attachment.
Unknown/unscoped files are not silently moved.
Move readiness checks are required before production moves.
Duplicate/overwrite risks are blocked or reviewed.
Old modals remain until replaced type-by-type.
Cleaner remains the only production deletion authority.
Downstream apps are readers of clean output, not drivers of AA design.
```

This document becomes the standing system contract for Archive Assistant work going forward.
