import type { WorkspaceFilter } from "../types/archive";
import type { CandidateViewModel } from "./ReviewWorkspace";

type Props = {
  filter: WorkspaceFilter;
  candidates: CandidateViewModel[];
  qualityIssueCount: number;
  showTech: boolean;
  onFilterChange: (filter: WorkspaceFilter) => void;
  onToggleTech: () => void;
};

const FILTERS: Array<{ key: WorkspaceFilter; label: string }> = [
  { key: "all", label: "All" },
  { key: "blocked", label: "Blocked" },
  { key: "review", label: "Needs review" },
  { key: "safe", label: "Safe" },
  { key: "music", label: "Music" },
  { key: "audiobook", label: "Audiobook" },
  { key: "ebook", label: "Ebook" },
  { key: "comic", label: "Comic" },
  { key: "movie", label: "Movie" },
  { key: "tv", label: "TV" },
  { key: "artwork", label: "Artwork" },
  { key: "unknown", label: "Unknown" },
];

function countFor(filter: WorkspaceFilter, candidates: CandidateViewModel[]): number {
  if (filter === "all") return candidates.length;
  if (filter === "safe") {
    return candidates.filter((candidate) => candidate.displayState === "safe" || candidate.displayState === "approved").length;
  }
  if (["blocked", "review"].includes(filter)) {
    return candidates.filter((candidate) => candidate.displayState === filter).length;
  }
  return candidates.filter((candidate) => candidate.mediaType === filter).length;
}

export default function WorkspaceLeftRail({
  filter,
  candidates,
  qualityIssueCount,
  showTech,
  onFilterChange,
  onToggleTech,
}: Props) {
  return (
    <aside className="review-workspace__rail" aria-label="Workspace filters">
      <div className="review-workspace__rail-header">
        <strong>Queue</strong>
        {qualityIssueCount > 0 && <span>{qualityIssueCount} quality issue(s)</span>}
      </div>
      <div className="review-workspace__filters">
        {FILTERS.map((item) => (
          <button
            key={item.key}
            className={item.key === filter ? "is-active" : ""}
            onClick={() => onFilterChange(item.key)}
          >
            <span>{item.label}</span>
            <small>{countFor(item.key, candidates)}</small>
          </button>
        ))}
      </div>
      <button className="btn btn--compact review-workspace__tech-toggle" onClick={onToggleTech}>
        <i className="ti ti-code" /> {showTech ? "Hide technical" : "Technical"}
      </button>
    </aside>
  );
}
