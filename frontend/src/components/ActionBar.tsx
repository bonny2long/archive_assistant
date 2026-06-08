type ActionKey = "refresh" | "scan" | "move" | "reset";

type Props = {
  onScan: () => Promise<void>;
  onMove: () => Promise<void>;
  onRefresh: () => Promise<void>;
  onReset: () => Promise<void>;
  loadingAction: ActionKey | null;
  devToolsEnabled: boolean;
};

export default function ActionBar({
  onScan,
  onMove,
  onRefresh,
  onReset,
  loadingAction,
  devToolsEnabled,
}: Props) {
  const disabled = loadingAction !== null;

  return (
    <div className="action-bar">
      <div>
        <div className="action-bar__title">Archive Assistant</div>
        <div className="action-bar__subtitle">Archive ingest dashboard</div>
      </div>
      <div className="action-bar__buttons">
        <button className="btn" disabled={disabled} onClick={() => void onRefresh()}>
          <i className={`ti ti-refresh ${loadingAction === "refresh" ? "spinner" : ""}`} /> Refresh
        </button>
        <button className="btn" disabled={disabled} onClick={() => void onScan()}>
          <i className={`ti ti-scan ${loadingAction === "scan" ? "spinner" : ""}`} /> Scan ingest
        </button>
        <button className="btn btn--green" disabled={disabled} onClick={() => void onMove()}>
          <i className={`ti ti-circle-arrow-right ${loadingAction === "move" ? "spinner" : ""}`} /> Move approved
        </button>
        {devToolsEnabled && (
          <button className="btn btn--warning" disabled={disabled} onClick={() => void onReset()}>
            <i className={`ti ti-restore ${loadingAction === "reset" ? "spinner" : ""}`} /> Reset test data
          </button>
        )}
      </div>
    </div>
  );
}
