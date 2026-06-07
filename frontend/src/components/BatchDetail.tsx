import { useState } from "react";
import type { BatchMoveSummary, IngestBatch } from "../types/archive";

type Props = {
  batch: IngestBatch;
  moveSummary?: BatchMoveSummary;
};

function formatDate(value?: string | null): string {
  return value ? new Date(value).toLocaleString() : "-";
}

function metadataValue(batch: IngestBatch, key: string): string {
  const value = batch.metadata_json?.[key];
  return value === null || value === undefined || value === "" ? "-" : String(value);
}

function readableLibraryPath(value?: string | null): string {
  if (!value) return "-";
  const normalized = value.replace(/\\/g, "/");
  const libraryIndex = normalized.toLowerCase().indexOf("music/library/");
  return libraryIndex >= 0 ? normalized.slice(libraryIndex) : normalized;
}

function DebugDetails({ batch, moveSummary }: Props) {
  const [showJson, setShowJson] = useState(false);

  return (
    <div className="batch-debug">
      <button className="btn btn--compact" onClick={() => setShowJson((value) => !value)}>
        <i className={`ti ti-${showJson ? "eye-off" : "code"}`} />
        {showJson ? "Hide debug JSON" : "Show debug JSON"}
      </button>
      {showJson && (
        <div className="batch-debug__content">
          <div>
            <div className="batch-detail__label">Source path</div>
            <div className="batch-detail__value batch-detail__path">{batch.source_path}</div>
          </div>
          <pre className="batch-detail__debug">
            {JSON.stringify({ batch, move_summary: moveSummary }, null, 2)}
          </pre>
        </div>
      )}
    </div>
  );
}

function MovedBatchDetail({ batch, moveSummary }: Props) {
  const completedDates = moveSummary?.moves
    .filter((move) => move.completed_at)
    .map((move) => move.completed_at as string)
    .sort() ?? [];
  const latestCompleted = completedDates[completedDates.length - 1];
  const warnings = moveSummary?.moves.filter(
    (move) => move.status !== "completed" || move.error_message,
  ) ?? [];

  return (
    <div className="batch-detail batch-detail--moved">
      <div className="library-status">
        <div className="library-status__icon"><i className="ti ti-circle-check" /></div>
        <div>
          <div className="library-status__eyebrow">Library status</div>
          <h2>Moved successfully</h2>
          <p>{metadataValue(batch, "artist")} · {metadataValue(batch, "album")}</p>
        </div>
        <div className="library-status__facts">
          <span>{Math.round(batch.confidence * 100)}% confidence</span>
          <span>{batch.metadata_confirmed ? "Metadata confirmed" : "Detected metadata"}</span>
        </div>
      </div>

      <div className="library-detail__grid">
        <section className="library-card">
          <h3>Album</h3>
          <dl className="library-fields">
            <div><dt>Artist</dt><dd>{metadataValue(batch, "artist")}</dd></div>
            <div><dt>Album</dt><dd>{metadataValue(batch, "album")}</dd></div>
            <div><dt>Year</dt><dd>{metadataValue(batch, "year")}</dd></div>
            <div><dt>Genre</dt><dd>{metadataValue(batch, "genre")}</dd></div>
            <div><dt>Format</dt><dd>{metadataValue(batch, "format")}</dd></div>
            <div><dt>Tracks</dt><dd>{moveSummary?.total ?? batch.files.length}</dd></div>
          </dl>
        </section>

        <section className="library-card">
          <h3>Timeline</h3>
          <dl className="library-fields">
            <div><dt>Created</dt><dd>{formatDate(batch.created_at)}</dd></div>
            <div><dt>Approved</dt><dd>{formatDate(batch.approved_at)}</dd></div>
            <div><dt>Moved</dt><dd>{formatDate(latestCompleted)}</dd></div>
          </dl>
        </section>
      </div>

      <section className="library-destination">
        <span>Final destination</span>
        <strong>{readableLibraryPath(batch.suggested_destination)}</strong>
      </section>

      <section className="move-log">
        <div className="move-log__header">
          <div>
            <h3>Move log</h3>
            <p>{moveSummary?.completed ?? 0} completed, {moveSummary?.failed ?? 0} failed</p>
          </div>
          <span className={`move-log__summary ${warnings.length ? "move-log__summary--warning" : ""}`}>
            {warnings.length ? `${warnings.length} warning(s)` : "All files completed"}
          </span>
        </div>
        {moveSummary?.moves.length ? (
          <div className="move-file-list">
            {moveSummary.moves.map((move) => (
              <div className="move-file" key={move.id}>
                <i className={`ti ti-${move.status === "completed" ? "check" : "alert-triangle"}`} />
                <span title={move.destination_path}>{move.file_name ?? "Unknown file"}</span>
                <span className={`move-file__status move-file__status--${move.status}`}>
                  {move.status}
                </span>
                {move.error_message && <small>{move.error_message}</small>}
              </div>
            ))}
          </div>
        ) : (
          <div className="move-log__empty">No move actions were recorded for this batch.</div>
        )}
      </section>

      <DebugDetails batch={batch} moveSummary={moveSummary} />
    </div>
  );
}

export default function BatchDetail({ batch, moveSummary }: Props) {
  if (batch.status === "moved") {
    return <MovedBatchDetail batch={batch} moveSummary={moveSummary} />;
  }

  return (
    <div className="batch-detail">
      <div className="batch-detail__grid">
        <div>
          <div className="batch-detail__label">Source path</div>
          <div className="batch-detail__value batch-detail__path">{batch.source_path}</div>
        </div>
        <div>
          <div className="batch-detail__label">Suggested destination</div>
          <div className="batch-detail__value batch-detail__path">{batch.suggested_destination ?? "-"}</div>
        </div>
        <div>
          <div className="batch-detail__label">Detected type</div>
          <div className="batch-detail__value">{batch.detected_type}</div>
        </div>
        <div>
          <div className="batch-detail__label">Source kind</div>
          <div className="batch-detail__value">{batch.source_kind}</div>
        </div>
        <div>
          <div className="batch-detail__label">Created at</div>
          <div className="batch-detail__value">{formatDate(batch.created_at)}</div>
        </div>
        <div>
          <div className="batch-detail__label">Approved at</div>
          <div className="batch-detail__value">{formatDate(batch.approved_at)}</div>
        </div>
      </div>
      <DebugDetails batch={batch} moveSummary={moveSummary} />
    </div>
  );
}
