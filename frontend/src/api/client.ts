import type {
  BatchSummary,
  BatchActionResult,
  BatchMetadataUpdate,
  BatchMoveSummary,
  BatchMetadataQuality,
  BatchReview,
  BatchUniversalIngestion,
  CandidateMovePreview,
  AudiobookMetadataUpdate,
  BookCollectionReviewUpdate,
  BookMetadataUpdate,
  BulkApproveResult,
  DevResetResponse,
  DiscographyMetadataUpdate,
  DuplicateFragmentResolutionRequest,
  DuplicateFragmentResolutionResponse,
  DuplicateFragmentReview,
  HealthResponse,
  IngestBatch,
  LibrarySummary,
  MovieCollectionReviewUpdate,
  MovieMetadataUpdate,
  MoveResult,
  SelectedMovePreflight,
  SelectedMoveResult,
  PaginatedResponse,
  ScanMusicResponse,
  ScanJobStatus,
  SplitCandidateResult,
  SplitDiscographyReleasesResult,
  MaterializeApprovedCandidatesResult,
  SystemPathsResponse,
  SystemTimeResponse,
  TvMetadataUpdate,
  TvEpisodeReviewUpdate,
  ReviewConfirmationUpdate,
  RoutingDecision,
  UniversalReviewAction,
  UniversalReviewActionUpdate,
  MetadataEnrichmentApplyResponse,
  MetadataEnrichmentPreview,
} from "../types/archive";

const BASE = "/api";
const BATCH_LIST_TIMEOUT_MS = 30000;

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

async function request<T>(path: string, method = "GET", body?: unknown, timeoutMs?: number): Promise<T> {
  const controller = timeoutMs ? new AbortController() : undefined;
  const timeoutId = timeoutMs
    ? window.setTimeout(() => controller?.abort(), timeoutMs)
    : undefined;
  let res: Response;
  try {
    res = await fetch(`${BASE}${path}`, {
      method,
      headers: body === undefined ? undefined : { "Content-Type": "application/json" },
      body: body === undefined ? undefined : JSON.stringify(body),
      signal: controller?.signal,
    });
  } catch (error) {
    if (error instanceof DOMException && error.name === "AbortError") {
      throw new Error(`${method} ${path} timed out. Refresh and try again.`);
    }
    throw error;
  } finally {
    if (timeoutId !== undefined) window.clearTimeout(timeoutId);
  }
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
  listBatches: () => request<PaginatedResponse<BatchSummary>>("/batches?page_size=100", "GET", undefined, BATCH_LIST_TIMEOUT_MS),
  listPending: () => request<PaginatedResponse<BatchSummary>>("/batches/pending?page_size=100", "GET", undefined, BATCH_LIST_TIMEOUT_MS),
  getBatch: (id: number) => request<IngestBatch>(`/batches/${id}`),
  getBatchChildBatches: (id: number) => request<BatchSummary[]>(`/batches/${id}/child-batches`),
  getBatchReview: (id: number) => request<BatchReview>(`/batches/${id}/review`),
  getBatchMetadataQuality: (id: number) =>
    request<BatchMetadataQuality>(`/batches/${id}/metadata-quality`),
  getBatchUniversalIngestion: (id: number, snapshot = false) =>
    request<BatchUniversalIngestion>(`/batches/${id}/universal-ingestion${snapshot ? "?snapshot=true" : ""}`),
  createUniversalIngestionAction: (id: number, update: UniversalReviewActionUpdate) =>
    request<UniversalReviewAction>(`/batches/${id}/universal-ingestion/actions`, "POST", update),
  clearUniversalIngestionAction: (id: number, actionId: number) =>
    request<UniversalReviewAction>(`/batches/${id}/universal-ingestion/actions/${actionId}/clear`, "POST"),
  getDuplicateFragmentReview: () => request<DuplicateFragmentReview>("/duplicate-fragment-review"),
  getBatchDuplicateFragmentReview: (id: number) => request<DuplicateFragmentReview>(`/batches/${id}/duplicate-fragment-review`),
  resolveDuplicateFragmentReview: (id: number, update: DuplicateFragmentResolutionRequest) =>
    request<DuplicateFragmentResolutionResponse>(`/batches/${id}/duplicate-fragment-review/resolve`, "POST", update),
  getReviewRouting: (id: number, targetEditor?: string) =>
    request<RoutingDecision>(`/batches/${id}/review-routing${targetEditor ? `?target_editor=${targetEditor}` : ""}`),
  getCandidateMovePreview: (id: number, snapshot = false) =>
    request<CandidateMovePreview>(`/batches/${id}/candidate-move-preview${snapshot ? "?snapshot=true" : ""}`),
  splitCandidate: (id: number, candidateId: number) =>
    request<SplitCandidateResult>(`/batches/${id}/split-candidate`, "POST", { candidate_id: candidateId }),
  splitDiscographyReleases: (id: number) =>
    request<SplitDiscographyReleasesResult>(`/batches/${id}/split-discography-releases`, "POST", undefined, 180000),
  materializeApprovedCandidates: (id: number) =>
    request<MaterializeApprovedCandidatesResult>(`/batches/${id}/materialize-approved-candidates`, "POST", undefined, 180000),
  createUniversalIngestionChildBatches: (id: number) =>
    request<MaterializeApprovedCandidatesResult>(`/batches/${id}/universal-ingestion/create-child-batches`, "POST", undefined, 180000),
  getBatchMoves: (id: number) => request<BatchMoveSummary>(`/batches/${id}/moves`),
  previewMetadataEnrichment: (id: number) =>
    request<MetadataEnrichmentPreview>("/batches/" + id + "/metadata-enrichment/preview", "POST", undefined, 60000),
  applyMetadataEnrichment: (id: number, releaseId: string) =>
    request<MetadataEnrichmentApplyResponse>("/batches/" + id + "/metadata-enrichment/apply", "POST", { release_id: releaseId }, 60000),
  updateBatchMediaType: (
    id: number,
    targetDetectedType: "music_album" | "audiobook",
    expectedAudioFileIds: number[],
  ) =>
    request<BatchSummary>(`/batches/${id}/media-type`, "PATCH", {
      target_detected_type: targetDetectedType,
      confirmed: true,
      scope_confirmation: "all_attached_primary_audio_files",
      expected_audio_file_ids: expectedAudioFileIds,
    }),
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
  scanMusic: () => request<ScanJobStatus>("/scan/music", "POST"),
  scanStatus: () => request<ScanJobStatus>("/scan/status"),
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
  preflightSelectedMove: (batchIds: number[]) =>
    request<SelectedMovePreflight>("/move/selected/preflight", "POST", { batch_ids: batchIds }),
  moveSelected: (batchIds: number[]) =>
    request<SelectedMoveResult>("/move/selected", "POST", { batch_ids: batchIds }),
  moveBatch: (id: number) =>
    request<SelectedMoveResult>(`/batches/${id}/move`, "POST"),
  getLibrarySummary: () => request<LibrarySummary>("/library/summary"),
  resetTestData: () => request<DevResetResponse>("/dev/reset/test-data", "POST"),
};
