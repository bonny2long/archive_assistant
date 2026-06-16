export type IngestFile = {
  id: number;
  file_name: string;
  extension: string;
  size_bytes: number;
  detected_role: string;
  metadata_json?: Record<string, unknown> | null;
};

export type IngestBatch = {
  id: number;
  source_kind: string;
  source_path: string;
  detected_type: string;
  status: string;
  confidence: number;
  suggested_destination?: string | null;
  suggested_metadata?: SuggestedMetadata | null;
  metadata_json?: Record<string, unknown> | null;
  metadata_confirmed: boolean;
  created_at: string;
  approved_at?: string | null;
  files: IngestFile[];
};

export type TvWarningFile = {
  source_file: string;
  relative_source?: string | null;
  raw_name?: string | null;
};

export type TvWarningDetails = {
  unparsed_video_files: TvWarningFile[];
  generic_title_files: TvWarningFile[];
};

export type UnresolvedVideoFile = {
  source_file: string;
  relative_source?: string | null;
  raw_name?: string | null;
  show_title?: string | null;
};

export type BatchSummary = {
  id: number;
  detected_type: string;
  status: string;
  artist?: string | null;
  album?: string | null;
  year?: string | null;
  primary_genre?: string | null;
  format?: string | null;
  track_count: number;
  artwork_count: number;
  ignored_sidecar_count: number;
  subtitle_count: number;
  video_file_count: number;
  video_files?: string[];
  title?: string | null;
  edition?: string | null;
  resolution?: string | null;
  source?: string | null;
  original_release_name?: string | null;
  primary_video_file?: string | null;
  artwork_files: string[];
  subtitle_files: string[];
  ignored_sidecar_files: string[];
  release_tags_removed: string[];
  show_title?: string | null;
  season_count: number;
  episode_count: number;
  seasons: TvSeason[];
  special_episode_count?: number;
  special_episodes?: TvEpisode[];
  unresolved_video_count?: number;
  unresolved_video_files?: UnresolvedVideoFile[];
  tv_warning_details?: TvWarningDetails | null;
  ignored_corrupt_video_count: number;
  ignored_corrupt_video_files: string[];
  name?: string | null;
  reason?: string | null;
  file_count: number;
  folder_count: number;
  size_bytes: number;
  recommended_action?: string | null;
  release_count: number;
  album_count: number;
  albums: DiscographyAlbum[];
  disc_count: number;
  confidence: number;
  metadata_quality: string;
  metadata_warnings: string[];
  blocking_review_items: ReviewItem[];
  non_blocking_review_items: ReviewItem[];
  review_confirmed: boolean;
  review_type?: string | null;
  review_mode?: string | null;
  movie_items?: MovieCollectionItem[];
  collection_title?: string | null;
  keep_collection_together?: boolean | null;
  collection_destination_root?: string | null;
  author?: string | null;
  book_file_count?: number;
  book_files?: string[];
  primary_book_file?: string | null;
  book_items?: BookCollectionItem[];
  collection_summary?: BookCollectionSummary;
  narrator?: string | null;
  series?: string | null;
  series_index?: string | null;
  audiobook_file_count?: number;
  audio_files?: string[];
  primary_audio_file?: string | null;
  chapter_count?: number;
  metadata_candidates?: Record<string, MetadataCandidate[]>;
  chapter_candidates?: ChapterCandidate[];
  artwork_candidates?: MetadataCandidate[];
  generic_audio_tag_count?: number;
  detected_disc_count?: number;
  candidate_warning_count?: number;
  audiobook_collection_type?: string | null;
  contained_books?: AudiobookContainedBook[];
  accepted_unknown_author?: boolean;
  accepted_unknown_year?: boolean;
  accepted_unknown_narrator?: boolean;
  accepted_unknown_album_artist?: boolean;
  accepted_unknown_album_title?: boolean;
  accepted_unknown_discography_artist?: boolean;
  accepted_unknown_title?: boolean;
  lookup_later?: boolean;
  move_manifest?: MoveManifestPointer | null;
  metadata_assist_version?: string | null;
  suggested_destination?: string | null;
  suggested_metadata?: SuggestedMetadata | null;
  metadata_confirmed: boolean;
  action_message?: string | null;
  media_category?: string | null;
  media_label?: string | null;
  primary_name?: string | null;
  secondary_name?: string | null;
  item_label?: string | null;
  item_count: number;
  edit_kind?: string | null;
  created_at: string;
};

export type MetadataCandidate = {
  field: string;
  value: string;
  source: string;
  source_label: string;
  confidence: number;
  confidence_label: "high" | "medium" | "low";
  applied: boolean;
  ignored: boolean;
  notes: string[];
};

export type ChapterCandidate = {
  source_file: string;
  track_number?: string | number | null;
  disc_number?: string | number | null;
  current_name: string;
  suggested_title: string;
  source: string;
  source_label?: string;
  confidence: number;
  confidence_label: "high" | "medium" | "low";
  ignored?: boolean;
  generic?: boolean;
  notes?: string[];
};

export type SuggestedMetadata = {
  metadata_assist_version?: string | null;
  artist?: string | null;
  album?: string | null;
  year?: string | null;
  genre?: string | null;
  title?: string | null;
  author?: string | null;
  narrator?: string | null;
  series?: string | null;
  series_index?: string | null;
  edition?: string | null;
  format?: string | null;
  show_title?: string | null;
  season_number?: number | null;
  season_title?: string | null;
  note?: string | null;
  accepted_unknown_author?: boolean;
  accepted_unknown_year?: boolean;
  accepted_unknown_narrator?: boolean;
  accepted_unknown_album_artist?: boolean;
  accepted_unknown_album_title?: boolean;
  accepted_unknown_discography_artist?: boolean;
  accepted_unknown_title?: boolean;
  lookup_later?: boolean;
  sources?: Partial<Record<
    "artist" | "album" | "year" | "genre" | "title" | "author" | "narrator" | "series" | "series_index" | "edition" | "format" | "show_title" | "season_number" | "season_title",
    string
  >>;
  compilation?: boolean;
};

export type BatchMetadataUpdate = {
  artist: string;
  album: string;
  year: string | null;
  primary_genre?: string | null;
  format?: string | null;
  note?: string | null;
  accepted_unknown_album_artist?: boolean;
  accepted_unknown_album_title?: boolean;
  accepted_unknown_year?: boolean;
  lookup_later?: boolean;
};

export type ReviewItem = {
  type: string;
  message: string;
  file_name?: string | null;
  source_folder?: string | null;
  episode_code?: string | null;
};

export type ReviewConfirmationUpdate = {
  confirmed: boolean;
  accept_non_blocking_warnings: boolean;
  note?: string | null;
};

export type DiscographyReleaseType =
  | "album"
  | "single"
  | "ep"
  | "compilation"
  | "live"
  | "other"
  | "exclude";

export type DiscographyAlbum = {
  source_folder: string;
  artist?: string | null;
  album: string;
  year?: string | null;
  format?: string;
  track_count: number;
  disc_count?: number;
  artwork_count?: number;
  artwork_files?: string[];
  status?: string;
  warnings?: string[];
  release_type?: DiscographyReleaseType;
  include?: boolean;
  metadata_candidates?: Record<string, MetadataCandidate[]>;
  track_candidates?: MetadataCandidate[];
  accepted_unknown_album_artist?: boolean;
  accepted_unknown_album_title?: boolean;
  accepted_unknown_year?: boolean;
  lookup_later?: boolean;
};

export type DiscographyAlbumUpdate = {
  source_folder: string;
  album: string;
  year: string | null;
  release_type: DiscographyReleaseType;
  include: boolean;
  accepted_unknown_album_artist: boolean;
  accepted_unknown_album_title: boolean;
  accepted_unknown_year: boolean;
  lookup_later: boolean;
};

export type DiscographyMetadataUpdate = {
  artist: string;
  albums?: DiscographyAlbumUpdate[];
  accepted_unknown_discography_artist?: boolean;
  lookup_later?: boolean;
};

export type MovieMetadataUpdate = {
  title: string;
  year: string | null;
  edition?: string | null;
  format?: string | null;
  accepted_unknown_title?: boolean;
  accepted_unknown_year?: boolean;
  lookup_later?: boolean;
};

export type MovieCollectionItem = {
  item_kind: "movie";
  source_key: string;
  source_file: string;
  include: boolean;
  title?: string | null;
  year?: string | null;
  edition?: string | null;
  format?: string | null;
  resolution?: string | null;
  source?: string | null;
  destination_preview?: string | null;
  metadata_candidates?: Record<string, MetadataCandidate[]>;
  release_cleanup?: Record<string, unknown>;
  accepted_unknown_title?: boolean;
  accepted_unknown_year?: boolean;
  lookup_later?: boolean;
};

export type MovieCollectionItemUpdate = {
  source_file: string;
  include: boolean;
  title: string;
  year: string | null;
  edition?: string | null;
  format?: string | null;
  metadata_candidates?: Record<string, MetadataCandidate[]>;
  accepted_unknown_title: boolean;
  accepted_unknown_year: boolean;
  lookup_later: boolean;
};

export type MovieCollectionReviewUpdate = {
  collection_title?: string | null;
  movies: MovieCollectionItemUpdate[];
  confirm_non_blocking_warnings?: boolean;
};

export type BookMetadataUpdate = {
  title: string;
  author: string;
  year?: string | null;
  format?: string | null;
  note?: string | null;
};

export type BookCollectionItem = {
  item_kind: "book";
  source_key: string;
  source_file: string;
  include: boolean;
  title?: string | null;
  metadata_title?: string | null;
  display_title?: string | null;
  destination_title?: string | null;
  author?: string | null;
  year?: string | null;
  format?: string | null;
  series?: string | null;
  series_index?: string | null;
  destination_preview?: string | null;
  metadata_candidates?: Record<string, MetadataCandidate[]>;
  candidate_notes?: string[];
  candidate_runtime?: Record<string, unknown>;
  matched_artwork?: MatchedArtwork | null;
  alternate_formats?: AlternateBookFormat[];
  accepted_unknown_author?: boolean;
  accepted_unknown_year?: boolean;
  lookup_later?: boolean;
};

export type BookCollectionItemUpdate = {
  source_file: string;
  include: boolean;
  title: string;
  author: string;
  year?: string | null;
  format?: string | null;
  series?: string | null;
  series_index?: string | null;
  metadata_candidates?: Record<string, MetadataCandidate[]>;
  candidate_notes?: string[];
  candidate_runtime?: Record<string, unknown>;
  matched_artwork?: MatchedArtwork | null;
  alternate_formats?: AlternateBookFormat[];
  accepted_unknown_author?: boolean;
  accepted_unknown_year?: boolean;
  lookup_later?: boolean;
};

export type MatchedArtwork = {
  file: string;
  match_method: "normalized_basename";
  confidence: number;
};

export type AlternateBookFormat = {
  format: string;
  file: string;
  role: "alternate_format";
};

export type BookCollectionSummary = {
  total_files_seen: number;
  primary_book_count: number;
  included_book_count: number;
  epub_count: number;
  pdf_count: number;
  mobi_duplicate_count: number;
  opf_sidecar_count: number;
  artwork_count: number;
  matched_artwork_count: number;
  unmatched_artwork_count: number;
  ignored_sidecar_count: number;
  duplicate_format_groups: number;
  needs_repair_count: number;
};

export type BookCollectionReviewUpdate = {
  collection_title?: string | null;
  keep_collection_together?: boolean;
  books: BookCollectionItemUpdate[];
  confirm_non_blocking_warnings?: boolean;
};

export type AudiobookMetadataUpdate = {
  author: string;
  title: string;
  year?: string | null;
  narrator?: string | null;
  series?: string | null;
  series_index?: string | null;
  format?: string | null;
  note?: string | null;
  accepted_unknown_author?: boolean;
  accepted_unknown_year?: boolean;
  accepted_unknown_narrator?: boolean;
  lookup_later?: boolean;
};

export type AudiobookContainedBook = {
  series_index: string;
  title: string;
};

export type TvMetadataUpdate = {
  show_title: string;
  season_number?: number | null;
  year?: string | null;
  season_title?: string | null;
};

export type TvEpisode = {
  show_title?: string | null;
  season_number?: number | null;
  episode_number?: number | null;
  episode_code?: string | null;
  episode_title?: string | null;
  subtitle_count?: number;
  source_file: string;
  relative_source?: string | null;
  // Review patch fields (set by user during episode review)
  include?: boolean;
  is_special?: boolean;
  special_label?: string | null;
  destination_group?: "season" | "specials" | "oad" | "ova" | "extras" | null;
  preserve_source_filename?: boolean;
  reviewed?: boolean;
};

export type TvSeason = {
  season_number: number;
  season_title?: string | null;
  episode_count: number;
  episodes: TvEpisode[];
};

export type PaginatedResponse<T> = {
  items: T[];
  page: number;
  page_size: number;
  total: number;
  total_pages: number;
};

export type MoveResult = {
  moved: number;
  errors: string[];
  files_moved: number;
  failed_moves: number;
  manifests: Array<MoveManifestPointer & { batch_id: number }>;
};

export type MoveManifestPointer = {
  json_path: string;
  markdown_path?: string | null;
  created_at: string;
  manifest_version: string;
  archive_assistant_version?: string;
  files_moved: number;
  artwork_moved: number;
  failed_moves: number;
};

export type ScanMusicResponse = {
  created: number;
  skipped_duplicates: number;
  batches: IngestBatch[];
  music_albums_found: number;
  discographies_found: number;
  unknown_items: number;
  unsupported_files: number;
  ignored_system_files: number;
  artwork_files_found: number;
  movie_batches_found: number;
  tv_shows_found: number;
  tv_episodes_found: number;
  subtitle_files_found: number;
  book_batches_found: number;
  book_files_found: number;
  audiobook_batches_found: number;
  audiobook_files_found: number;
};

export type DevResetResponse = {
  status: string;
  restored_tracks: number;
  restored_files: number;
  recovered_media_files?: number;
  untracked_library_media_files?: number;
  removed_reports: number;
  removed_move_logs: number;
  removed_library_metadata: number;
  removed_empty_dirs: number;
  cleared_batches: number;
  message: string;
};

export type LibrarySummary = {
  moved_albums: number;
  moved_tracks: number;
  moved_batches: number;
  moved_files: number;
  failed_moves: number;
  approved_waiting: number;
  needs_metadata: number;
};

export type HealthResponse = {
  status: string;
  service: string;
  debug: boolean;
  dev_tools_enabled: boolean;
};

export type SystemTimeResponse = {
  server_utc: string;
  server_timezone: string;
  server_local: string;
  source: "server_clock";
};

export type MoveAction = {
  id: number;
  source_path: string;
  destination_path: string;
  file_name?: string | null;
  status: string;
  error_message?: string | null;
  created_at: string;
  completed_at?: string | null;
};

export type BatchMoveSummary = {
  batch_id: number;
  total: number;
  completed: number;
  failed: number;
  moves: MoveAction[];
  manifest?: MoveManifestPointer | null;
};

export type BatchReviewTrack = {
  position: number;
  disc: number;
  track?: number | null;
  title: string;
  source_filename: string;
  destination_filename: string;
  artist?: string | null;
  album?: string | null;
  warnings: string[];
};

export type BatchReview = {
  batch_id: number;
  artist?: string | null;
  album?: string | null;
  year?: string | null;
  genre?: string | null;
  format: string;
  status: string;
  confidence: number;
  track_count: number;
  disc_count: number;
  warnings: string[];
  source_path: string;
  destination_preview?: string | null;
  tracks: BatchReviewTrack[];
};

export type BatchActionResult = {
  batch_id: number;
  status: string;
  message: string;
  metadata_quality?: string | null;
  metadata_warnings?: string[] | null;
};

export type BulkApproveError = {
  batch_id: number;
  reason: string;
};

export type BulkApproveResult = {
  approved: number[];
  skipped: number[];
  errors: BulkApproveError[];
};

export type TvEpisodeReviewPatch = {
  source_file: string;
  relative_source?: string | null;
  include: boolean;
  season_number?: number | null;
  episode_number?: number | null;
  is_special?: boolean;
  special_label?: string | null;
  destination_group?: "season" | "specials" | "oad" | "ova" | "extras" | null;
  episode_title?: string | null;
  preserve_source_filename?: boolean;
};

export type TvEpisodeReviewUpdate = {
  show_title?: string | null;
  year?: string | null;
  patches: TvEpisodeReviewPatch[];
  confirm_non_blocking_warnings?: boolean;
};

export type TabKey = "all" | "pending" | "needs_metadata" | "quarantine" | "approved" | "moved";
