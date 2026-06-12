# Usage Guide

## Common Flow

All media types follow the same pipeline:

```text
_INGEST/ → scan → review → edit → approve → move
```

1. **Drop** media folders or files into `data/_INGEST/`
2. **Scan** from the dashboard ("Scan ingest" button) or POST `/api/scan/music`
3. **Review** batches in the dashboard (All / Pending / Needs Metadata / Approved / Moved tabs)
4. **Edit** metadata if needed (pencil icon opens the correct editor for each media type)
5. **Confirm** review (check non-blocking warnings, mark as confirmed)
6. **Approve** (individual checkmark or bulk approve)
7. **Move** approved batches ("Move approved" button)

---

## Music Albums

**Place**: album folders directly into `data/_INGEST/`.

```text
data/_INGEST/
  Artist Name - Album Title (Year) [Format]/
    01 - Track Title.flac
    02 - Track Title.flac
    cover.jpg
```

**Detection**: folder name parsing + embedded tag extraction (mutagen). Supports FLAC, MP3, and common audio formats.

**Metadata fields**: artist, album, year, genre, format, disc number, track number, track title.

**Quality criteria**:

| Level | Required |
|---|---|
| good | artist + album + year |
| fair | artist + album (missing year) |
| weak | derived from folder name only |
| broken | no usable metadata |

**Special handling**:
- **Compilation albums**: detected by "VA", "Various Artists" patterns; prefix cleaned automatically
- **Track tag mismatches**: flagged per-track when embedded artist/album conflicts with batch metadata
- **Folder-level release tags**: `[FLAC]`, `[MP3]`, `[Mixtape]`, `[EP]`, `[Single]`, `[Vinyl]` — extracted and removed from album title

**Destinations**:
- `data/Music/Library/FLAC/Artist/Album (Year) [Format]/`
- `data/Music/Library/MP3/Artist/Album (Year) [Format]/`

---

## Music Discographies

**Place**: a parent folder containing multiple album subfolders.

```text
data/_INGEST/
  Artist Name - Discography/
    Album One (Year) [Format]/
    Album Two (Year) [Format]/
```

**Detection**: folder name must contain "discography" and a recognizable artist name. Child folders are parsed as individual albums.

**Review**: the discography editor shows all child albums in a summary table. For each album:
- Edit album title, year
- Set release type (studio, live, compilation, EP, single, remix, soundtrack, mixtape, bootleg, other)
- Exclude unwanted albums (moved to `discography-excluded` quarantine)
- Artist correction applies to all child albums

**Destinations**:
- `data/Music/Discographies/Artist Name/Album (Year) [Format]/`

---

## Movies

**Place**: a movie folder with a video file and optional artwork/subtitles.

```text
data/_INGEST/
  Movie Title (Year)/
    Movie Title.mkv
    Movie Title.en.srt
    poster.jpg
```

**Detection**: folder name parsing for title + year. Recognizes common video extensions (mkv, mp4, avi, m4v, etc.) and subtitle formats (srt, ass, ssa, vtt, sub).

**Metadata fields**: title, year, edition (e.g., "Director's Cut", "Extended"), format.

**Destinations**:
- `data/Movies/Library/Year - Title/`
- `data/Movies/Library/Year - Title [Edition]/`

---

## Movie Collections

**Place**: a folder containing multiple movies (box set, trilogy, etc.).

```text
data/_INGEST/
  Collection Name/
    Movie One (Year)/
    Movie Two (Year)/
    Movie Three (Year)/
```

**Detection**: multiple movie candidates found in a single ingest item. The scanner groups them as a batch with `review_type: "movie_collection"`.

**Review**: the movie collection editor shows each movie with fields for title, year, edition, format, and an include/exclude toggle. Set a collection title if desired.

**Destinations**: individual movie destinations within `data/Movies/Library/`, regardless of collection grouping.

---

## TV Shows

**Place**: a season folder or a folder with episode files.

```text
data/_INGEST/
  Show Name/
    Season 01/
      Show Name - S01E01 - Episode Title.mkv
      Show Name - S01E02 - Episode Title.mkv
    Season 02/
      ...
```

Or flat structure with episode-coded filenames.

**Detection**: TV detection looks for season/episode patterns (S01E01, 1x01, etc.) and common TV folder conventions. Supports multi-season batches.

**Metadata fields**: show title, year, season number, season title.

**Episode-level review**: the TV episode review panel allows per-episode:
- Title correction
- Season / episode number correction
- Include / exclude toggle
- Manual episode code assignment for unparseable filenames

**Destinations**:
- `data/TV/Library/Show Name/Season 01/`

---

## Books

**Place**: EPUB or PDF files (single book or loose files).

```text
data/_INGEST/
  Author - Title (Year).epub
```

Or for a single book folder:

```text
data/_INGEST/
  Book Title/
    book.epub
```

**Detection**: file extension (`.epub`, `.pdf`). Multiple book files in the same ingest root position are grouped as a book collection.

**Metadata fields**: author, title, year, format, series, series index.

**Destinations**: organized by author, format, and title:
- `data/Books/Author/Title (Year)/`

---

## Book Collections

**Place**: multiple book files together (series, box set, etc.).

```text
data/_INGEST/
  Author - Series Name/
    Book 1 - Title.epub
    Book 2 - Title.epub
```

**Detection**: multiple book files grouped by the scanner. Review mode shows each book with per-item metadata and include/exclude.

**Options**:
- Keep collection together (creates a nested folder structure under the collection label)
- Or keep books individually organized by author/title

**Destinations**:
- Individual: `data/Books/Author/Title (Year)/`
- Collection: `data/Books/Collection Name/Author - Title (Year)/`

---

## Audiobooks

**Place**: audiobook folder with audio files.

```text
data/_INGEST/
  Author - Title (Year)/
    CD1/
      01 - Chapter Title.mp3
      02 - Chapter Title.mp3
    CD2/
      ...
```

**Detection**: audio files with `_audiobook` marker or detected by context. Supports multi-disc folders and common audiobook naming patterns.

**Metadata fields**: author, title, year, narrator, series, series index, format.

**Destinations**:
- `data/Audiobooks/Library/Author/Title (Year)/`

---

## Bulk Operations

### Bulk approval

Select multiple batches in the dashboard and click "Approve selected". The bulk approve endpoint checks each batch individually:
- Skips batches that require metadata review
- Skips batches with blocking review items
- Reports per-batch skip reasons
- Returns counts of approved vs skipped

### Batch merging

When metadata is saved and another pending batch matches by canonical artist/album/format, the system automatically merges:
- Files from the smaller batch are reassigned to the largest
- The smaller batch becomes a `merged` audit row
- Archived duplicates are flagged with an alert (not merged)
- Merged batches are excluded from the main batch list

---

## Library Summary

The dashboard shows a library summary card with:

- **Moved albums / batches** — total completed moves
- **Moved tracks / files** — individual file moves
- **Failed moves** — any move errors
- **Approved waiting** — approved batches awaiting the move action
- **Needs metadata** — batches stuck in metadata review

Data is available via `GET /api/library/summary`.

---

## Move Logs

Every move action is recorded:
- Per-file: source path, destination path, status, error message, timestamps
- Available via `GET /api/batches/{id}/moves`
- Written to filesystem: `data/_REPORTS/move-logs/`

---

## Metadata Manifests

Each moved folder receives a JSON manifest file (`.archive-assistant-manifest.json`) containing:
- Final metadata used for the move
- Correction history (if metadata was edited)
- Confidence score
- File checksums
- Move completion timestamp

---

## Library Indexes

Each media-type root receives or updates a library index file (`.archive-assistant-index.json`):
- `Music/Library/.archive-assistant-index.json`
- `Movies/Library/.archive-assistant-index.json`
- `TV/Library/.archive-assistant-index.json`
- `Books/.archive-assistant-index.json`
- `Audiobooks/Library/.archive-assistant-index.json`

The index lists all moved items under that root with their paths and metadata summaries.

---

## Reset Test Data (Dev Mode)

Restores all moved or quarantined test media back to `_INGEST` and clears database records:

```bash
# Preview
python scripts/reset_music_test.py

# Apply
python scripts/reset_music_test.py --apply
```

From the dashboard (debug + dev tools enabled): click **Reset test data**. Requires confirmation.
