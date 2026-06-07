import type { BatchSummary } from "../types/archive";

type Props = {
  batches: BatchSummary[];
  loading: boolean;
  onConfirm: () => void;
  onClose: () => void;
};

const BLOCKING_WARNINGS = new Set([
  "possible_duplicate_destination",
  "possible_artist_alias",
  "possible_archived_duplicate_candidate",
  "destination_file_conflict",
  "child_album_metadata_missing",
  "discography_destination_exists",
]);

function isApprovable(batch: BatchSummary): boolean {
  return batch.status === "pending_review"
    && !batch.metadata_warnings.some((warning) => BLOCKING_WARNINGS.has(warning));
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
            <p>These albums will be marked ready to move. No files will be moved yet.</p>
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
                <strong>{batch.artist ?? "Unknown Artist"} - {batch.album ?? "Unknown Album"}</strong>
                <small>
                  {isApprovable(batch)
                    ? "ready to approve"
                    : batch.status === "pending_review"
                      ? "blocked by warning"
                      : batch.status.replace(/_/g, " ")}
                </small>
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
