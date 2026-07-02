import type { CandidateViewModel } from "./ReviewWorkspace";

type Props = {
  candidate: CandidateViewModel;
  selected: boolean;
  onSelect: () => void;
};

function stateIcon(state: CandidateViewModel["displayState"]): string {
  if (state === "blocked") return "ti-ban";
  if (state === "review") return "ti-alert-triangle";
  if (state === "approved") return "ti-circle-check";
  return "ti-shield-check";
}

export default function WorkspaceCandidateCard({ candidate, selected, onSelect }: Props) {
  const compact = candidate.displayState === "safe" || candidate.displayState === "approved";
  return (
    <button
      className={`workspace-candidate workspace-candidate--${candidate.displayState} ${selected ? "is-selected" : ""}`}
      onClick={onSelect}
    >
      <div className="workspace-candidate__top">
        <span className="workspace-candidate__state"><i className={`ti ${stateIcon(candidate.displayState)}`} /> {candidate.displayState}</span>
        <span>{candidate.mediaType}</span>
      </div>
      <strong>{candidate.title}</strong>
      <small>{candidate.creator} | {candidate.year}</small>
      {!compact && (
        <p>{candidate.recommendedAction}</p>
      )}
      <div className="workspace-candidate__meta">
        <span>{candidate.fileCount} files</span>
        <span>{candidate.sourceFragmentCount} fragments</span>
        <span>{candidate.confidenceLabel}</span>
        {candidate.warningCount > 0 && <span>{candidate.warningCount} warnings</span>}
        {candidate.activeActions.length > 0 && <span>{candidate.activeActions.length} actions</span>}
      </div>
      {candidate.hasChunkIdentityRisk && (
        <div className="workspace-candidate__risk"><i className="ti ti-layers-intersect" /> Chunk identity risk</div>
      )}
    </button>
  );
}
