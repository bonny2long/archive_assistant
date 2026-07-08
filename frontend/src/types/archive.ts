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
  music_review_summary?: MusicReviewSummary | null;
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

export type FieldEnvelope = {
  value?: unknown;
  source?: string | null;
  confidence?: number | null;
  reason?: string | null;
  approval_state?: string | null;
  approved?: boolean | null;
  approved_at?: string | null;
  approved_by?: string | null;
  updated_at?: string | null;
};

export type MusicTrackProfileSummary = {
  file_name?: string | null;
  track_profile?: Record<string, FieldEnvelope> | null;
  inheritance_summary?: Record<string, unknown> | null;
};

export type MusicReviewSummary = {
  core_metadata_status?: string | null;
  approved_core_fields?: string[];
  inherited_to_track_count?: number;
  inherited_fields?: string[];
  missing_optional_fields?: string[];
  blocking_issue_count?: number;
  needs_review_issue_count?: number;
  info_issue_count?: number;
  setup_warnings?: string[];
  profile_consistency?: string | null;
  artist_profile?: Record<string, FieldEnvelope>;
  release_profile?: Record<string, FieldEnvelope>;
  track_profiles?: MusicTrackProfileSummary[];
};

export type MetadataQualityDecisionName =
  | "approved_ready"
  | "review_recommended"
  | "review_required"
  | "blocked";

export type MetadataQualityDecision = {
  media_file_id: number;
  ingest_file_id?: number | null;
  file_name: string;
  relative_path?: string | null;
  decision: MetadataQualityDecisionName;
  severity: string;
  score?: number | null;
  reasons: string[];
  blocking_flags: string[];
  warning_flags: string[];
  profile?: Record<string, unknown> | null;
  review_flags: Array<Record<string, unknown>>;
};

export type BatchMetadataQuality = {
  batch_id: number;
  total_files: number;
  approved_ready_count: number;
  review_recommended_count: number;
  review_required_count: number;
  blocked_count: number;
  worst_decision: MetadataQualityDecisionName;
  flag_counts: Record<string, number>;
  items: MetadataQualityDecision[];
};


export type UniversalReviewActionType =
  | "approve_candidate"
  | "mark_review_later"
  | "override_media_class"
  | "override_identity"
  | "merge_candidates"
  | "split_candidate"
  | "exclude_from_move_plan"
  | "block_candidate";

export type UniversalReviewAction = {
  id: number;
  batch_id: number;
  candidate_id?: number | null;
  source_fragment_id?: number | null;
  media_file_id?: number | null;
  action_type: UniversalReviewActionType | string;
  target_media_class?: string | null;
  target_candidate_id?: number | null;
  override_title?: string | null;
  override_primary_creator?: string | null;
  override_year?: string | null;
  override_series?: string | null;
  override_series_index?: string | null;
  override_release_type?: string | null;
  override_genre_family?: string | null;
  override_destination_root?: string | null;
  decision_status: string;
  reason?: string | null;
  note?: string | null;
  created_at?: string | null;
  updated_at?: string | null;
  applied_at?: string | null;
  created_by?: string | null;
};

export type UniversalReviewActionUpdate = {
  action_type: UniversalReviewActionType;
  candidate_id?: number | null;
  source_fragment_id?: number | null;
  media_file_id?: number | null;
  target_media_class?: string | null;
  target_candidate_id?: number | null;
  override_title?: string | null;
  override_primary_creator?: string | null;
  override_year?: string | null;
  override_series?: string | null;
  override_series_index?: string | null;
  override_release_type?: string | null;
  override_genre_family?: string | null;
  override_destination_root?: string | null;
  reason?: string | null;
  note?: string | null;
};
export type UniversalDecisionName =
  | "safe_group"
  | "split_recommended"
  | "merge_recommended"
  | "review_required"
  | "blocked_conflict";

export type UniversalIngestionSummary = {
  source_fragment_count: number;
  candidate_count: number;
  member_count: number;
  mixed_media_flag_count: number;
  decision_counts: Record<string, number>;
  media_class_counts: Record<string, number>;
  worst_decision: UniversalDecisionName;
  action_summary?: Record<string, unknown>;
};

export type SourceFragment = {
  id: number;
  batch_id: number;
  fragment_group_key?: string | null;
  source_root: string;
  source_path: string;
  fragment_label?: string | null;
  file_count: number;
  media_class_counts: Record<string, number>;
  created_at?: string | null;
  updated_at?: string | null;
  active_actions?: UniversalReviewAction[];
};

export type CandidateMember = {
  id: number;
  candidate_id: number;
  media_file_id?: number | null;
  ingest_file_id?: number | null;
  relative_path: string;
  filename: string;
  extension?: string | null;
  media_class: string;
  size_bytes?: number | null;
  duration_seconds?: string | null;
  track_number?: string | null;
  disc_number?: string | null;
  season_number?: string | null;
  episode_number?: string | null;
  title?: string | null;
  artist_or_author?: string | null;
  album_or_series?: string | null;
  member_role: string;
  confidence?: number | null;
  reason?: string | null;
  active_actions?: UniversalReviewAction[];
};

export type MediaIdentityCandidate = {
  id: number;
  batch_id: number;
  candidate_key: string;
  candidate_media_type: string;
  candidate_title?: string | null;
  candidate_primary_creator?: string | null;
  candidate_secondary_creator?: string | null;
  candidate_year?: string | null;
  candidate_series?: string | null;
  candidate_series_index?: string | null;
  candidate_confidence: number;
  candidate_confidence_label: string;
  member_count: number;
  source_fragment_count: number;
  recommended_action?: string | null;
  summary_reason?: string | null;
  members: CandidateMember[];
  active_actions?: UniversalReviewAction[];
};

export type FragmentReconstructionDecision = {
  id: number;
  batch_id: number;
  candidate_id?: number | null;
  source_fragment_id?: number | null;
  decision: UniversalDecisionName;
  severity: string;
  reason?: string | null;
  recommended_action?: string | null;
  conflict_flags: string[];
  created_at?: string | null;
};

export type MixedMediaFlag = {
  id: number;
  batch_id: number;
  source_fragment_id?: number | null;
  candidate_id?: number | null;
  flag_type: string;
  severity: string;
  message: string;
  media_classes_involved: string[];
  example_paths: string[];
  recommended_action?: string | null;
  created_at?: string | null;
};

export type BatchUniversalIngestion = {
  batch_id: number;
  phase: string;
  analysis_status: "not_analyzed" | "analyzed" | string;
  summary: UniversalIngestionSummary;
  source_fragments: SourceFragment[];
  candidates: MediaIdentityCandidate[];
  reconstruction_decisions: FragmentReconstructionDecision[];
  mixed_media_flags: MixedMediaFlag[];
  review_actions?: UniversalReviewAction[];
};

export type DuplicateFragmentBatch = {
  batch_id: number;
  title: string;
  creator?: string | null;
  year?: string | null;
  item_count: number;
  file_count?: number;
  file_ownership_status?: "verified" | "missing_files" | string;
  file_ownership_warning?: string | null;
  suggested_destination?: string | null;
  source_path?: string | null;
  status: string;
  detected_type: string;
};

export type DuplicateFragmentCluster = {
  cluster_id: string;
  review_type: string;
  media_type: string;
  confidence: string;
  reason: string;
  has_file_ownership_warnings?: boolean;
  batches: DuplicateFragmentBatch[];
};

export type DuplicateFragmentReview = {
  clusters: DuplicateFragmentCluster[];
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
  embedded_artwork_count?: number;
  embedded_artwork_files?: string[];
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
  music_review_summary?: MusicReviewSummary | null;
  action_message?: string | null;
  candidate_group_count?: number;
  approved_candidate_count?: number;
  excluded_candidate_count?: number;
  remaining_candidate_count?: number;
  needs_materialization?: boolean;
  parent_review_state?: "review_in_progress" | "candidates_approved_waiting_materialization" | "split_complete" | string | null;
  is_parent_review_container?: boolean;
  possible_duplicate_group_id?: string | null;
  possible_duplicate_count?: number;
  possible_fragment_group_id?: string | null;
  possible_fragment_count?: number;
  duplicate_fragment_review_state?: string;
  requires_duplicate_review?: boolean;
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
  genre?: string | null;
  genre_source?: string | null;
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
  genre?: string | null;
  release_type: DiscographyReleaseType;
  include: boolean;
  accepted_unknown_album_artist: boolean;
  accepted_unknown_album_title: boolean;
  accepted_unknown_year: boolean;
  lookup_later: boolean;
};

export type DiscographyMetadataUpdate = {
  artist: string;
  primary_genre?: string | null;
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
  audit_records: string[];
  notices: string[];
  warnings: string[];
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
  ignored_sidecar_only_folders: number;
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

export type ScanJobStatus = {
  job_id: string | null;
  status: "idle" | "running" | "completed" | "failed";
  phase?: string | null;
  message?: string | null;
  current_path?: string | null;
  started_at?: string | null;
  completed_at?: string | null;
  elapsed_seconds?: number;
  created?: number;
  skipped_duplicates?: number;
  result?: ScanMusicResponse | null;
  error_message?: string | null;
  already_running?: boolean;
};

export type PathHealth = {
  exists: boolean;
  is_dir: boolean;
  writable: boolean;
  error?: string | null;
};

export type SystemPathsResponse = {
  data_root: string;
  ingest_root: string;
  reports_dir: string;
  move_logs_dir: string;
  movies_dir: string;
  tv_dir: string;
  music_flac_dir: string;
  music_mp3_dir: string;
  books_dir: string;
  audiobooks_dir: string;
  path_health?: {
    data_root?: PathHealth;
    ingest_root?: PathHealth;
    reports_dir?: PathHealth;
  };
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

export type WorkspaceCandidateState = "blocked" | "review" | "safe" | "approved";

export type WorkspaceFilter =
  | "all"
  | "blocked"
  | "review"
  | "safe"
  | "music"
  | "audiobook"
  | "ebook"
  | "comic"
  | "movie"
  | "tv"
  | "artwork"
  | "unknown";

export interface RoutingDecision {
  batch_id: number;
  decision: "music_editor_allowed" | "universal_review_required" | "universal_review_recommended" | "blocked_conflict" | "not_analyzed";
  allowed_editors: string[];
  blocked_editors: string[];
  reasons: string[];
  universal_ingestion_available: boolean;
  requires_snapshot: boolean;
  summary: {
    candidate_count: number;
    media_types: string[];
    media_class_counts: Record<string, number>;
    mixed_media_flag_count: number;
    source_fragment_group_count?: number;
    reconstruction_decision_count?: number;
    blocked_conflict_count: number;
    review_required_count?: number;
    chunk_identity_candidate_count: number;
  };
  candidate_route_summaries?: Array<{
    candidate_id: number;
    candidate_title?: string | null;
    candidate_media_type?: string | null;
    candidate_key?: string | null;
    chunk_identity_risk: boolean;
  }>;
}
export interface CandidateMovePreviewSummary {
  candidate_count: number;
  source_fragment_count: number;
  member_count: number;
  media_class_counts: Record<string, number>;
  decision_counts: Record<string, number>;
  active_action_count: number;
  mixed_media: boolean;
  music_only_fragmented: boolean;
  blocked_conflict_count: number;
  review_required_count: number;
}

export interface CandidateMovePreviewGroup {
  candidate_id: number;
  candidate_media_type: string | null;
  candidate_title: string | null;
  candidate_primary_creator: string | null;
  candidate_year?: string | number | null;
  confidence?: string | null;
  member_count: number;
  source_fragment_count: number;
  active_action?: Record<string, unknown> | null;
  decision?: string | null;
  recommended_action?: string | null;
  target_library: string;
  destination_preview: string;
  source_fragment_names: string[];
  warnings: string[];
  blocked: boolean;
  requires_review: boolean;
}

export interface CandidateMovePreview {
  batch_id: number;
  status: "not_analyzed" | "ready" | "review_required" | "blocked_conflict";
  summary: CandidateMovePreviewSummary;
  preview_groups: CandidateMovePreviewGroup[];
  global_warnings: string[];
  next_actions: string[];
}
export interface SplitCandidateResult {
  parent_batch_id: number;
  child_batch_id: number;
  moved_file_count: number;
  remaining_parent_file_count: number;
  parent_status: string;
  child_detected_type: string;
  child_status: string;
  suggested_destination?: string | null;
  artist?: string | null;
  album?: string | null;
}

export interface MaterializeApprovedCandidatesResult {
  parent_batch_id: number;
  created_child_batch_ids: number[];
  created_count: number;
  skipped_count: number;
  parent_review_state: string;
  message: string;
}
