import type { BatchSummary } from "../types/archive";
import {
  getBatchDisplayTitle,
  getBatchPrimaryName,
  getBatchSecondaryName,
} from "../utils/batchDisplay";

type Props = {
  batches: BatchSummary[];
  loading: boolean;
  onConfirm: () => void;
  onClose: () => void;
};

function isApprovable(batch: BatchSummary): boolean {
  return batch.status === "pending_review"
    && batch.blocking_review_items.length === 0;
}

function approvalTitle(batch: BatchSummary): string {
  if (batch.detected_type === "video_movie") {
    return `${getBatchPrimaryName(batch)} - ${getBatchSecondaryName(batch)}`;
  }
  return getBatchDisplayTitle(batch);
}

function approvalStatus(batch: BatchSummary): string {
  if (isApprovable(batch)) return "Ready to approve";
  if (batch.blocking_review_items.length > 0) {
    return "Blocked - fix review first";
  }
  if (batch.status === "approved") return "Already approved - skipped";
  return `${batch.status.replace(/_/g, " ")} - skipped`;
}

export default function BulkApproveModal({
  batches,
  loading,
  onConfirm,
  onClose,
}: Props) {
  const valid = batches.filter(isApprovable);
  const skipped = batches.length - valid.length;

  return (
    <div className="modal-backdrop" role="presentation" onMouseDown={onClose}>
      <section
        className="confirm-modal"
        role="dialog"
        aria-modal="true"
        aria-labelledby="bulk-approve-title"
        onMouseDown={(event) => event.stopPropagation()}
      >
        <div className="confirm-modal__header">
          <div>
            <h2 id="bulk-approve-title">Approve selected batches?</h2>
            <p>These releases will be marked ready to move. No files will be moved yet.</p>
          </div>
          <button className="btn-sm" disabled={loading} title="Close" onClick={onClose}>
            <i className="ti ti-x" />
          </button>
        </div>

        <div className="confirm-modal__list">
          {batches.map((batch) => (
            <div key={batch.id}>
              <i className={`ti ti-${isApprovable(batch) ? "disc" : "alert-triangle"}`} />
              <span>
                <strong>{approvalTitle(batch)}</strong>
                <small>{approvalStatus(batch)}</small>
              </span>
            </div>
          ))}
        </div>

        {skipped > 0 && (
          <p className="confirm-modal__warning">
            {skipped} selected batch(es) are not pending review and will be skipped.
          </p>
        )}

        <div className="confirm-modal__actions">
          <button className="btn" disabled={loading} onClick={onClose}>Cancel</button>
          <button
            className="btn btn--green"
            disabled={loading || valid.length === 0}
            onClick={onConfirm}
          >
            <i className={`ti ti-${loading ? "loader-2 spinner" : "check"}`} />
            Approve selected
          </button>
        </div>
      </section>
    </div>
  );
}
