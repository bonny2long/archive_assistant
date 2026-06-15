# Archive Assistant Roadmap

## v1 Core — Complete

Tagged: `archive-assistant-v1-core`

Safe deterministic organizer: scan, classify, guided review, edit, approve, move, manifest, index, logs, and regression runner.

**Supported workflows:**
- Music albums
- Music discographies
- Single movies
- Movie collections / trilogies
- TV shows (seasons, episodes, specials)
- Books / book collections
- Audiobooks / multi-disc audiobook folders
- Bulk approval with skip reporting
- Metadata manifests and library indexes
- Mixed-media scan / review / approve / move
- Core v1 regression suite

**Core v1 rules:**
- No deletion
- No overwrite
- No embedded tag mutation
- No move without approval
- Recognized media with weak metadata → review, not quarantine
- True unknown / unsupported → quarantine review
- Moved media gets metadata manifests and move logs

---

## v2 Metadata Assist — In Progress

### v2.064 Checkpoint

**v2.064 is functionally passing for book/audiobook metadata assist and move
manifests. Full v2 remains open until music, movie, and TV metadata assist reach
parity.**

Passing at this checkpoint:

- Book and book-collection metadata candidates and guided repair
- Audiobook metadata candidates, artwork matching, and multi-book preview
- Explicit accepted-unknown and lookup-later review decisions
- JSON and Markdown move manifests with persisted audit pointers

Still open for full v2:

- Movie metadata-assist parity
- TV metadata-assist parity
- Final mixed-media v2 regression and release lock

### v2.065 Music Metadata Assist

Passing at this checkpoint:

- Local music candidates from folders, parent folders, filenames, embedded tags, and artwork
- DJ/mixtape guards that prevent weak VA tags from replacing stronger folder context
- Album and discography suggestion chips and guided repair controls
- Explicit accepted-unknown and lookup-later decisions for music
- Album track detail and artwork evidence in JSON/Markdown move manifests
- Central discography move manifests under `Music/Metadata/move_manifests`

Scope stays focused on metadata only:

- **EPUB/PDF metadata reading** — extract title, author, series from book files using EbookLib / pypdf
- **Audiobook chapter/title metadata** — optional chapter naming helpers using mutagen
- **Suggestion chips in editors** — metadata candidates from file parsing, embedded tags, and optional online lookup
- **Artwork suggestion support** — find and suggest cover art candidates
- **Online lookup** — optional Open Library, Google Books, Audible lookups (opt-in, never automatic)
- No silent edits
- No deletion
- No embedded tag writing (unless explicitly approved later)
- Manual approval remains authoritative

---

## v3 Production Ingest Cleanup

Production hardening after metadata assist is stable:

- Clean empty `_INGEST` folders after successful moves
- Leave folders with leftover files for review
- Never delete files that were not moved
- Never delete quarantined / rejected files
- Development mode keeps leftovers
- Production mode can clean approved empty source folders
- Cleanup actions must be logged

---

## Later Phases

- **PostgreSQL analytics** — richer search, library intelligence, historical stats
- **Dashboard intelligence** — library trends, missing metadata reports, duplicate analysis
- **Local radio** — streaming from organized music library
- **External metadata engines** — plugin system for custom metadata sources
- **Off-site backup** — parents-house replication, remote sync
