import type {
  BatchSummary,
  BatchMetadataUpdate,
  BookCollectionReviewUpdate,
  BookMetadataUpdate,
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
import BookMetadataEditor from "./BookMetadataEditor";
import BookCollectionEditor from "./BookCollectionEditor";

type Props = {
  batch: BatchSummary;
  saving: boolean;
  onMetadataSave: (update: BatchMetadataUpdate) => Promise<void>;
  onDiscographySave: (update: DiscographyMetadataUpdate) => Promise<void>;
  onMovieSave: (update: MovieMetadataUpdate) => Promise<void>;
  onMovieCollectionSave: (update: MovieCollectionReviewUpdate) => Promise<void>;
  onBookSave: (update: BookMetadataUpdate) => Promise<void>;
  onBookCollectionSave: (update: BookCollectionReviewUpdate) => Promise<void>;
  onTvSave: (update: TvMetadataUpdate) => Promise<void>;
  onTvEpisodeReviewSave: (update: TvEpisodeReviewUpdate) => Promise<void>;
  onConfirm: () => Promise<void>;
  onClose: () => void;
};

export default function MediaReviewRouter({
  batch,
  saving,
  onMetadataSave,
  onDiscographySave,
  onMovieSave,
  onMovieCollectionSave,
  onBookSave,
  onBookCollectionSave,
  onTvSave,
  onTvEpisodeReviewSave,
  onConfirm,
  onClose,
}: Props) {
  const { detected_type, review_type, blocking_review_items } = batch;

  const isMovieCollection =
    detected_type === "video_movie" &&
    (
      review_type === "movie_collection" ||
      (blocking_review_items ?? []).some((item) => item.type === "multiple_movie_candidates")
    );
  const isBookCollection =
    detected_type === "book" &&
    (review_type === "book_collection" || (batch.book_items ?? []).length > 0);

  if (detected_type === "music_album") {
    return (
      <MusicAlbumReviewEditor
        batch={batch}
        saving={saving}
        onSave={onMetadataSave}
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

  if (detected_type === "book" && isBookCollection) {
    return (
      <BookCollectionEditor
        batch={batch}
        saving={saving}
        onSave={onBookCollectionSave}
        onConfirm={onConfirm}
        onClose={onClose}
      />
    );
  }

  if (detected_type === "book") {
    return (
      <BookMetadataEditor
        batch={batch}
        saving={saving}
        onSave={onBookSave}
        onConfirm={onConfirm}
        onClose={onClose}
      />
    );
  }

  return null;
}
