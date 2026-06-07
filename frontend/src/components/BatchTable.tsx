import { useState } from "react";
import type { BatchMoveSummary, BatchSummary, IngestBatch } from "../types/archive";
import BatchRow from "./BatchRow";

type Props = {
  batches: BatchSummary[];
  selected: Set<number>;
  details: Record<number, IngestBatch>;
  moveSummaries: Record<number, BatchMoveSummary>;
  detailLoading: Set<number>;
  detailErrors: Record<number, string>;
  loading?: boolean;
  error?: string;
  bulkLoading: boolean;
  onSelectOne: (id: number, checked: boolean) => void;
  onSelectAll: (checked: boolean) => void;
  onLoadDetail: (id: number) => Promise<void>;
  onApprove: (id: number) => void;
  onReject: (id: number) => void;
  onRecovery: (id: number) => void;
  onEdit: (batch: BatchSummary) => void;
  onBulkApprove: () => Promise<void>;
  onBulkReject: () => Promise<void>;
};

export default function BatchTable({
  batches,
  selected,
  details,
  moveSummaries,
  detailLoading,
  detailErrors,
  loading,
  error,
  bulkLoading,
  onSelectOne,
  onSelectAll,
  onLoadDetail,
  onApprove,
  onReject,
  onRecovery,
  onEdit,
  onBulkApprove,
  onBulkReject,
}: Props) {
  const [expanded, setExpanded] = useState<number | null>(null);
  const allChecked = batches.length > 0 && batches.every((batch) => selected.has(batch.id));

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
          <span>{selected.size} selected</span>
          <button className="btn btn--compact" disabled={bulkLoading} onClick={() => void onBulkApprove()}>
            <i className={`ti ti-${bulkLoading ? "loader-2 spinner" : "check"}`} /> Approve selected
          </button>
          <button className="btn btn--compact" disabled={bulkLoading} onClick={() => void onBulkReject()}>
            <i className="ti ti-x" /> Reject selected
          </button>
          <button className="btn btn--compact" disabled={bulkLoading} onClick={() => onSelectAll(false)}>
            Clear
          </button>
        </div>
      )}
      <div className="batch-table-scroll">
        <table className="batch-table">
          <colgroup>
            <col style={{ width: 36 }} />
            <col style={{ width: 48 }} />
            <col style={{ width: "17%" }} />
            <col style={{ width: "22%" }} />
            <col style={{ width: "7%" }} />
            <col style={{ width: "7%" }} />
            <col style={{ width: "10%" }} />
            <col style={{ width: "12%" }} />
            <col style={{ width: "16%" }} />
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
              <th>Artist</th>
              <th>Album</th>
              <th>Year</th>
              <th style={{ textAlign: "center" }}>Tracks</th>
              <th>Status</th>
              <th>Confidence</th>
              <th>Actions</th>
            </tr>
          </thead>
          <tbody>
            {loading && (
              <tr><td colSpan={9}><div className="state-msg"><i className="ti ti-loader-2 spinner" />Loading batches...</div></td></tr>
            )}
            {!loading && error && (
              <tr><td colSpan={9}><div className="state-msg state-msg--error"><i className="ti ti-wifi-off" />{error}</div></td></tr>
            )}
            {!loading && !error && batches.map((batch, index) => (
              <BatchRow
                key={batch.id}
                batch={batch}
                detail={details[batch.id]}
                moveSummary={moveSummaries[batch.id]}
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
                onEdit={onEdit}
              />
            ))}
          </tbody>
        </table>
      </div>
      {!loading && !error && batches.length === 0 && (
        <div className="state-msg"><i className="ti ti-inbox" />No batches here</div>
      )}
    </div>
  );
}
