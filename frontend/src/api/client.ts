import type {
  BatchSummary,
  BatchActionResult,
  BatchMetadataUpdate,
  BatchMoveSummary,
  BatchReview,
  BulkApproveResult,
  DevResetResponse,
  DiscographyMetadataUpdate,
  HealthResponse,
  IngestBatch,
  LibrarySummary,
  MoveResult,
  PaginatedResponse,
  ScanMusicResponse,
} from "../types/archive";

const BASE = "/api";

async function request<T>(path: string, method = "GET", body?: unknown): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    method,
    headers: body === undefined ? undefined : { "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  if (!res.ok) {
    const errorBody = await res.json().catch(() => null) as { detail?: string } | null;
    throw new Error(errorBody?.detail ?? `${method} ${path} returned ${res.status}`);
  }
  const contentType = res.headers.get("content-type") ?? "";
  return contentType.includes("json") ? res.json() : (null as T);
}

export const api = {
  health: () => request<HealthResponse>("/health"),
  listBatches: () => request<PaginatedResponse<BatchSummary>>("/batches?page_size=100"),
  listPending: () => request<PaginatedResponse<BatchSummary>>("/batches/pending?page_size=100"),
  getBatch: (id: number) => request<IngestBatch>(`/batches/${id}`),
  getBatchReview: (id: number) => request<BatchReview>(`/batches/${id}/review`),
  getBatchMoves: (id: number) => request<BatchMoveSummary>(`/batches/${id}/moves`),
  updateBatchMetadata: (id: number, update: BatchMetadataUpdate) =>
    request<BatchSummary>(`/batches/${id}/metadata`, "PATCH", update),
  updateDiscographyMetadata: (id: number, update: DiscographyMetadataUpdate) =>
    request<BatchSummary>(`/batches/${id}/discography`, "PATCH", update),
  scanMusic: () => request<ScanMusicResponse>("/scan/music", "POST"),
  approveBatch: (id: number) => request<BatchActionResult>(`/batches/${id}/approve`, "POST"),
  approveSelected: (batchIds: number[]) =>
    request<BulkApproveResult>("/batches/approve-selected", "POST", { batch_ids: batchIds }),
  rejectBatch: (id: number) => request<BatchActionResult>(`/batches/${id}/reject`, "POST"),
  sendToRecovery: (id: number) => request<BatchActionResult>(`/batches/${id}/recovery`, "POST"),
  moveApproved: () => request<MoveResult>("/move/approved", "POST"),
  getLibrarySummary: () => request<LibrarySummary>("/library/summary"),
  resetMusicTest: () => request<DevResetResponse>("/dev/reset/music-test", "POST"),
};
