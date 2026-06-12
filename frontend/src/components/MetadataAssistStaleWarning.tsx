import type { BatchSummary } from "../types/archive";

const CURRENT_METADATA_ASSIST_VERSION = "v2.056";

type Props = {
  batch: BatchSummary;
};

export default function MetadataAssistStaleWarning({ batch }: Props) {
  if (batch.metadata_assist_version === CURRENT_METADATA_ASSIST_VERSION) {
    return null;
  }

  return (
    <div className="metadata-assist-stale-warning">
      <i className="ti ti-refresh-alert" />
      <div>
        <strong>Metadata suggestions may be stale</strong>
        <span>
          Suggestions were built by an older metadata parser. Reset/rescan this
          test batch to refresh them.
        </span>
      </div>
    </div>
  );
}
