# Archive Assistant Core v1 Acceptance

Core v1 is accepted when mixed media can safely pass through:

```text
scan -> review/edit -> approve -> move -> log -> manifest/index
```

## Accepted media types

- Music album
- Music discography
- Movie
- Movie collection
- TV show
- Book
- Book collection
- Audiobook

## Required behavior

- Known media must not become quarantine only because metadata is imperfect.
- Metadata review blocks only on required fields.
- Books and audiobooks may use `Unknown Year`.
- Audiobook narrator is optional.
- Moved or approved confirmed items do not show active review warnings.
- Clean TV specials, OADs, and OVAs do not render as problem cards.
- Bulk approval handles different media types together.
- Each moved media folder receives a metadata manifest.
- Each top-level media metadata folder receives or updates a library index.
- Move logs remain with the moved media folder.

## Regression boundary

The default automated suite is bounded and does not scan, reset, or move real
media. Filesystem-heavy discography, audiobook, and manifest integration checks
remain targeted manual checks on Windows because their temporary-directory
cleanup can stall. A mixed-media UI smoke test is still required before a
release.

## Deferred after v1

- EPUB/PDF embedded metadata assist
- Audiobook chapter naming assist
- Calibre, Open Library, and Google Books lookups
- Audible or other audiobook metadata lookups
- Photo management, which is handled separately by Immich
- Lyrics and artwork enrichment
- Media playback UI
