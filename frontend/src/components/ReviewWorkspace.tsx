import { useCallback, useEffect, useMemo, useState } from "react";
import { api } from "../api/client";
import type {
  BatchMetadataQuality,
  BatchUniversalIngestion,
  FragmentReconstructionDecision,
  IngestBatch,
  MediaIdentityCandidate,
  RoutingDecision,
  UniversalReviewAction,
  UniversalReviewActionType,
  UniversalReviewActionUpdate,
  WorkspaceCandidateState,
  WorkspaceFilter,
} from "../types/archive";
import WorkspaceCandidateCard from "./WorkspaceCandidateCard";
import WorkspaceHeader from "./WorkspaceHeader";
import WorkspaceInspector from "./WorkspaceInspector";
import WorkspaceLeftRail from "./WorkspaceLeftRail";

export const SOURCE_CHUNK_PATTERNS = [
  /\bpart\s*\d+\b/i,
  /\bdisc\s*\d+\b/i,
  /\bcd\s*\d+\b/i,
  /\bchapter\s*\d+\b/i,
  /\bvolume\s*\d+\b/i,
  /\bfragment\b/i,
  /\bchunk\b/i,
];

export type CandidateViewModel = {
  id: number;
  title: string;
  creator: string;
  year: string;
  mediaType: WorkspaceFilter;
  displayState: WorkspaceCandidateState;
  confidenceLabel: string;
  fileCount: number;
  sourceFragmentCount: number;
  warningCount: number;
  recommendedAction: string;
  hasChunkIdentityRisk: boolean;
  activeActions: UniversalReviewAction[];
  rawCandidate: MediaIdentityCandidate;
};

type ReviewWorkspaceProps = {
  batch: IngestBatch;
  onClose: () => void;
  onSaveAction: (batchId: number, update: UniversalReviewActionUpdate) => Promise<void>;
  onClearAction: (batchId: number, actionId: number) => Promise<void>;
  onApprove: (batchId: number) => Promise<void>;
};

function mediaTypeFilter(value: string | null | undefined): WorkspaceFilter {
  const normalized = (value ?? "unknown").toLowerCase();
  if (normalized.includes("music")) return "music";
  if (normalized.includes("audio")) return "audiobook";
  if (normalized.includes("ebook") || normalized === "book") return "ebook";
  if (normalized.includes("comic")) return "comic";
  if (normalized.includes("movie")) return "movie";
  if (normalized.includes("tv")) return "tv";
  if (normalized.includes("art")) return "artwork";
  return "unknown";
}

function hasActiveAction(actions: UniversalReviewAction[], actionType: UniversalReviewActionType): boolean {
  return actions.some((action) => action.action_type === actionType && action.decision_status !== "cleared");
}

function candidateDecisions(
  candidateId: number,
  decisions: FragmentReconstructionDecision[],
): FragmentReconstructionDecision[] {
  return decisions.filter((decision) => decision.candidate_id === candidateId);
}

function candidateHasChunkIdentityRisk(candidate: MediaIdentityCandidate, routing: RoutingDecision | null): boolean {
  const routeRisk = routing?.candidate_route_summaries?.some(
    (summary) => summary.candidate_id === candidate.id && summary.chunk_identity_risk,
  );
  if (routeRisk) return true;
  return candidate.members.some((member) => SOURCE_CHUNK_PATTERNS.some(
    (pattern) => pattern.test(member.relative_path) || pattern.test(member.filename),
  ));
}

function deriveDisplayState(
  candidate: MediaIdentityCandidate,
  decisions: FragmentReconstructionDecision[],
): WorkspaceCandidateState {
  const actions = candidate.active_actions ?? [];
  if (hasActiveAction(actions, "block_candidate")) return "blocked";
  if (hasActiveAction(actions, "approve_candidate")) return "approved";
  if (hasActiveAction(actions, "mark_review_later")) return "review";
  if (decisions.some((decision) => decision.decision === "blocked_conflict")) return "blocked";
  if (decisions.some((decision) => ["review_required", "split_recommended", "merge_recommended"].includes(decision.decision))) {
    return "review";
  }
  return "safe";
}

export function buildCandidateViewModels(
  ingestion: BatchUniversalIngestion,
  routing: RoutingDecision | null,
): CandidateViewModel[] {
  return ingestion.candidates.map((candidate) => {
    const decisions = candidateDecisions(candidate.id, ingestion.reconstruction_decisions);
    const relatedFlags = ingestion.mixed_media_flags.filter((flag) => flag.candidate_id === candidate.id);
    const displayState = deriveDisplayState(candidate, decisions);
    return {
      id: candidate.id,
      title: candidate.candidate_title || candidate.candidate_key || "Untitled candidate",
      creator: candidate.candidate_primary_creator || candidate.candidate_secondary_creator || "Unknown creator",
      year: candidate.candidate_year || "Unknown year",
      mediaType: mediaTypeFilter(candidate.candidate_media_type),
      displayState,
      confidenceLabel: candidate.candidate_confidence_label || `${Math.round(candidate.candidate_confidence * 100)}%`,
      fileCount: candidate.member_count || candidate.members.length,
      sourceFragmentCount: candidate.source_fragment_count,
      warningCount: decisions.length + relatedFlags.length,
      recommendedAction: candidate.recommended_action || decisions[0]?.recommended_action || "Review candidate",
      hasChunkIdentityRisk: candidateHasChunkIdentityRisk(candidate, routing),
      activeActions: candidate.active_actions ?? [],
      rawCandidate: candidate,
    };
  });
}

function filterCandidates(candidates: CandidateViewModel[], filter: WorkspaceFilter): CandidateViewModel[] {
  if (filter === "all") return candidates;
  if (["blocked", "review", "safe"].includes(filter)) {
    return candidates.filter((candidate) => candidate.displayState === filter);
  }
  return candidates.filter((candidate) => candidate.mediaType === filter);
}

export default function ReviewWorkspace({
  batch,
  onClose,
  onSaveAction,
  onClearAction,
  onApprove,
}: ReviewWorkspaceProps) {
  const [ingestion, setIngestion] = useState<BatchUniversalIngestion | null>(null);
  const [routing, setRouting] = useState<RoutingDecision | null>(null);
  const [quality, setQuality] = useState<BatchMetadataQuality | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [selectedCandidateId, setSelectedCandidateId] = useState<number | null>(null);
  const [filter, setFilter] = useState<WorkspaceFilter>("all");
  const [savingActionId, setSavingActionId] = useState<number | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [showTech, setShowTech] = useState(false);

  const loadWorkspace = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [nextIngestion, nextRouting, nextQuality] = await Promise.all([
        api.getBatchUniversalIngestion(batch.id, true),
        api.getReviewRouting(batch.id),
        api.getBatchMetadataQuality(batch.id),
      ]);
      setIngestion(nextIngestion);
      setRouting(nextRouting);
      setQuality(nextQuality);
      setSelectedCandidateId((current) => current ?? nextIngestion.candidates[0]?.id ?? null);
    } catch (loadError: unknown) {
      setError(loadError instanceof Error ? loadError.message : "Unable to load review workspace");
    } finally {
      setLoading(false);
    }
  }, [batch.id]);

  useEffect(() => {
    void loadWorkspace();
  }, [loadWorkspace]);

  const candidates = useMemo(
    () => ingestion ? buildCandidateViewModels(ingestion, routing) : [],
    [ingestion, routing],
  );
  const filteredCandidates = useMemo(() => filterCandidates(candidates, filter), [candidates, filter]);
  const selectedCandidate = candidates.find((candidate) => candidate.id === selectedCandidateId)
    ?? filteredCandidates[0]
    ?? null;
  const qualityIssueCount = (quality?.blocked_count ?? 0) + (quality?.review_required_count ?? 0);

  const handleAction = async (
    candidateId: number,
    actionType: UniversalReviewActionType,
    overrides: Partial<UniversalReviewActionUpdate> = {},
  ) => {
    setSavingActionId(candidateId);
    setActionError(null);
    try {
      await onSaveAction(batch.id, { action_type: actionType, candidate_id: candidateId, ...overrides });
      await loadWorkspace();
    } catch (saveError: unknown) {
      setActionError(saveError instanceof Error ? saveError.message : "Unable to save review action");
    } finally {
      setSavingActionId(null);
    }
  };

  const handleClear = async (actionId: number, candidateId: number) => {
    setSavingActionId(candidateId);
    setActionError(null);
    try {
      await onClearAction(batch.id, actionId);
      await loadWorkspace();
    } catch (clearError: unknown) {
      setActionError(clearError instanceof Error ? clearError.message : "Unable to clear review action");
    } finally {
      setSavingActionId(null);
    }
  };

  return (
    <div className="review-workspace" role="dialog" aria-modal="true" aria-label="Review Workspace">
      <WorkspaceHeader
        batch={batch}
        ingestion={ingestion}
        routing={routing}
        onClose={onClose}
        onApprove={onApprove}
      />
      {loading && <div className="review-workspace__state"><i className="ti ti-loader-2 spinner" /> Loading workspace...</div>}
      {!loading && error && <div className="review-workspace__state review-workspace__state--error"><i className="ti ti-alert-triangle" /> {error}</div>}
      {!loading && !error && ingestion && (
        <div className="review-workspace__body">
          <WorkspaceLeftRail
            filter={filter}
            candidates={candidates}
            qualityIssueCount={qualityIssueCount}
            showTech={showTech}
            onFilterChange={setFilter}
            onToggleTech={() => setShowTech((current) => !current)}
          />
          <section className="review-workspace__candidates" aria-label="Candidates">
            {filteredCandidates.map((candidate) => (
              <WorkspaceCandidateCard
                key={candidate.id}
                candidate={candidate}
                selected={candidate.id === selectedCandidate?.id}
                onSelect={() => setSelectedCandidateId(candidate.id)}
              />
            ))}
            {filteredCandidates.length === 0 && (
              <div className="review-workspace__empty">No candidates match this filter.</div>
            )}
          </section>
          <WorkspaceInspector
            vm={selectedCandidate}
            ingestion={ingestion}
            batchId={batch.id}
            savingActionId={savingActionId}
            actionError={actionError}
            onAction={handleAction}
            onClear={handleClear}
            showTech={showTech}
            onCloseTech={() => setShowTech(false)}
          />
        </div>
      )}
    </div>
  );
}
