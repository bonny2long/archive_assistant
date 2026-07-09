import type { BatchMoveSummary, BatchReview, BatchSummary, IngestBatch } from "../types/archive";
import BatchDetail from "./BatchDetail";
import {
  getBatchEditKind,
  getBatchItemText,
  getBatchMediaLabel,
  getBatchPrimaryName,
  getBatchSecondaryName,
} from "../utils/batchDisplay";

type Props = {
  batch: BatchSummary;
  detail?: IngestBatch;
  moveSummary?: BatchMoveSummary;
  review?: BatchReview;
  detailLoading: boolean;
  detailError?: string;
  index: number;
  selected: boolean;
  expanded: boolean;
  onSelect: (id: number, checked: boolean) => void;
  onToggle: (id: number) => void;
  onApprove: (id: number) => void;
  onReject: (id: number) => void;
  onRecovery: (id: number) => void;
  onQuarantine: (id: number) => void;
  onRestoreQuarantine: (id: number) => void;
  onEdit: (batch: BatchSummary) => void;
  onOpenWorkspace: (batch: BatchSummary) => void;
};

function confidenceColor(percent: number): string {
  if (percent >= 80) return "var(--accent-green)";
  if (percent >= 50) return "var(--accent-amber)";
  return "var(--accent-red)";
}

function pillClass(status: string): string {
  return `pill pill--${status}`;
}

function statusLabel(status: string): string {
  return status.replace(/_/g, " ");
}

function isParentReviewContainer(batch: BatchSummary): boolean {
  return Boolean(batch.is_parent_review_container || batch.parent_container_state);
}

function duplicateFragmentMatchCount(batch: BatchSummary): number {
  return Math.max(batch.possible_fragment_count ?? 0, batch.possible_duplicate_count ?? 0);
}

function hasActiveDuplicateFragmentReview(batch: BatchSummary): boolean {
  return Boolean(batch.requires_duplicate_review && duplicateFragmentMatchCount(batch) > 0);
}

function duplicateFragmentLabel(batch: BatchSummary): string | null {
  if (!hasActiveDuplicateFragmentReview(batch)) return null;
  if (batch.duplicate_fragment_review_state === "possible_fragment") return "Possible fragment";
  if (batch.duplicate_fragment_review_state === "possible_edition_conflict") return "Edition conflict review";
  if (batch.duplicate_fragment_review_state === "possible_append_to_canonical") return "Append to existing batch";
  return "Possible duplicate";
}

function batchStatusLabel(batch: BatchSummary): string {
  if (batch.parent_is_drained || batch.parent_container_state === "drained_parent" || batch.display_state === "drained_parent") {
    return "Drained intake container";
  }
  const duplicateLabel = duplicateFragmentLabel(batch);
  if (duplicateLabel) return duplicateLabel;
  if (!isParentReviewContainer(batch)) return statusLabel(batch.status);
  if (batch.parent_container_state === "partial_parent_container") return "Active files remaining";
  if ((batch.approved_candidate_count ?? 0) > 0 && (batch.unresolved_candidate_count ?? 0) === 0 && (batch.child_batch_count ?? 0) === 0) {
    return "Ready to create child batches";
  }
  if ((batch.child_batch_count ?? 0) > 0) return "Child batches created";
  return "Review in progress";
}

function MoveManifestProof({
  batch,
  moveSummary,
}: {
  batch: BatchSummary;
  moveSummary?: BatchMoveSummary;
}) {
  const manifest = moveSummary?.manifest ?? batch.move_manifest;
  if (!manifest) return null;
  return (
    <section className="move-manifest-proof">
      <div className="move-manifest-proof__heading">
        <div>
          <strong>Move manifest available</strong>
          <span>
            {manifest.archive_assistant_version ?? "Archive Assistant"}
            {" | "}
            {manifest.manifest_version}
          </span>
        </div>
        <div className="move-manifest-proof__counts">
          <span>{manifest.files_moved + manifest.artwork_moved} files</span>
          <span>{manifest.failed_moves} failed</span>
        </div>
      </div>
      <dl>
        <div><dt>JSON</dt><dd>{manifest.json_path}</dd></div>
        <div><dt>Markdown</dt><dd>{manifest.markdown_path ?? "Not created"}</dd></div>
      </dl>
    </section>
  );
}

export default function BatchRow({
  batch,
  detail,
  moveSummary,
  review,
  detailLoading,
  detailError,
  index,
  selected,
  expanded,
  onSelect,
  onToggle,
  onApprove,
  onReject,
  onRecovery,
  onQuarantine,
  onRestoreQuarantine,
  onEdit,
  onOpenWorkspace,
}: Props) {
  const awaitingQuarantine = batch.status === "needs_quarantine_review";
  const quarantined = batch.status === "quarantined";
  const quarantineReview = awaitingQuarantine || quarantined;
  const mediaLabel = getBatchMediaLabel(batch);
  const primaryName = getBatchPrimaryName(batch);
  const secondaryName = getBatchSecondaryName(batch);
  const itemText = getBatchItemText(batch);
  const editKind = getBatchEditKind(batch);
  const year = batch.year ?? "-";
  const percent = Math.round((batch.confidence ?? 0) * 100);
  const parentReviewContainer = isParentReviewContainer(batch);
  const drainedParent = Boolean(batch.parent_is_drained || batch.parent_container_state === "drained_parent" || batch.display_state === "drained_parent");
  const hasDiscographyRemainderReview = batch.parent_container_state === "partial_parent_container";
  const splitCompleteParent = drainedParent && !hasDiscographyRemainderReview;
  const isDiscographySplitChild =
    batch.detected_type === "music_album"
    && batch.review_origin === "multi_artist_discography_split";
  const canOpenWorkspace = batch.status !== "moved" && !quarantineReview && !splitCompleteParent && !isDiscographySplitChild;
  const shouldOpenEditorFromWorkspaceButton = isDiscographySplitChild && batch.status !== "moved" && !quarantineReview;
  const duplicateLabel = duplicateFragmentLabel(batch);
  const activeDuplicateReview = hasActiveDuplicateFragmentReview(batch);
  const duplicateMatchCount = duplicateFragmentMatchCount(batch);
  const approveDisabled = batch.status !== "pending_review" || parentReviewContainer || activeDuplicateReview;
  const approveTitle = drainedParent
    ? "This intake container is drained. Review child batches instead."
    : parentReviewContainer
    ? "Parent containers are not move-ready. Review child batches or handle active files first."
    : activeDuplicateReview
      ? "Needs duplicate/fragment review before move approval"
      : "Approve";

  return (
    <>
      <tr
        className={`row--clickable ${selected ? "row--selected" : ""} ${drainedParent ? "row--drained-parent" : ""}`}
        onClick={() => onToggle(batch.id)}
      >
        <td onClick={(event) => event.stopPropagation()} style={{ textAlign: "center" }}>
          <input
            aria-label={`Select batch ${batch.id}`}
            type="checkbox"
            checked={selected}
            onChange={(event) => onSelect(batch.id, event.target.checked)}
          />
        </td>
        <td style={{ color: "var(--text-muted)" }}>{index}</td>
        <td><span className="media-type-label">{mediaLabel}</span></td>
        <td title={primaryName}>{primaryName}</td>
        <td title={secondaryName}>
          {secondaryName}
          {quarantineReview && (
            <small className="row-artwork">
              {batch.file_count} file(s) ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â· {batch.folder_count} folder(s)
            </small>
          )}
          {!quarantineReview && batch.artwork_count > 0 && (
            <small className="row-artwork">Artwork: {batch.artwork_count}</small>
          )}
          {!quarantineReview && batch.ignored_sidecar_count > 0 && (
            <small className="row-artwork">
              Ignored sidecars: {batch.ignored_sidecar_count}
            </small>
          )}
          {duplicateLabel && (
            <small className="row-artwork">
              {duplicateLabel}: {duplicateMatchCount} matching batches
            </small>
          )}
        </td>
        <td>{year}</td>
        <td>{itemText}</td>
        <td><span className={pillClass(batch.status)}>{batchStatusLabel(batch)}</span></td>
        <td>
          <div className="conf-bar">
            <div className="conf-bar__track">
              <div
                className="conf-bar__fill"
                style={{
                  width: `${Math.min(100, Math.max(0, percent))}%`,
                  background: confidenceColor(percent),
                }}
              />
            </div>
            <span className="conf-bar__label">{percent}%</span>
          </div>
        </td>
        <td className="batch-table__actions" onClick={(event) => event.stopPropagation()}>
          {awaitingQuarantine ? (
            <button
              className="btn btn--compact quarantine-action"
              title="Move to quarantine"
              onClick={(event) => { event.stopPropagation(); onQuarantine(batch.id); }}
            >
              <i className="ti ti-archive" /> {
                batch.name === "Unsupported loose files"
                  ? "Move group to quarantine"
                  : "Move to quarantine"
              }
            </button>
          ) : quarantined ? (
            <button
              className="btn btn--compact quarantine-restore-action"
              title="Restore to ingest"
              onClick={(event) => {
                event.stopPropagation();
                onRestoreQuarantine(batch.id);
              }}
            >
              <i className="ti ti-restore" /> Restore to ingest
            </button>
          ) : <button
            className="btn-sm"
            title={approveTitle}
            disabled={approveDisabled}
            style={{ color: "var(--accent-green)" }}
            onClick={(event) => { event.stopPropagation(); onApprove(batch.id); }}
          >
            <i className="ti ti-check" />
          </button>}
          <button
            className="btn-sm"
            title="Edit metadata"
            disabled={
              batch.status === "moved"
              || quarantineReview
              || !editKind
            }
            style={{ color: "var(--accent-blue)" }}
            onClick={(event) => { event.stopPropagation(); onEdit(batch); }}
          >
            <i className="ti ti-pencil" />
          </button>
          {canOpenWorkspace && (
            <button
              className="btn-sm"
              title={activeDuplicateReview ? "Open Duplicate / Fragment Review" : "Open Review Workspace"}
              style={{ color: "var(--accent-blue)" }}
              onClick={(event) => { event.stopPropagation(); onOpenWorkspace(batch); }}
            >
              <i className={`ti ${activeDuplicateReview ? "ti-layers-intersect" : "ti-layout-sidebar"}`} />
            </button>
          )}
          {shouldOpenEditorFromWorkspaceButton && (
            <button
              className="btn-sm"
              title="Open Metadata Editor"
              style={{ color: "var(--accent-blue)" }}
              onClick={(event) => { event.stopPropagation(); onEdit(batch); }}
            >
              <i className="ti ti-layout-sidebar" />
            </button>
          )}
          <button
            className="btn-sm"
            title="Send to recovery"
            disabled={quarantineReview}
            style={{ color: "var(--text-secondary)" }}
            onClick={(event) => { event.stopPropagation(); onRecovery(batch.id); }}
          >
            <i className="ti ti-refresh-alert" />
          </button>
          {batch.status === "moved" && batch.move_manifest && (
            <button
              className="btn-sm"
              title="View manifest"
              style={{ color: "var(--accent-blue)" }}
              onClick={(event) => {
                event.stopPropagation();
                onToggle(batch.id);
              }}
            >
              <i className="ti ti-file-description" />
            </button>
          )}
          <button
            className="btn-sm"
            title="Reject"
            style={{ color: "var(--accent-red)" }}
            onClick={(event) => { event.stopPropagation(); onReject(batch.id); }}
          >
            <i className="ti ti-x" />
          </button>
        </td>
      </tr>
      {expanded && (
        <tr>
          <td colSpan={10} style={{ padding: 0 }}>
            {detailLoading && (
              <div className="detail-state"><i className="ti ti-loader-2 spinner" /> Loading details...</div>
            )}
            {detailError && (
              <div className="detail-state detail-state--error"><i className="ti ti-wifi-off" /> {detailError}</div>
            )}
            {detail && (
              <>
                <BatchDetail batch={detail} moveSummary={moveSummary} review={review} onEditBatch={onEdit} onApproveBatch={onApprove} />
                <MoveManifestProof batch={batch} moveSummary={moveSummary} />
              </>
            )}
          </td>
        </tr>
      )}
    </>
  );
}
