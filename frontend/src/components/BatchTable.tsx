import { useState } from "react";
import type { BatchMoveSummary, BatchReview, BatchSummary, IngestBatch } from "../types/archive";
import BatchRow from "./BatchRow";

const BLOCKING_APPROVAL_WARNINGS = new Set([
  "possible_duplicate_destination",
  "possible_artist_alias",
  "possible_archived_duplicate_candidate",
  "destination_file_conflict",
  "child_album_metadata_missing",
  "discography_destination_exists",
  "movie_destination_exists",
  "tv_destination_exists",
]);

function isProcessedContainerBatch(batch: BatchSummary): boolean {
  return Boolean(batch.parent_is_drained || batch.parent_container_state === "drained_parent" || batch.display_state === "drained_parent");
}
type Props = {
  batches: BatchSummary[];
  selected: Set<number>;
  details: Record<number, IngestBatch>;
  moveSummaries: Record<number, BatchMoveSummary>;
  reviews: Record<number, BatchReview>;
  detailLoading: Set<number>;
  detailErrors: Record<number, string>;
  isInitialLoading?: boolean;
  isRefreshing?: boolean;
  hasLoaded?: boolean;
  error?: string;
  bulkLoading: boolean;
  onSelectOne: (id: number, checked: boolean) => void;
  onSelectAll: (checked: boolean) => void;
  onLoadDetail: (id: number) => Promise<void>;
  onApprove: (id: number) => void;
  onReject: (id: number) => void;
  onRecovery: (id: number) => void;
  onQuarantine: (id: number) => void;
  onRestoreQuarantine: (id: number) => void;
  onEdit: (batch: BatchSummary) => void;
  onOpenWorkspace: (batch: BatchSummary) => void;
  onBulkApprove: () => Promise<void>;
  onBulkReject: () => Promise<void>;
};

export default function BatchTable({
  batches,
  selected,
  details,
  moveSummaries,
  reviews,
  detailLoading,
  detailErrors,
  isInitialLoading = false,
  isRefreshing = false,
  hasLoaded = false,
  error,
  bulkLoading,
  onSelectOne,
  onSelectAll,
  onLoadDetail,
  onApprove,
  onReject,
  onRecovery,
  onQuarantine,
  onRestoreQuarantine,
  onEdit,
  onOpenWorkspace,
  onBulkApprove,
  onBulkReject,
}: Props) {
  const [expanded, setExpanded] = useState<number | null>(null);
  const allChecked = batches.length > 0 && batches.every((batch) => selected.has(batch.id));
  const selectedBatches = batches.filter((batch) => selected.has(batch.id));
  const approvableCount = selectedBatches.filter(
    (batch) => !isProcessedContainerBatch(batch) && batch.status === "pending_review"
      && !batch.metadata_warnings.some(
        (warning) => BLOCKING_APPROVAL_WARNINGS.has(warning),
      ),
  ).length;
  const rejectableCount = selectedBatches.filter(
    (batch) => batch.status !== "moved",
  ).length;

  const handleToggle = (id: number) => {
    if (expanded === id) {
      setExpanded(null);
      return;
    }
    setExpanded(id);
    if (!details[id]) void onLoadDetail(id);
  };

  return (
    <div className="batch-table-wrap">
      {selected.size > 0 && (
        <div className="selection-bar">
          <span>
            {selected.size} selected
            {approvableCount !== selected.size && ` · ${approvableCount} ready to approve`}
          </span>
          {approvableCount > 0 && (
            <button className="btn btn--compact" disabled={bulkLoading} onClick={() => void onBulkApprove()}>
              <i className={`ti ti-${bulkLoading ? "loader-2 spinner" : "check"}`} /> Approve selected
            </button>
          )}
          {rejectableCount > 0 && (
            <button className="btn btn--compact" disabled={bulkLoading} onClick={() => void onBulkReject()}>
              <i className="ti ti-x" /> Reject selected
            </button>
          )}
          <button className="btn btn--compact" disabled={bulkLoading} onClick={() => onSelectAll(false)}>
            Clear
          </button>
        </div>
      )}
      {isRefreshing && batches.length > 0 && (
        <div className="batch-table__refreshing"><i className="ti ti-loader-2 spinner" /> Refreshing...</div>
      )}
      {error && batches.length > 0 && (
        <div className="batch-table__refreshing batch-table__refreshing--error"><i className="ti ti-wifi-off" /> Could not refresh batches. Keeping the last loaded table.</div>
      )}
      <div className="batch-table-scroll">
        <table className="batch-table">
          <colgroup>
            <col style={{ width: 36 }} />
            <col style={{ width: 42 }} />
            <col style={{ width: 90 }} />
            <col />
            <col />
            <col style={{ width: 65 }} />
            <col style={{ width: 90 }} />
            <col style={{ width: 120 }} />
            <col style={{ width: 110 }} />
            <col style={{ width: 180 }} />
          </colgroup>
          <thead>
            <tr>
              <th style={{ textAlign: "center" }}>
                <input
                  aria-label="Select all visible batches"
                  type="checkbox"
                  checked={allChecked}
                  onChange={(event) => onSelectAll(event.target.checked)}
                />
              </th>
              <th>#</th>
              <th>Type</th>
              <th>Name</th>
              <th>Details</th>
              <th>Year</th>
              <th>Items</th>
              <th>Status</th>
              <th>Confidence</th>
              <th>Actions</th>
            </tr>
          </thead>
          <tbody>
            {isInitialLoading && batches.length === 0 && !hasLoaded && (
              <tr><td colSpan={10}><div className="state-msg"><i className="ti ti-loader-2 spinner" />Loading saved batches...</div></td></tr>
            )}
            {!isInitialLoading && error && batches.length === 0 && (
              <tr><td colSpan={10}><div className="state-msg state-msg--error"><i className="ti ti-wifi-off" />Could not load batches. Backend may be unavailable.</div></td></tr>
            )}
            {batches.map((batch, index) => (
              <BatchRow
                key={batch.id}
                batch={batch}
                detail={details[batch.id]}
                moveSummary={moveSummaries[batch.id]}
                review={reviews[batch.id]}
                detailLoading={detailLoading.has(batch.id)}
                detailError={detailErrors[batch.id]}
                index={index + 1}
                selected={selected.has(batch.id)}
                expanded={expanded === batch.id}
                onSelect={onSelectOne}
                onToggle={handleToggle}
                onApprove={onApprove}
                onReject={onReject}
                onRecovery={onRecovery}
                onQuarantine={onQuarantine}
                onRestoreQuarantine={onRestoreQuarantine}
                onEdit={onEdit}
                onOpenWorkspace={onOpenWorkspace}
              />
            ))}
          </tbody>
        </table>
      </div>
      {!isInitialLoading && !error && hasLoaded && batches.length === 0 && (
        <div className="state-msg"><i className="ti ti-inbox" />No batches found. Click Scan ingest to discover ready media.</div>
      )}
    </div>
  );
}
