import type {
  BatchSummary,
  BatchActionResult,
  BatchMetadataUpdate,
  IngestBatch,
  MoveResult,
  PaginatedResponse,
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
  listBatches: () => request<PaginatedResponse<BatchSummary>>("/batches?page_size=100"),
  listPending: () => request<PaginatedResponse<BatchSummary>>("/batches/pending?page_size=100"),
  getBatch: (id: number) => request<IngestBatch>(`/batches/${id}`),
  updateBatchMetadata: (id: number, update: BatchMetadataUpdate) =>
    request<BatchSummary>(`/batches/${id}/metadata`, "PATCH", update),
  scanMusic: () => request<IngestBatch[]>("/scan/music", "POST"),
  approveBatch: (id: number) => request<BatchActionResult>(`/batches/${id}/approve`, "POST"),
  rejectBatch: (id: number) => request<BatchActionResult>(`/batches/${id}/reject`, "POST"),
  sendToRecovery: (id: number) => request<BatchActionResult>(`/batches/${id}/recovery`, "POST"),
  moveApproved: () => request<MoveResult>("/move/approved", "POST"),
};
