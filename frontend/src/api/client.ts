import type {
  BatchSummary,
  BatchActionResult,
  BatchMetadataUpdate,
  BatchMoveSummary,
  BatchReview,
  AudiobookMetadataUpdate,
  BookCollectionReviewUpdate,
  BookMetadataUpdate,
  BulkApproveResult,
  DevResetResponse,
  DiscographyMetadataUpdate,
  HealthResponse,
  IngestBatch,
  LibrarySummary,
  MovieCollectionReviewUpdate,
  MovieMetadataUpdate,
  MoveResult,
  PaginatedResponse,
  ScanMusicResponse,
  SystemPathsResponse,
  SystemTimeResponse,
  TvMetadataUpdate,
  TvEpisodeReviewUpdate,
  ReviewConfirmationUpdate,
} from "../types/archive";

const BASE = "/api";

export function formatApiError(errorBody: unknown, fallback: string): string {
  const detail = (
    errorBody as { detail?: unknown } | null
  )?.detail;

  if (typeof detail === "string") return detail;

  if (Array.isArray(detail)) {
    return detail
      .map((item) => {
        if (item && typeof item === "object") {
          const record = item as Record<string, unknown>;
          const loc = Array.isArray(record.loc)
            ? record.loc.join(".")
            : "";
          const msg = typeof record.msg === "string"
            ? record.msg
            : JSON.stringify(record);
          return loc ? `${loc}: ${msg}` : msg;
        }
        return String(item);
      })
      .join("; ");
  }

  if (detail && typeof detail === "object") {
    return JSON.stringify(detail);
  }

  return fallback;
}

async function request<T>(path: string, method = "GET", body?: unknown): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    method,
    headers: body === undefined ? undefined : { "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  if (!res.ok) {
    const errorBody = await res.json().catch(() => null);
    throw new Error(
      formatApiError(
        errorBody,
        `${method} ${path} returned ${res.status}`,
      ),
    );
  }
  const contentType = res.headers.get("content-type") ?? "";
  return contentType.includes("json") ? res.json() : (null as T);
}

export const api = {
  health: () => request<HealthResponse>("/health"),
  systemTime: () => request<SystemTimeResponse>("/system/time"),
  systemPaths: () => request<SystemPathsResponse>("/system/paths"),
  listBatches: () => request<PaginatedResponse<BatchSummary>>("/batches?page_size=100"),
  listPending: () => request<PaginatedResponse<BatchSummary>>("/batches/pending?page_size=100"),
  getBatch: (id: number) => request<IngestBatch>(`/batches/${id}`),
  getBatchReview: (id: number) => request<BatchReview>(`/batches/${id}/review`),
  getBatchMoves: (id: number) => request<BatchMoveSummary>(`/batches/${id}/moves`),
  updateBatchMetadata: (id: number, update: BatchMetadataUpdate) =>
    request<BatchSummary>(`/batches/${id}/metadata`, "PATCH", update),
  updateDiscographyMetadata: (id: number, update: DiscographyMetadataUpdate) =>
    request<BatchSummary>(`/batches/${id}/discography`, "PATCH", update),
  updateMovieMetadata: (id: number, update: MovieMetadataUpdate) =>
    request<BatchSummary>(`/batches/${id}/movie-metadata`, "PATCH", update),
  updateTvMetadata: (id: number, update: TvMetadataUpdate) =>
    request<BatchSummary>(`/batches/${id}/tv-metadata`, "PATCH", update),
  updateTvEpisodeReview: (id: number, update: TvEpisodeReviewUpdate) =>
    request<BatchSummary>(`/batches/${id}/tv-episode-review`, "PATCH", update),
  updateMovieCollectionReview: (id: number, update: MovieCollectionReviewUpdate) =>
    request<BatchSummary>(`/batches/${id}/movie-collection-review`, "PATCH", update),
  updateBookMetadata: (id: number, update: BookMetadataUpdate) =>
    request<BatchSummary>(`/batches/${id}/book-metadata`, "PATCH", update),
  updateBookCollectionReview: (id: number, update: BookCollectionReviewUpdate) =>
    request<BatchSummary>(`/batches/${id}/book-collection-review`, "PATCH", update),
  updateAudiobookMetadata: (id: number, update: AudiobookMetadataUpdate) =>
    request<BatchSummary>(`/batches/${id}/audiobook-metadata`, "PATCH", update),
  updateReviewConfirmation: (id: number, update: ReviewConfirmationUpdate) =>
    request<BatchSummary>(`/batches/${id}/review-confirmation`, "PATCH", update),
  scanMusic: () => request<ScanMusicResponse>("/scan/music", "POST"),
  approveBatch: (id: number) => request<BatchActionResult>(`/batches/${id}/approve`, "POST"),
  approveSelected: (batchIds: number[]) =>
    request<BulkApproveResult>("/batches/approve-selected", "POST", { batch_ids: batchIds }),
  rejectBatch: (id: number) => request<BatchActionResult>(`/batches/${id}/reject`, "POST"),
  sendToRecovery: (id: number) => request<BatchActionResult>(`/batches/${id}/recovery`, "POST"),
  quarantineBatch: (id: number) =>
    request<BatchSummary>(`/batches/${id}/quarantine`, "POST"),
  restoreQuarantinedBatch: (id: number) =>
    request<BatchSummary>(`/batches/${id}/restore-quarantine`, "POST"),
  moveApproved: () => request<MoveResult>("/move/approved", "POST"),
  getLibrarySummary: () => request<LibrarySummary>("/library/summary"),
  resetTestData: () => request<DevResetResponse>("/dev/reset/test-data", "POST"),
};
