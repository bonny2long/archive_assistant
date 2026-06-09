import type { LibrarySummary as LibrarySummaryData } from "../types/archive";

type Props = {
  summary: LibrarySummaryData;
};

export default function LibrarySummary({ summary }: Props) {
  return (
    <div className="library-summary" aria-label="Library summary">
      <i className="ti ti-library" />
      <span>Library summary:</span>
      <strong>{summary.moved_batches} batches moved</strong>
      <span>·</span>
      <strong>{summary.moved_files} files</strong>
      <span>·</span>
      <strong className={summary.failed_moves ? "library-summary__warning" : ""}>
        {summary.failed_moves} failed moves
      </strong>
      {summary.approved_waiting > 0 && (
        <span className="library-summary__pending">{summary.approved_waiting} waiting to move</span>
      )}
      {summary.needs_metadata > 0 && (
        <span className="library-summary__pending">{summary.needs_metadata} need metadata</span>
      )}
    </div>
  );
}
