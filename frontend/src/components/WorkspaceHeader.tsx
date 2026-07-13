import type { BatchUniversalIngestion, IngestBatch, RoutingDecision } from "../types/archive";
import { getBatchPrimaryName, getBatchSecondaryName } from "../utils/batchDisplay";

type Props = {
  batch: IngestBatch;
  ingestion: BatchUniversalIngestion | null;
  routing: RoutingDecision | null;
  onClose: () => void;
  onApprove: (batchId: number) => Promise<void>;
  onOpenFullEditor?: () => void;
  onMaterializeApprovedCandidates?: () => Promise<void>;
  materializing?: boolean;
};

function decisionLabel(decision: string | undefined): string {
  return (decision ?? "loading").replace(/_/g, " ");
}

function hasActiveAction(actions: Array<{ action_type: string; decision_status?: string | null }>, actionType: string): boolean {
  return actions.some((action) => action.action_type === actionType && action.decision_status !== "cleared");
}

function hasPendingAction(actions: Array<{ action_type: string; decision_status?: string | null }>, actionType: string): boolean {
  return actions.some((action) => action.action_type === actionType && action.decision_status !== "cleared" && action.decision_status !== "applied");
}

export default function WorkspaceHeader({
  batch,
  ingestion,
  routing,
  onClose,
  onApprove,
  onOpenFullEditor,
  onMaterializeApprovedCandidates,
  materializing = false,
}: Props) {
  const blocked = ingestion?.summary.decision_counts.blocked_conflict ?? 0;
  const review = ingestion?.summary.decision_counts.review_required ?? 0;
  const candidateCount = ingestion?.summary.candidate_count ?? 0;
  const canApprove = !!ingestion && blocked === 0 && review === 0;
  const candidates = ingestion?.candidates ?? [];
  const isParentReviewContainer = candidateCount > 1;
  const approvedCount = candidates.filter((candidate) => hasPendingAction(candidate.active_actions ?? [], "approve_candidate")).length;
  const createdChildCount = candidates.filter((candidate) => hasActiveAction(candidate.active_actions ?? [], "approve_candidate") && !hasPendingAction(candidate.active_actions ?? [], "approve_candidate")).length;
  const excludedCount = candidates.filter((candidate) => hasActiveAction(candidate.active_actions ?? [], "exclude_from_move_plan")).length;
  const blockedCount = candidates.filter((candidate) => hasActiveAction(candidate.active_actions ?? [], "block_candidate")).length;
  const reviewLaterCount = candidates.filter((candidate) => hasActiveAction(candidate.active_actions ?? [], "mark_review_later")).length;
  const remainingCount = candidates.filter((candidate) => {
    const actions = candidate.active_actions ?? [];
    return !hasActiveAction(actions, "approve_candidate")
      && !hasActiveAction(actions, "exclude_from_move_plan")
      && !hasActiveAction(actions, "block_candidate")
      && !hasActiveAction(actions, "mark_review_later");
  }).length || (ingestion ? 0 : candidateCount);
  const canMaterialize = isParentReviewContainer && approvedCount > 0 && !!onMaterializeApprovedCandidates;
  const canOpenAudiobookEditor = batch.detected_type === "audiobook"
    && candidateCount === 1
    && routing?.decision === "audiobook_editor_allowed"
    && !!onOpenFullEditor;
  const approveDisabled = isParentReviewContainer || !canApprove;
  const approveTitle = isParentReviewContainer
    ? "Approved candidate groups must be created as child batches before this parent can move."
    : "Approves groups the backend currently considers safe. Individual candidate decisions remain visible in the workspace.";
  const approveLabel = isParentReviewContainer
    ? "Create child batches"
    : "Approve backend-safe groups";
  const materializeLabel = `Create ${approvedCount} child batch${approvedCount === 1 ? "" : "es"}`;
  const sourceOriginCount = ingestion?.summary.resolved_source_origin_count
    ?? ingestion?.summary.source_origin_count
    ?? 0;
  const missingTrackValues = batch.metadata_json?.missing_track_numbers;
  const missingTrackNumbers = (Array.isArray(missingTrackValues) ? missingTrackValues : [])
    .map((value: unknown) => Number(value))
    .filter((value: number) => Number.isInteger(value) && value > 0);

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
          {createdChildCount > 0 && (
            <span className="review-workspace__badge--approved">
              <i className="ti ti-git-branch" /> {createdChildCount} child batches created
            </span>
          )}
          {excludedCount > 0 && (
            <span className="review-workspace__badge--excluded">
              <i className="ti ti-eye-off" /> {excludedCount} excluded
            </span>
          )}
          {blockedCount > 0 && <span className="review-workspace__badge--warn">{blockedCount} blocked</span>}
          {reviewLaterCount > 0 && <span>{reviewLaterCount} review later</span>}
          <span className={remainingCount > 0 ? "review-workspace__badge--remaining" : ""}>
            {remainingCount} unresolved
          </span>
          <span>{batch.files.length} files</span>
          {ingestion?.summary.source_origins_resolved && sourceOriginCount > 1 && (
            <span><i className="ti ti-folders" /> Merged from {sourceOriginCount} source folders</span>
          )}
          {missingTrackNumbers.length > 0 && (
            <span className="review-workspace__badge--warn">
              Partial track set - missing tracks {missingTrackNumbers.join(" and ")}
            </span>
          )}
          <span>{decisionLabel(routing?.decision)}</span>
          {routing?.summary.chunk_identity_candidate_count ? (
            <span className="review-workspace__badge--warn">chunk identity risk</span>
          ) : null}
          {canMaterialize && (
            <span className="review-workspace__badge--warn">Next: create child batches</span>
          )}
        </div>
        {routing && !["music_editor_allowed", "audiobook_editor_allowed"].includes(routing.decision) && (
          <small className="review-workspace__routing">
            {routing.reasons.length ? routing.reasons.join(" | ") : "Universal review is recommended for this batch."}
          </small>
        )}
      </div>
      <div className="review-workspace__header-actions">
        {canOpenAudiobookEditor ? (
          <button
            className="btn btn--green"
            title="Open the audiobook metadata editor for this single scoped book."
            onClick={onOpenFullEditor}
          >
            <i className="ti ti-headphones" /> Open audiobook editor
          </button>
        ) : canMaterialize ? (
          <button
            className="btn btn--green"
            disabled={materializing}
            title="Creates child review batches from approved candidate groups. Files are not moved to the final library."
            onClick={() => void onMaterializeApprovedCandidates?.()}
          >
            <i className={`ti ti-${materializing ? "loader-2 spinner" : "git-branch"}`} /> {materializeLabel}
          </button>
        ) : (
          <button
            className="btn btn--green"
            disabled={approveDisabled}
            title={approveTitle}
            onClick={() => void onApprove(batch.id)}
          >
            <i className="ti ti-check" /> {approveLabel}
          </button>
        )}
        <button className="btn-sm" title="Close Review Workspace" onClick={onClose}>
          <i className="ti ti-x" />
        </button>
      </div>
    </header>
  );
}
