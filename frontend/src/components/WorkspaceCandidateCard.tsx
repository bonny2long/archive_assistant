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

function stateLabel(candidate: CandidateViewModel): string {
  if (hasAppliedAction(candidate, "approve_candidate") || hasAppliedAction(candidate, "split_candidate")) return "Child batch created";
  if (hasAction(candidate, "exclude_from_move_plan")) return "Excluded";
  if (hasAction(candidate, "block_candidate")) return "Blocked";
  if (hasAction(candidate, "mark_review_later")) return "Review later";
  if (hasAction(candidate, "approve_candidate")) return "Ready to extract";
  if (candidate.displayState === "blocked") return "Blocked";
  if (candidate.hasChunkIdentityRisk) return "Identity review";
  if (candidate.displayState === "review") return "Needs review";
  return "Safe";
}

function mediaTypeLabel(mediaType: string): string {
  const labels: Record<string, string> = {
    music: "Music",
    audiobook: "Audiobook",
    ebook: "Ebook",
    comic: "Comic",
    movie: "Movie",
    tv: "TV",
    artwork: "Artwork",
    unknown: "Unknown",
  };
  return labels[mediaType] ?? mediaType;
}

function plural(count: number, singular: string, pluralLabel = `${singular}s`): string {
  return `${count} ${count === 1 ? singular : pluralLabel}`;
}

function hasAction(candidate: CandidateViewModel, actionType: string): boolean {
  return candidate.activeActions.some((action) => action.action_type === actionType);
}

function hasAppliedAction(candidate: CandidateViewModel, actionType: string): boolean {
  return candidate.activeActions.some((action) => action.action_type === actionType && action.decision_status === "applied");
}

function actionSummary(candidate: CandidateViewModel): string | null {
  if (hasAppliedAction(candidate, "approve_candidate") || hasAppliedAction(candidate, "split_candidate")) return "Child batch created";
  if (hasAction(candidate, "exclude_from_move_plan")) return "Excluded from move plan";
  if (hasAction(candidate, "approve_candidate")) return "Will create child batch";
  if (hasAction(candidate, "split_candidate")) return "Approve first";
  if (hasAction(candidate, "mark_review_later")) return "Review later";
  if (hasAction(candidate, "block_candidate")) return "Blocked by user";
  if (candidate.activeActions.length > 0) return plural(candidate.activeActions.length, "decision");
  return null;
}

export default function WorkspaceCandidateCard({ candidate, selected, onSelect }: Props) {
  const compact = candidate.displayState === "safe" || candidate.displayState === "approved";
  const summary = actionSummary(candidate);
  return (
    <button
      className={`workspace-candidate workspace-candidate--${candidate.displayState} ${selected ? "is-selected" : ""}`}
      onClick={onSelect}
    >
      <div className="workspace-candidate__top">
        <span className="workspace-candidate__state"><i className={`ti ${stateIcon(candidate.displayState)}`} /> {stateLabel(candidate)}</span>
        <span>{mediaTypeLabel(candidate.mediaType)}</span>
      </div>
      <strong>{candidate.title}</strong>
      <small>{candidate.creator} | {candidate.year}</small>
      {!compact && (
        <p>{candidate.recommendedAction}</p>
      )}
      <div className="workspace-candidate__meta">
        <span>{plural(candidate.fileCount, "file")}</span>
        {candidate.mediaType === "audiobook" && <span>{plural(candidate.primaryFileCount, "audio file")}</span>}
        {candidate.mediaType === "audiobook" && candidate.supportFileCount > 0 && <span>{plural(candidate.supportFileCount, "support file")}</span>}
        {candidate.mediaType === "audiobook" && candidate.discCount > 0 && <span>{plural(candidate.discCount, "disc")}</span>}
        {candidate.sourceFragmentCount > 0 && <span>{plural(candidate.sourceFragmentCount, "source fragment")}</span>}
        <span>{candidate.confidenceLabel}</span>
        {candidate.warningCount > 0 && <span>{plural(candidate.warningCount, "warning")}</span>}
        {summary && <span>{summary}</span>}
      </div>
      {candidate.hasChunkIdentityRisk && (
        <div className="workspace-candidate__risk"><i className="ti ti-alert-triangle" /> Source folder name used as identity</div>
      )}
    </button>
  );
}
