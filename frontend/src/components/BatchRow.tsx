import type { BatchSummary, IngestBatch } from "../types/archive";
import BatchDetail from "./BatchDetail";

type Props = {
  batch: BatchSummary;
  detail?: IngestBatch;
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
  onEdit: (batch: BatchSummary) => void;
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

export default function BatchRow({
  batch,
  detail,
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
  onEdit,
}: Props) {
  const artist = batch.artist ?? "-";
  const album = batch.album ?? "-";
  const year = batch.year ?? "-";
  const tracks = batch.track_count || "-";
  const percent = Math.round((batch.confidence ?? 0) * 100);

  return (
    <>
      <tr
        className={`row--clickable ${selected ? "row--selected" : ""}`}
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
        <td title={artist}>{artist}</td>
        <td title={album}>{album}</td>
        <td>{year}</td>
        <td style={{ textAlign: "center" }}>{tracks}</td>
        <td><span className={pillClass(batch.status)}>{statusLabel(batch.status)}</span></td>
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
        <td onClick={(event) => event.stopPropagation()}>
          <button
            className="btn-sm"
            title="Approve"
            disabled={batch.status !== "pending_review"}
            style={{ color: "var(--accent-green)" }}
            onClick={(event) => { event.stopPropagation(); onApprove(batch.id); }}
          >
            <i className="ti ti-check" />
          </button>
          <button
            className="btn-sm"
            title="Edit metadata"
            disabled={batch.status === "moved"}
            style={{ color: "var(--accent-blue)" }}
            onClick={(event) => { event.stopPropagation(); onEdit(batch); }}
          >
            <i className="ti ti-pencil" />
          </button>
          <button
            className="btn-sm"
            title="Send to recovery"
            style={{ color: "var(--text-secondary)" }}
            onClick={(event) => { event.stopPropagation(); onRecovery(batch.id); }}
          >
            <i className="ti ti-refresh-alert" />
          </button>
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
          <td colSpan={9} style={{ padding: 0 }}>
            {detailLoading && (
              <div className="detail-state"><i className="ti ti-loader-2 spinner" /> Loading details...</div>
            )}
            {detailError && (
              <div className="detail-state detail-state--error"><i className="ti ti-wifi-off" /> {detailError}</div>
            )}
            {detail && <BatchDetail batch={detail} />}
          </td>
        </tr>
      )}
    </>
  );
}
