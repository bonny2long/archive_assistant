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
  /^drive-download-/i,
  /^googledrive[-_\s]*\d+/i,
  /^google-drive[-_\s]*\d+/i,
  /^part[-_\s]*\d{2,}$/i,
  /^chunk[-_\s]*\d+$/i,
  /^source[-_\s]*fragment[-_\s]*\d*$/i,
  /^fragment[-_\s]*\d+$/i,
];

function lastPathSegment(value: string): string {
  return value.replace(/\\/g, "/").split("/").filter(Boolean).pop() ?? value;
}

function isSourceChunkIdentity(value: string | null | undefined): boolean {
  if (!value) return false;
  const trimmed = value.trim();
  if (!trimmed) return false;
  const segment = lastPathSegment(trimmed);
  return SOURCE_CHUNK_PATTERNS.some((pattern) => pattern.test(segment));
}

function isActionActive(action: UniversalReviewAction): boolean {
  return action.decision_status !== "cleared";
}

function activeOnly(actions: UniversalReviewAction[] | null | undefined): UniversalReviewAction[] {
  return (actions ?? []).filter(isActionActive);
}

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
  onOpenFullEditor?: (batch: IngestBatch) => void;
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

function mediaTypeFromClass(mediaClass: string | null | undefined): string | null {
  if (!mediaClass) return null;
  const mapping: Record<string, string> = {
    music_audio: "music",
    audiobook_audio: "audiobook",
    ebook: "ebook",
    comic: "comic",
    movie: "movie",
    tv_episode: "tv",
    artwork: "artwork",
    sidecar_metadata: "unknown",
    unknown: "unknown",
  };
  return mapping[mediaClass] ?? mediaClass;
}

function latestActiveAction(actions: UniversalReviewAction[], actionType: string): UniversalReviewAction | undefined {
  return actions.find((action) => action.action_type === actionType && isActionActive(action));
}

function applyCandidateOverrides(
  candidate: MediaIdentityCandidate,
  actions: UniversalReviewAction[],
): MediaIdentityCandidate {
  const identityOverride = latestActiveAction(actions, "override_identity");
  const mediaClassOverride = latestActiveAction(actions, "override_media_class");
  const mediaType = mediaTypeFromClass(mediaClassOverride?.target_media_class) ?? candidate.candidate_media_type;
  return {
    ...candidate,
    candidate_title: identityOverride?.override_title || candidate.candidate_title,
    candidate_primary_creator: identityOverride?.override_primary_creator || candidate.candidate_primary_creator,
    candidate_year: identityOverride?.override_year || candidate.candidate_year,
    candidate_series: identityOverride?.override_series || candidate.candidate_series,
    candidate_series_index: identityOverride?.override_series_index || candidate.candidate_series_index,
    candidate_media_type: mediaType,
    active_actions: actions,
  };
}

function hasActiveAction(actions: UniversalReviewAction[], actionType: UniversalReviewActionType): boolean {
  return actions.some((action) => action.action_type === actionType && isActionActive(action));
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

  return [
    candidate.candidate_title,
    candidate.candidate_primary_creator,
    candidate.candidate_secondary_creator,
    candidate.candidate_key,
  ].some(isSourceChunkIdentity);
}

function deriveDisplayState(
  candidate: MediaIdentityCandidate,
  decisions: FragmentReconstructionDecision[],
  hasChunkIdentityRisk: boolean,
): WorkspaceCandidateState {
  const actions = activeOnly(candidate.active_actions);
  if (hasActiveAction(actions, "block_candidate")) return "blocked";
  if (hasActiveAction(actions, "approve_candidate")) return "approved";
  if (hasChunkIdentityRisk) return "review";
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
    const actions = activeOnly(candidate.active_actions);
    const effectiveCandidate = applyCandidateOverrides(candidate, actions);
    const decisions = candidateDecisions(candidate.id, ingestion.reconstruction_decisions);
    const relatedFlags = ingestion.mixed_media_flags.filter((flag) => flag.candidate_id === candidate.id);
    const hasChunkIdentityRisk = candidateHasChunkIdentityRisk(effectiveCandidate, routing);
    const displayState = deriveDisplayState({ ...candidate, active_actions: actions }, decisions, hasChunkIdentityRisk);
    return {
      id: candidate.id,
      title: effectiveCandidate.candidate_title || effectiveCandidate.candidate_key || "Untitled candidate",
      creator: effectiveCandidate.candidate_primary_creator || effectiveCandidate.candidate_secondary_creator || "Unknown creator",
      year: effectiveCandidate.candidate_year || "Unknown year",
      mediaType: mediaTypeFilter(effectiveCandidate.candidate_media_type),
      displayState,
      confidenceLabel: effectiveCandidate.candidate_confidence_label || `${Math.round(effectiveCandidate.candidate_confidence * 100)}%`,
      fileCount: effectiveCandidate.member_count || effectiveCandidate.members.length,
      sourceFragmentCount: effectiveCandidate.source_fragment_count,
      warningCount: decisions.length + relatedFlags.length,
      recommendedAction: effectiveCandidate.recommended_action || decisions[0]?.recommended_action || "Review candidate",
      hasChunkIdentityRisk,
      activeActions: actions,
      rawCandidate: effectiveCandidate,
    };
  });
}

const CANDIDATE_STATE_ORDER: Record<WorkspaceCandidateState, number> = {
  blocked: 0,
  review: 1,
  safe: 2,
  approved: 3,
};

function sortCandidates(candidates: CandidateViewModel[]): CandidateViewModel[] {
  return [...candidates].sort((a, b) => {
    const stateDiff = CANDIDATE_STATE_ORDER[a.displayState] - CANDIDATE_STATE_ORDER[b.displayState];
    if (stateDiff !== 0) return stateDiff;
    const warningDiff = b.warningCount - a.warningCount;
    if (warningDiff !== 0) return warningDiff;
    const fileDiff = b.fileCount - a.fileCount;
    if (fileDiff !== 0) return fileDiff;
    return a.title.localeCompare(b.title);
  });
}

function filterCandidates(candidates: CandidateViewModel[], filter: WorkspaceFilter): CandidateViewModel[] {
  const sorted = sortCandidates(candidates);
  if (filter === "all") return sorted;
  if (filter === "safe") {
    return sorted.filter((candidate) => candidate.displayState === "safe" || candidate.displayState === "approved");
  }
  if (["blocked", "review"].includes(filter)) {
    return sorted.filter((candidate) => candidate.displayState === filter);
  }
  return sorted.filter((candidate) => candidate.mediaType === filter);
}

export default function ReviewWorkspace({
  batch,
  onClose,
  onSaveAction,
  onClearAction,
  onApprove,
  onOpenFullEditor,
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
  const [workspaceRefreshKey, setWorkspaceRefreshKey] = useState(0);

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
  const selectedCandidate = filteredCandidates.find((candidate) => candidate.id === selectedCandidateId)
    ?? filteredCandidates[0]
    ?? null;
  const qualityIssueCount = (quality?.blocked_count ?? 0) + (quality?.review_required_count ?? 0);

  useEffect(() => {
    if (!filteredCandidates.length) {
      if (selectedCandidateId !== null) setSelectedCandidateId(null);
      return;
    }
    if (!filteredCandidates.some((candidate) => candidate.id === selectedCandidateId)) {
      setSelectedCandidateId(filteredCandidates[0].id);
    }
  }, [filteredCandidates, selectedCandidateId]);

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
      setWorkspaceRefreshKey((key) => key + 1);
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
      setWorkspaceRefreshKey((key) => key + 1);
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
            workspaceRefreshKey={workspaceRefreshKey}
            savingActionId={savingActionId}
            actionError={actionError}
            onAction={handleAction}
            onClear={handleClear}
            showTech={showTech}
            onCloseTech={() => setShowTech(false)}
            onOpenFullEditor={onOpenFullEditor ? () => onOpenFullEditor(batch) : undefined}
          />
        </div>
      )}
    </div>
  );
}
