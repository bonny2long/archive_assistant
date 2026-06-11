# Archive Assistant Roadmap

## Milestone 1: Local music scanner
- Scan `_INGEST/music`
- Extract metadata
- Create ingest batches
- Create JSON reports

## Milestone 2: Approved mover
- Approve/reject batches
- Move approved files only
- Write move logs
- Update archive item records

## Milestone 3: Local dashboard
- Inbox
- Pending Review
- Move History
- Library Search

## Milestone 4: PostgreSQL
- Replace SQLite with PostgreSQL for NAS deployment

## Milestone 5: AI metadata recovery
- Use AI only for ambiguous metadata
- Human approval before writes

## Milestone 6: Add media types
- Movies
- TV
- Books
- Audiobooks
- Internet Archive imports

## Future metadata assist phase
- Books: read EPUB/PDF metadata using EbookLib / pypdf / optional Calibre CLI.
- Audiobooks: optional read-only metadata/chapter helpers using mutagen and/or external lookup.
- All suggestions remain review-first. No automatic rename or move without user approval.
