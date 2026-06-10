# UPDATE 042 — PART 2: FRONTEND TYPES, API CLIENT, AND REVIEW ROUTER
## Universal Media Review Framework — Frontend Plumbing

Apply Part 1 (backend) first and verify `python -m compileall app` is clean before starting here.

This part covers:
- New types in `types/archive.ts`
- New API method in `api/client.ts`
- New `MediaReviewRouter` component that centralizes editor selection
- Simplified `App.tsx` modal routing

No existing editor components are changed in this part. Those are in Part 3.

Run at the end:
```bash
cd frontend
npm run build
```

---

## CONTEXT: Current modal routing in App.tsx

Currently `App.tsx` has four inline conditionals for editors:
```tsx
{editingBatch?.detected_type === "music_album" && <MusicAlbumReviewEditor ... />}
{editingBatch?.detected_type === "music_discography" && <DiscographyEditor ... />}
{editingBatch?.detected_type === "video_movie" && <MovieMetadataEditor ... />}
{editingBatch?.detected_type === "video_tv_show" && <TvMetadataEditor ... />}
```

After this part, all four conditionals are replaced with one:
```tsx
{editingBatch && <MediaReviewRouter batch={editingBatch} ... />}
```

The individual editors remain completely unchanged for now.
The router is the only new thing.

---

## CHANGE 1 — `frontend/src/types/archive.ts`

### 1a. Add `review_mode` and `movie_items` to `BatchSummary`

Find this field in `BatchSummary`:
```ts
  review_type?: string | null;
```

After it, add:
```ts
  review_mode?: string | null;
  movie_items?: MovieCollectionItem[];
```

### 1b. Add `MovieCollectionItem` type

Add this type near the movie-related types (after `MovieMetadataUpdate`):

```ts
export type MovieCollectionItem = {
  item_kind: "movie";
  source_key: string;
  source_file: string;
  include: boolean;
  title?: string | null;
  year?: string | null;
  edition?: string | null;
  format?: string | null;
  destination_preview?: string | null;
};
```

### 1c. Add `MovieCollectionItemUpdate` and `MovieCollectionReviewUpdate` types

Add these after `MovieCollectionItem`:

```ts
export type MovieCollectionItemUpdate = {
  source_file: string;
  include: boolean;
  title: string;
  year: string;
  edition?: string | null;
  format?: string | null;
};

export type MovieCollectionReviewUpdate = {
  collection_title?: string | null;
  movies: MovieCollectionItemUpdate[];
  confirm_non_blocking_warnings?: boolean;
};
```

---

## CHANGE 2 — `frontend/src/api/client.ts`

### 2a. Add `MovieCollectionReviewUpdate` to imports

Find the import block that pulls types from `"../types/archive"`.
Add `MovieCollectionReviewUpdate` to the list.

### 2b. Add new API method

Find the `api` object. After the `updateTvEpisodeReview` entry, add:

```ts
  updateMovieCollectionReview: (id: number, update: MovieCollectionReviewUpdate) =>
    request<BatchSummary>(`/batches/${id}/movie-collection-review`, "PATCH", update),
```

---

## CHANGE 3 — `frontend/src/components/MediaReviewRouter.tsx` (NEW FILE)

Create this file. It does not exist.

This component receives the editing batch and all handler callbacks
and dispatches to the right editor. It replaces the four inline conditionals in App.tsx.
None of the individual editors are modified here — this is pure routing logic.

```tsx
import type {
  BatchSummary,
  BatchMetadataUpdate,
  DiscographyMetadataUpdate,
  MovieMetadataUpdate,
  MovieCollectionReviewUpdate,
  TvMetadataUpdate,
  TvEpisodeReviewUpdate,
} from "../types/archive";
import MusicAlbumReviewEditor from "./MetadataEditor";
import DiscographyEditor from "./DiscographyEditor";
import MovieMetadataEditor from "./MovieMetadataEditor";
import MovieCollectionEditor from "./MovieCollectionEditor";
import TvMetadataEditor from "./TvMetadataEditor";

type Props = {
  batch: BatchSummary;
  saving: boolean;
  // Music album
  onMetadataSave: (update: BatchMetadataUpdate) => Promise<void>;
  // Discography
  onDiscographySave: (update: DiscographyMetadataUpdate) => Promise<void>;
  // Single movie
  onMovieSave: (update: MovieMetadataUpdate) => Promise<void>;
  // Movie collection
  onMovieCollectionSave: (update: MovieCollectionReviewUpdate) => Promise<void>;
  // TV show-level
  onTvSave: (update: TvMetadataUpdate) => Promise<void>;
  // TV episode-level repair
  onTvEpisodeReviewSave: (update: TvEpisodeReviewUpdate) => Promise<void>;
  // Universal confirm (no-blocker path)
  onConfirm: () => Promise<void>;
  onClose: () => void;
};

/**
 * MediaReviewRouter
 *
 * Chooses the right editor based on detected_type and review_type.
 * Routing logic:
 *   - music_album                                     → MusicAlbumReviewEditor
 *   - music_discography                               → DiscographyEditor
 *   - video_movie + review_type=movie_collection      → MovieCollectionEditor
 *   - video_movie + review_type=movie (or unset)      → MovieMetadataEditor
 *   - video_movie + multiple_movie_candidates blocker → MovieCollectionEditor
 *   - video_tv_show                                   → TvMetadataEditor
 *   - anything else                                   → null (no editor yet)
 */
export default function MediaReviewRouter({
  batch,
  saving,
  onMetadataSave,
  onDiscographySave,
  onMovieSave,
  onMovieCollectionSave,
  onTvSave,
  onTvEpisodeReviewSave,
  onConfirm,
  onClose,
}: Props) {
  const { detected_type, review_type, blocking_review_items } = batch;

  // Determine if this is a movie collection case
  const isMovieCollection =
    detected_type === "video_movie" &&
    (
      review_type === "movie_collection" ||
      (blocking_review_items ?? []).some((item) => item.type === "multiple_movie_candidates")
    );

  if (detected_type === "music_album") {
    return (
      <MusicAlbumReviewEditor
        batch={batch}
        saving={saving}
        onSave={onMetadataSave}
        onConfirm={onConfirm}
        onClose={onClose}
      />
    );
  }

  if (detected_type === "music_discography") {
    return (
      <DiscographyEditor
        batch={batch}
        saving={saving}
        onSave={onDiscographySave}
        onConfirm={onConfirm}
        onClose={onClose}
      />
    );
  }

  if (detected_type === "video_movie" && isMovieCollection) {
    return (
      <MovieCollectionEditor
        batch={batch}
        saving={saving}
        onSave={onMovieCollectionSave}
        onConfirm={onConfirm}
        onClose={onClose}
      />
    );
  }

  if (detected_type === "video_movie") {
    return (
      <MovieMetadataEditor
        batch={batch}
        saving={saving}
        onSave={onMovieSave}
        onConfirm={onConfirm}
        onClose={onClose}
      />
    );
  }

  if (detected_type === "video_tv_show") {
    return (
      <TvMetadataEditor
        batch={batch}
        saving={saving}
        onSave={onTvSave}
        onSaveEpisodeReview={onTvEpisodeReviewSave}
        onConfirm={onConfirm}
        onClose={onClose}
      />
    );
  }

  // No editor for this type yet (quarantine, books, etc.)
  return null;
}
```

---

## CHANGE 4 — `frontend/src/App.tsx`

### 4a. Update imports

Add to the existing import block from `"./types/archive"`:
```ts
  MovieCollectionReviewUpdate,
```

Add a new component import below the existing editor imports:
```ts
import MediaReviewRouter from "./components/MediaReviewRouter";
```

### 4b. Add `handleMovieCollectionSave` handler

Find `handleMovieSave`. After its closing `};`, add:

```ts
  const handleMovieCollectionSave = async (update: MovieCollectionReviewUpdate) => {
    if (!editingBatch) return;
    setSavingMetadata(true);
    try {
      const result = await api.updateMovieCollectionReview(editingBatch.id, update);
      showToast(result.action_message ?? "Movie collection review saved");
      setEditingBatch(null);
      await loadBatches();
    } catch (saveError: unknown) {
      showToast(
        saveError instanceof Error ? saveError.message : "Movie collection review save failed",
        "error",
      );
    } finally {
      setSavingMetadata(false);
    }
  };
```

### 4c. Replace the four editor conditionals with MediaReviewRouter

Find this block in the JSX return:

```tsx
      {editingBatch?.detected_type === "music_album" && (
        <MusicAlbumReviewEditor
          batch={editingBatch}
          saving={savingMetadata}
          onSave={handleMetadataSave}
          onConfirm={handleReviewConfirm}
          onClose={() => {
            if (!savingMetadata) setEditingBatch(null);
          }}
        />
      )}
      {editingBatch?.detected_type === "music_discography" && (
        <DiscographyEditor
          batch={editingBatch}
          saving={savingMetadata}
          onSave={handleDiscographySave}
          onConfirm={handleReviewConfirm}
          onClose={() => {
            if (!savingMetadata) setEditingBatch(null);
          }}
        />
      )}
      {editingBatch?.detected_type === "video_movie" && (
        <MovieMetadataEditor
          batch={editingBatch}
          saving={savingMetadata}
          onSave={handleMovieSave}
          onConfirm={handleReviewConfirm}
          onClose={() => {
            if (!savingMetadata) setEditingBatch(null);
          }}
        />
      )}
      {editingBatch?.detected_type === "video_tv_show" && (
        <TvMetadataEditor
          batch={editingBatch}
          saving={savingMetadata}
          onSave={handleTvSave}
          onSaveEpisodeReview={handleTvEpisodeReviewSave}
          onConfirm={handleReviewConfirm}
          onClose={() => {
            if (!savingMetadata) setEditingBatch(null);
          }}
        />
      )}
```

Replace the entire block with:

```tsx
      {editingBatch && (
        <MediaReviewRouter
          batch={editingBatch}
          saving={savingMetadata}
          onMetadataSave={handleMetadataSave}
          onDiscographySave={handleDiscographySave}
          onMovieSave={handleMovieSave}
          onMovieCollectionSave={handleMovieCollectionSave}
          onTvSave={handleTvSave}
          onTvEpisodeReviewSave={handleTvEpisodeReviewSave}
          onConfirm={handleReviewConfirm}
          onClose={() => {
            if (!savingMetadata) setEditingBatch(null);
          }}
        />
      )}
```

### 4d. Remove now-unused individual editor imports from App.tsx

The individual editors are now imported inside `MediaReviewRouter`, not `App.tsx`.
Remove these four import lines from `App.tsx`:

```ts
import MusicAlbumReviewEditor from "./components/MetadataEditor";
import DiscographyEditor from "./components/DiscographyEditor";
import MovieMetadataEditor from "./components/MovieMetadataEditor";
import TvMetadataEditor from "./components/TvMetadataEditor";
```

Also remove the now-unused type imports from `"./types/archive"` in App.tsx:
- `BatchMetadataUpdate` — keep if used elsewhere in App.tsx (check before removing)
- `DiscographyMetadataUpdate` — keep if used elsewhere
- `MovieMetadataUpdate` — keep if used elsewhere
- `TvMetadataUpdate` — keep if used elsewhere
- `TvEpisodeReviewUpdate` — keep if used elsewhere

**Important:** Only remove an import if it has no other usage in App.tsx after the refactor.
The handler functions (`handleMetadataSave`, `handleDiscographySave`, etc.) still use these
types in their function signatures — check each one before removing.

---

## VALIDATION CHECKLIST

- [ ] `types/archive.ts` — `BatchSummary` has `review_mode` and `movie_items`
- [ ] `types/archive.ts` — `MovieCollectionItem`, `MovieCollectionItemUpdate`, `MovieCollectionReviewUpdate` added
- [ ] `api/client.ts` — `updateMovieCollectionReview` method added
- [ ] `MediaReviewRouter.tsx` created with correct routing logic for all 4 detected types
- [ ] `MovieCollectionEditor` import in `MediaReviewRouter.tsx` will resolve after Part 3 creates the file
- [ ] `App.tsx` — `handleMovieCollectionSave` handler added
- [ ] `App.tsx` — four editor conditionals replaced with single `<MediaReviewRouter>`
- [ ] `App.tsx` — individual editor imports removed (or kept only if used elsewhere)
- [ ] `npm run build` — expected to fail only on missing `MovieCollectionEditor` until Part 3 is applied

## DO NOT

- Do not modify `MetadataEditor.tsx`, `DiscographyEditor.tsx`, `MovieMetadataEditor.tsx`, or `TvMetadataEditor.tsx` in this part
- Do not change handler function names in App.tsx — only add the new one
- Do not change `BatchRow.tsx` or `BatchTable.tsx`
- Do not add any new CSS in this part
