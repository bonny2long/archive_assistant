import type { BatchSummary } from "../types/archive";

type Props = {
  batch: BatchSummary;
  saving: boolean;
  confirmLabel: string;
  onConfirm: () => Promise<void>;
};

export default function ReviewIssuesPanel({
  batch,
  saving,
  confirmLabel,
  onConfirm,
}: Props) {
  const blockers = batch.blocking_review_items ?? [];
  const warnings = batch.non_blocking_review_items ?? [];
  if (blockers.length === 0 && warnings.length === 0 && batch.review_confirmed) {
    return null;
  }

  return (
    <section className="review-issues">
      <div className="review-issues__summary">
        <strong>{blockers.length > 0 ? "Review required" : "Review available"}</strong>
        <span>{blockers.length} blocking item(s) · {warnings.length} warning(s)</span>
      </div>
      {blockers.length > 0 && (
        <div>
          <h3>Blocking issues</h3>
          {blockers.map((item, index) => (
            <p key={`${item.type}-${item.file_name ?? item.source_folder ?? index}`}>
              <i className="ti ti-alert-triangle" /> {item.message}
              {(item.file_name || item.source_folder) && (
                <small>{item.file_name ?? item.source_folder}</small>
              )}
            </p>
          ))}
        </div>
      )}
      {warnings.length > 0 && (
        <div>
          <h3>Warnings</h3>
          {warnings.map((item, index) => (
            <p key={`${item.type}-${item.file_name ?? index}`}>
              <i className="ti ti-info-circle" /> {item.message}
              {item.file_name && <small>{item.file_name}</small>}
            </p>
          ))}
        </div>
      )}
      {blockers.length === 0 && !batch.review_confirmed && (
        <button
          type="button"
          className="btn btn--green"
          disabled={saving}
          onClick={() => void onConfirm()}
        >
          <i className={`ti ti-${saving ? "loader-2 spinner" : "checks"}`} />
          {confirmLabel}
        </button>
      )}
    </section>
  );
}
