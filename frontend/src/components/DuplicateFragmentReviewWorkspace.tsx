import type { DuplicateFragmentBatch, DuplicateFragmentCluster, DuplicateFragmentReview, IngestBatch } from "../types/archive";
import { useEffect, useMemo, useState } from "react";
import { api } from "../api/client";

type Props = {
  review: DuplicateFragmentReview;
  selectedBatchId: number;
  onClose: () => void;
};

function reviewTypeLabel(value: string): string {
  const labels: Record<string, string> = {
    possible_fragment: "Possible fragment",
    possible_duplicate: "Possible duplicate",
    possible_edition_conflict: "Edition conflict",
    reviewed_keep_separate: "Reviewed - keep separate",
  };
  return labels[value] ?? value.replace(/_/g, " ");
}

function mediaLabel(value: string): string {
  const labels: Record<string, string> = {
    music_album: "Music",
    music_discography: "Discography",
    audiobook: "Audiobook",
    ebook: "Ebook",
    comic: "Comic",
    video_movie: "Movie",
    video_tv_show: "TV",
    artwork: "Artwork",
    unknown: "Unknown",
  };
  return labels[value] ?? value.replace(/_/g, " ");
}

function statusLabel(value: string): string {
  return value.replace(/_/g, " ");
}

function itemLabel(count: number): string {
  return `Items: ${count}`;
}

function fileLabel(count: number | undefined): string {
  return `Files: ${count ?? 0}`;
}

function identityLabel(cluster: DuplicateFragmentCluster | null): string {
  const first = cluster?.batches[0];
  if (!first) return "No matching batches";
  const creator = first.creator?.trim();
  const title = first.title?.trim();
  if (creator && title) return `${creator} \u2014 ${title}`;
  return title || creator || `Batch ${first.batch_id}`;
}

function clusterSubtitle(cluster: DuplicateFragmentCluster | null): string {
  if (!cluster) return "No active cluster";
  return [
    reviewTypeLabel(cluster.review_type),
    `${cluster.batches.length} matching batches`,
    mediaLabel(cluster.media_type),
  ].join(" \u00b7 ");
}

function selectedCluster(review: DuplicateFragmentReview, selectedBatchId: number): DuplicateFragmentCluster | null {
  return review.clusters.find((cluster) => cluster.batches.some((batch) => batch.batch_id === selectedBatchId))
    ?? review.clusters[0]
    ?? null;
}

function batchSubtitle(batch: DuplicateFragmentBatch): string {
  const parts = [batch.creator, batch.year, mediaLabel(batch.detected_type)].filter(Boolean);
  return parts.join(" | ");
}

function displayFileCount(batch: DuplicateFragmentBatch, detail: IngestBatch | null): number {
  const detailCount = detail?.id === batch.batch_id ? detail.files.length : 0;
  if ((batch.file_count ?? 0) > 0) return batch.file_count ?? 0;
  return detailCount;
}

export default function DuplicateFragmentReviewWorkspace({ review, selectedBatchId, onClose }: Props) {
  const cluster = useMemo(() => selectedCluster(review, selectedBatchId), [review, selectedBatchId]);
  const [activeBatchId, setActiveBatchId] = useState<number | null>(selectedBatchId);
  const [detail, setDetail] = useState<IngestBatch | null>(null);
  const [loadingDetail, setLoadingDetail] = useState(false);
  const [detailError, setDetailError] = useState<string | null>(null);
  const [showTech, setShowTech] = useState(false);

  useEffect(() => {
    if (!cluster?.batches.length) {
      setActiveBatchId(null);
      return;
    }
    if (!cluster.batches.some((batch) => batch.batch_id === activeBatchId)) {
      setActiveBatchId(cluster.batches[0].batch_id);
    }
  }, [cluster, activeBatchId]);

  const selected = cluster?.batches.find((batch) => batch.batch_id === activeBatchId) ?? cluster?.batches[0] ?? null;

  useEffect(() => {
    if (!selected) {
      setDetail(null);
      return;
    }
    let cancelled = false;
    setLoadingDetail(true);
    setDetailError(null);
    void api.getBatch(selected.batch_id)
      .then((batch) => {
        if (!cancelled) setDetail(batch);
      })
      .catch((error: unknown) => {
        if (!cancelled) {
          setDetail(null);
          setDetailError(error instanceof Error ? error.message : "Unable to load batch details");
        }
      })
      .finally(() => {
        if (!cancelled) setLoadingDetail(false);
      });
    return () => {
      cancelled = true;
    };
  }, [selected]);

  const destination = selected?.suggested_destination ?? detail?.suggested_destination ?? null;
  const files = detail?.files ?? [];
  const selectedFileCount = selected ? displayFileCount(selected, detail) : 0;

  return (
    <div className="review-workspace duplicate-review-workspace" role="dialog" aria-modal="true" aria-label="Duplicate Fragment Review">
      <header className="review-workspace__header duplicate-review-workspace__header">
        <div>
          <span className="review-workspace__eyebrow">Duplicate / Fragment Review</span>
          <h2>{identityLabel(cluster)}</h2>
          <div className="duplicate-review-workspace__subtitle">{clusterSubtitle(cluster)}</div>
          {cluster?.reason && <p className="duplicate-review-workspace__reason">{cluster.reason}</p>}
        </div>
        <button className="btn-sm" onClick={onClose} aria-label="Close duplicate review workspace">
          <i className="ti ti-x" />
        </button>
      </header>

      <div className="duplicate-review-workspace__body">
        <section className="duplicate-review-workspace__main" aria-label="Matching batches">
          <div className="duplicate-review-workspace__notice">
            <i className="ti ti-alert-triangle" />
            <span>Resolution actions are coming next. This group is blocked from move approval until it is resolved.</span>
          </div>

          <div className="duplicate-review-workspace__batch-list">
            {cluster?.batches.map((batch) => {
              const isSelected = batch.batch_id === selected?.batch_id;
              const fileCount = isSelected ? displayFileCount(batch, detail) : batch.file_count;
              return (
                <button
                  key={batch.batch_id}
                  className={`duplicate-review-card ${isSelected ? "is-active" : ""}`}
                  type="button"
                  onClick={() => setActiveBatchId(batch.batch_id)}
                >
                  <div className="duplicate-review-card__topline">
                    <span>{reviewTypeLabel(cluster.review_type)}</span>
                    <small>{statusLabel(batch.status)}</small>
                  </div>
                  <strong>{batch.title || `Batch ${batch.batch_id}`}</strong>
                  <small>{batchSubtitle(batch) || `Batch ${batch.batch_id}`}</small>
                  <div className="duplicate-review-card__facts">
                    <span>{itemLabel(batch.item_count)}</span>
                    <span>{fileLabel(fileCount)}</span>
                    <span>{batch.year ?? "No year"}</span>
                  </div>
                  <dl>
                    <div>
                      <dt>Destination preview</dt>
                      <dd title={batch.suggested_destination ?? undefined}>{batch.suggested_destination ?? "No destination preview"}</dd>
                    </div>
                    <div>
                      <dt>Source folder</dt>
                      <dd title={batch.source_path ?? undefined}>{batch.source_path ?? "Unknown source"}</dd>
                    </div>
                  </dl>
                </button>
              );
            })}
          </div>
        </section>

        <aside className="duplicate-review-workspace__inspector" aria-label="Selected batch details">
          {selected ? (
            <>
              <section className="workspace-inspector__section">
                <h3>Selected batch</h3>
                <strong>{selected.title || `Batch ${selected.batch_id}`}</strong>
                <small>{batchSubtitle(selected) || statusLabel(selected.status)}</small>
                <div className="duplicate-review-workspace__chips">
                  <span>{itemLabel(selected.item_count)}</span>
                  <span>{fileLabel(selectedFileCount)}</span>
                  <span>Status: {statusLabel(selected.status)}</span>
                </div>
              </section>

              <section className="workspace-inspector__section">
                <h3>Destination preview</h3>
                {destination ? <code title={destination}>{destination}</code> : <small>No destination preview available.</small>}
              </section>

              <section className="workspace-inspector__section">
                <h3>Source folder</h3>
                {selected.source_path ? <code title={selected.source_path}>{selected.source_path}</code> : <small>Unknown source folder.</small>}
              </section>

              <section className="workspace-inspector__section duplicate-review-workspace__decision-section">
                <h3>Group decision</h3>
                <p>Resolution actions are coming next. This group is blocked from move approval until it is resolved.</p>
                <div className="duplicate-review-workspace__decision-grid">
                  <button className="btn-sm" disabled><i className="ti ti-copy-check" /> Keep separate</button>
                  <button className="btn-sm" disabled><i className="ti ti-git-merge" /> Merge into one batch</button>
                  <button className="btn-sm" disabled><i className="ti ti-layers-subtract" /> Mark duplicate</button>
                  <button className="btn-sm" disabled><i className="ti ti-clock" /> Review later</button>
                  <button className="btn-sm" disabled><i className="ti ti-lock" /> Block move</button>
                </div>
              </section>

              <section className="workspace-inspector__section">
                <h3>Files</h3>
                {loadingDetail && <small><i className="ti ti-loader-2 spinner" /> Loading files...</small>}
                {detailError && <small className="error-text">{detailError}</small>}
                {!loadingDetail && !detailError && (
                  <div className="workspace-inspector__files">
                    {files.slice(0, 16).map((file) => (
                      <div key={file.id}>
                        <strong>{file.file_name}</strong>
                        <small>{file.detected_role} | {file.extension} | {Math.round(file.size_bytes / 1024)} KB</small>
                      </div>
                    ))}
                    {files.length === 0 && <small>No files loaded for this batch.</small>}
                    {files.length > 16 && <small className="workspace-inspector__files-more">{files.length - 16} more file(s)</small>}
                  </div>
                )}
              </section>

              <section className="workspace-inspector__section">
                <button className="btn-sm" onClick={() => setShowTech((value) => !value)}>
                  <i className="ti ti-code" /> {showTech ? "Hide" : "Show"} technical details
                </button>
                {showTech && (
                  <pre className="duplicate-review-workspace__technical">
                    {JSON.stringify({ cluster, selectedBatch: detail ?? selected }, null, 2)}
                  </pre>
                )}
              </section>
            </>
          ) : (
            <section className="workspace-inspector__section">
              <h3>No batch selected</h3>
              <small>This duplicate/fragment review did not return matching batches.</small>
            </section>
          )}
        </aside>
      </div>
    </div>
  );
}
