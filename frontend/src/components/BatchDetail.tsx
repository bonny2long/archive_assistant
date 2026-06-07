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

const WARNING_LABELS: Record<string, string> = {
  artist_missing: "Artist missing",
  album_missing: "Album missing",
  year_missing: "Year missing",
  year_invalid: "Year invalid",
  genre_missing: "Genre missing",
  raw_folder_name_detected: "Raw folder name detected",
  partial_duplicate_tracks_detected: "Partial duplicate tracks detected",
  compilation_suspected: "Compilation suspected",
  mixed_embedded_metadata_detected: "Mixed embedded metadata detected",
  track_album_mismatch_detected: "Some track album tags differ from the release folder",
  track_artist_mismatch_detected: "Some track artist tags differ from the release folder",
  release_folder_grouping_used: "Release folder grouping used",
  possible_duplicate_destination: "Possible duplicate destination",
  possible_artist_alias: "Possible artist alias",
  manual_duplicate_batch_merge_performed: "Manual duplicate batch merge performed",
  possible_artist_alias_resolved: "Artist alias resolved",
  possible_archived_duplicate_candidate: "Matching release already archived",
  destination_file_conflict: "Destination filename conflict",
};

function metadataWarnings(batch: IngestBatch): string[] {
  const warnings = batch.metadata_json?.metadata_warnings;
  return Array.isArray(warnings)
    ? warnings.filter((warning): warning is string => typeof warning === "string")
    : [];
}

function metadataAlertMessages(batch: IngestBatch): string[] {
  const alerts = batch.metadata_json?.metadata_alerts;
  if (!Array.isArray(alerts)) return [];
  return alerts
    .map((alert) => {
      if (
        alert
        && typeof alert === "object"
        && "message" in alert
        && typeof alert.message === "string"
      ) {
        return alert.message;
      }
      return null;
    })
    .filter((message): message is string => Boolean(message));
}

function warningLabel(warning: string): string {
  return WARNING_LABELS[warning]
    ?? warning.replace(/_/g, " ").replace(/^\w/, (value: string) => value.toUpperCase());
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
  const metadataWarningValues = metadataWarnings(batch);
  const metadataAlerts = metadataAlertMessages(batch);

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

      {metadataWarningValues.length > 0 && (
        <section className="metadata-warnings" aria-label="Metadata warnings">
          <div className="metadata-warnings__list">
            {metadataWarningValues.map((warning) => (
              <span key={warning}><i className="ti ti-alert-triangle" />{warningLabel(warning)}</span>
            ))}
          </div>
        </section>
      )}
      {metadataAlerts.length > 0 && (
        <section className="metadata-alerts" aria-label="Metadata alerts">
          {metadataAlerts.map((message) => (
            <div key={message}><i className="ti ti-info-circle" />{message}</div>
          ))}
        </section>
      )}

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

  const warnings = metadataWarnings(batch);
  const alerts = metadataAlertMessages(batch);

  return (
    <div className="batch-detail">
      <div className="batch-detail__grid">
        <div>
          <div className="batch-detail__label">Artist</div>
          <div className="batch-detail__value">{metadataValue(batch, "artist")}</div>
        </div>
        <div>
          <div className="batch-detail__label">Album</div>
          <div className="batch-detail__value">{metadataValue(batch, "album")}</div>
        </div>
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
      {warnings.length > 0 && (
        <section className="metadata-warnings" aria-label="Metadata warnings">
          <div className="batch-detail__label">Metadata warnings</div>
          <div className="metadata-warnings__list">
            {warnings.map((warning) => (
              <span key={warning}><i className="ti ti-alert-triangle" />{warningLabel(warning)}</span>
            ))}
          </div>
        </section>
      )}
      {alerts.length > 0 && (
        <section className="metadata-alerts" aria-label="Metadata alerts">
          {alerts.map((message) => (
            <div key={message}><i className="ti ti-info-circle" />{message}</div>
          ))}
        </section>
      )}
      <DebugDetails batch={batch} moveSummary={moveSummary} />
    </div>
  );
}
