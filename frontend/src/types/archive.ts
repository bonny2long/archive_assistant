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
  disc_count: number;
  confidence: number;
  metadata_quality: string;
  metadata_warnings: string[];
  suggested_destination?: string | null;
  suggested_metadata?: SuggestedMetadata | null;
  metadata_confirmed: boolean;
  created_at: string;
};

export type SuggestedMetadata = {
  artist?: string | null;
  album?: string | null;
  year?: string | null;
  genre?: string | null;
};

export type BatchMetadataUpdate = {
  artist: string;
  album: string;
  year: string;
  primary_genre?: string | null;
  format?: string | null;
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

export type BatchActionResult = {
  batch_id: number;
  status: string;
  message: string;
  metadata_quality?: string | null;
  metadata_warnings?: string[] | null;
};

export type TabKey = "all" | "pending" | "needs_metadata" | "approved" | "moved";
