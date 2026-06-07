import { useState } from "react";
import type { IngestBatch } from "../types/archive";

type Props = { batch: IngestBatch };

export default function BatchDetail({ batch }: Props) {
  const [showJson, setShowJson] = useState(false);

  return (
    <div className="batch-detail">
      <div className="batch-detail__grid">
        <div>
          <div className="batch-detail__label">Source path</div>
          <div className="batch-detail__value">{batch.source_path}</div>
        </div>
        <div>
          <div className="batch-detail__label">Suggested destination</div>
          <div className="batch-detail__value">{batch.suggested_destination ?? "-"}</div>
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
          <div className="batch-detail__value">{new Date(batch.created_at).toLocaleString()}</div>
        </div>
        <div>
          <div className="batch-detail__label">Approved at</div>
          <div className="batch-detail__value">
            {batch.approved_at ? new Date(batch.approved_at).toLocaleString() : "-"}
          </div>
        </div>
      </div>
      <button className="btn btn--compact" onClick={() => setShowJson((value) => !value)}>
        <i className={`ti ti-${showJson ? "eye-off" : "code"}`} />
        {showJson ? "Hide debug JSON" : "Show debug JSON"}
      </button>
      {showJson && <pre className="batch-detail__debug">{JSON.stringify(batch, null, 2)}</pre>}
    </div>
  );
}
