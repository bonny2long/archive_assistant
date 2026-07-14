type ActionKey = "refresh" | "scan" | "move" | "reset";

type Props = {
  onScan: () => Promise<void>;
  onMove: () => Promise<void>;
  onRefresh: () => Promise<void>;
  onReset: () => Promise<void>;
  loadingAction: ActionKey | null;
  devToolsEnabled: boolean;
  serverTime?: string | null;
  ingestPath?: string | null;
  isScanningIngest?: boolean;
};

export default function ActionBar({
  onScan,
  onMove,
  onRefresh,
  onReset,
  loadingAction,
  devToolsEnabled,
  serverTime,
  ingestPath,
  isScanningIngest = false,
}: Props) {
  const disabled = loadingAction !== null;
  const scanDisabled = disabled || isScanningIngest;

  return (
    <div className="action-bar">
      <div>
        <div className="action-bar__title">Archive Assistant</div>
        <div className="action-bar__subtitle">Archive ingest dashboard</div>
        <div className="action-bar__system-path">
          {isScanningIngest ? "Scanning ingest" : "Ingest path"}: {ingestPath || "unknown - check backend"}
        </div>
        {devToolsEnabled && serverTime && (
          <div className="action-bar__system-time">{serverTime}</div>
        )}
      </div>
      <div className="action-bar__buttons">
        <button className="btn" disabled={disabled} onClick={() => void onRefresh()}>
          <i className={`ti ti-refresh ${loadingAction === "refresh" ? "spinner" : ""}`} /> Refresh
        </button>
        <button className="btn" disabled={scanDisabled} onClick={() => void onScan()}>
          <i className={`ti ti-scan ${loadingAction === "scan" || isScanningIngest ? "spinner" : ""}`} /> {isScanningIngest ? "Scanning ingest" : "Scan ingest"}
        </button>
        <button className="btn btn--green" disabled={disabled} onClick={() => void onMove()}>
          <i className={`ti ti-circle-arrow-right ${loadingAction === "move" ? "spinner" : ""}`} /> Move all approved
        </button>
        {devToolsEnabled && (
          <button
            className="btn btn--warning"
            disabled={disabled}
            title="Reset preserves media files. Media moved out of active test folders will be placed in _RECOVERY."
            onClick={() => void onReset()}
          >
            <i className={`ti ti-restore ${loadingAction === "reset" ? "spinner" : ""}`} /> Reset test data
          </button>
        )}
      </div>
    </div>
  );
}
