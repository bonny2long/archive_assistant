import type { BatchUniversalIngestion, IngestBatch, RoutingDecision } from "../types/archive";
import { getBatchPrimaryName, getBatchSecondaryName } from "../utils/batchDisplay";

type Props = {
  batch: IngestBatch;
  ingestion: BatchUniversalIngestion | null;
  routing: RoutingDecision | null;
  onClose: () => void;
  onApprove: (batchId: number) => Promise<void>;
};

function decisionLabel(decision: string | undefined): string {
  return (decision ?? "loading").replace(/_/g, " ");
}

function hasActiveAction(actions: Array<{ action_type: string; decision_status?: string | null }>, actionType: string): boolean {
  return actions.some((action) => action.action_type === actionType && action.decision_status !== "cleared");
}

export default function WorkspaceHeader({ batch, ingestion, routing, onClose, onApprove }: Props) {
  const blocked = ingestion?.summary.decision_counts.blocked_conflict ?? 0;
  const review = ingestion?.summary.decision_counts.review_required ?? 0;
  const candidateCount = ingestion?.summary.candidate_count ?? 0;
  const canApprove = !!ingestion && blocked === 0 && review === 0;
  const candidates = ingestion?.candidates ?? [];
  const isParentReviewContainer = candidateCount > 1;
  const approvedCount = candidates.filter((candidate) => hasActiveAction(candidate.active_actions ?? [], "approve_candidate")).length;
  const excludedCount = candidates.filter((candidate) => hasActiveAction(candidate.active_actions ?? [], "exclude_from_move_plan")).length;
  const remainingCount = candidates.filter((candidate) => {
    const actions = candidate.active_actions ?? [];
    return !hasActiveAction(actions, "approve_candidate") && !hasActiveAction(actions, "exclude_from_move_plan");
  }).length || (ingestion ? 0 : candidateCount);
  const allCandidatesResolved = isParentReviewContainer && approvedCount > 0 && remainingCount === 0;
  const approveDisabled = isParentReviewContainer || !canApprove;
  const approveTitle = isParentReviewContainer
    ? "Approved candidate groups must be materialized into child batches before this parent can move."
    : "Approves groups the backend currently considers safe. Individual candidate decisions remain visible in the workspace.";
  const approveLabel = isParentReviewContainer
    ? "Child batch creation required"
    : "Approve backend-safe groups";

  return (
    <header className="review-workspace__header">
      <div>
        <div className="review-workspace__eyebrow">Review Workspace</div>
        <h2>{getBatchPrimaryName(batch)}</h2>
        <p>{getBatchSecondaryName(batch)}</p>
        <div className="review-workspace__badges">
          {approvedCount > 0 && (
            <span className="review-workspace__badge--approved">
              <i className="ti ti-circle-check" /> {approvedCount} {isParentReviewContainer ? "approved candidate groups" : "approved"}
            </span>
          )}
          {excludedCount > 0 && (
            <span className="review-workspace__badge--excluded">
              <i className="ti ti-eye-off" /> {excludedCount} excluded
            </span>
          )}
          <span className={remainingCount > 0 ? "review-workspace__badge--remaining" : ""}>
            {remainingCount} remaining
          </span>
          <span>{batch.files.length} files</span>
          <span>{decisionLabel(routing?.decision)}</span>
          {routing?.summary.chunk_identity_candidate_count ? (
            <span className="review-workspace__badge--warn">chunk identity risk</span>
          ) : null}
          {allCandidatesResolved && (
            <span className="review-workspace__badge--warn">Next: create child batches</span>
          )}
        </div>
        {routing && routing.decision !== "music_editor_allowed" && (
          <small className="review-workspace__routing">
            {routing.reasons.length ? routing.reasons.join(" | ") : "Universal review is recommended for this batch."}
          </small>
        )}
      </div>
      <div className="review-workspace__header-actions">
        <button
          className="btn btn--green"
          disabled={approveDisabled}
          title={approveTitle}
          onClick={() => void onApprove(batch.id)}
        >
          <i className="ti ti-check" /> {approveLabel}
        </button>
        <button className="btn-sm" title="Close Review Workspace" onClick={onClose}>
          <i className="ti ti-x" />
        </button>
      </div>
    </header>
  );
}
