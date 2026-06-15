import type { BatchSummary } from "../types/archive";

const CURRENT_METADATA_ASSIST_VERSION = "v2.065";
const CURRENT_METADATA_ASSIST_REVISION = 65;

type Props = {
  batch: BatchSummary;
};

export default function MetadataAssistStaleWarning({ batch }: Props) {
  const versionMatch = batch.metadata_assist_version?.match(/^v2\.(\d+)$/);
  const revision = versionMatch ? Number(versionMatch[1]) : null;
  if (
    batch.metadata_assist_version === CURRENT_METADATA_ASSIST_VERSION ||
    (revision !== null && revision >= CURRENT_METADATA_ASSIST_REVISION)
  ) {
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
