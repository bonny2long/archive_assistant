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
  title?: string | null;
  edition?: string | null;
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

export type SuggestedMetadata = {
  artist?: string | null;
  album?: string | null;
  year?: string | null;
  genre?: string | null;
  title?: string | null;
  edition?: string | null;
  format?: string | null;
  show_title?: string | null;
  season_number?: number | null;
  season_title?: string | null;
  sources?: Partial<Record<
    "artist" | "album" | "year" | "genre" | "title" | "edition" | "format" | "show_title" | "season_number" | "season_title",
    string
  >>;
  compilation?: boolean;
};

export type BatchMetadataUpdate = {
  artist: string;
  album: string;
  year: string;
  primary_genre?: string | null;
  format?: string | null;
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
  artwork_count?: number;
  artwork_files?: string[];
  status?: string;
  warnings?: string[];
  release_type?: DiscographyReleaseType;
  include?: boolean;
};

export type DiscographyAlbumUpdate = {
  source_folder: string;
  album: string;
  year: string | null;
  release_type: DiscographyReleaseType;
  include: boolean;
};

export type DiscographyMetadataUpdate = {
  artist: string;
  albums?: DiscographyAlbumUpdate[];
};

export type MovieMetadataUpdate = {
  title: string;
  year: string | null;
  edition?: string | null;
  format?: string | null;
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
  source_file: string;
  relative_source?: string;
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
};

export type DevResetResponse = {
  status: string;
  restored_tracks: number;
  restored_files: number;
  removed_reports: number;
  removed_move_logs: number;
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

export type TabKey = "all" | "pending" | "needs_metadata" | "quarantine" | "approved" | "moved";
