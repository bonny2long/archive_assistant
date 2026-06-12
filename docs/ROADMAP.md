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

## v2 Metadata Assist — Next

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
