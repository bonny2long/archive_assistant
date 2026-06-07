type ActionKey = "refresh" | "scan" | "move";

type Props = {
  onScan: () => Promise<void>;
  onMove: () => Promise<void>;
  onRefresh: () => Promise<void>;
  loadingAction: ActionKey | null;
};

export default function ActionBar({ onScan, onMove, onRefresh, loadingAction }: Props) {
  const disabled = loadingAction !== null;

  return (
    <div className="action-bar">
      <div>
        <div className="action-bar__title">Archive Assistant</div>
        <div className="action-bar__subtitle">Music ingest dashboard</div>
      </div>
      <div className="action-bar__buttons">
        <button className="btn" disabled={disabled} onClick={() => void onRefresh()}>
          <i className={`ti ti-refresh ${loadingAction === "refresh" ? "spinner" : ""}`} /> Refresh
        </button>
        <button className="btn" disabled={disabled} onClick={() => void onScan()}>
          <i className={`ti ti-scan ${loadingAction === "scan" ? "spinner" : ""}`} /> Scan music
        </button>
        <button className="btn btn--green" disabled={disabled} onClick={() => void onMove()}>
          <i className={`ti ti-circle-arrow-right ${loadingAction === "move" ? "spinner" : ""}`} /> Move approved
        </button>
      </div>
    </div>
  );
}
