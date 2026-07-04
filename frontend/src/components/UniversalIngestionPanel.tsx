import { useEffect, useMemo, useState } from "react";
import { api } from "../api/client";
import type {
  BatchUniversalIngestion,
  MediaIdentityCandidate,
  UniversalDecisionName,
  UniversalReviewAction,
  UniversalReviewActionUpdate,
} from "../types/archive";

const DECISION_LABELS: Record<UniversalDecisionName, string> = {
  safe_group: "Safe Group",
  split_recommended: "Split Recommended",
  merge_recommended: "Merge Recommended",
  review_required: "Review Required",
  blocked_conflict: "Blocked Conflict",
};

const DECISION_HELP: Record<UniversalDecisionName, string> = {
  safe_group: "AA found a clean candidate group. No conflict detected.",
  merge_recommended: "These source fragments appear to belong to the same media item or release.",
  split_recommended: "This source folder contains multiple media identities and should be split during final organization.",
  review_required: "AA found uncertain or conflicting metadata. Review before final move.",
  blocked_conflict: "AA found a conflict that should not move automatically.",
};

const MEDIA_CLASSES = [
  "music_audio",
  "audiobook_audio",
  "ebook",
  "comic",
  "movie",
  "tv_episode",
  "video_extra",
  "subtitle",
  "artwork",
  "sidecar_metadata",
  "playlist",
  "archive_file",
  "unknown",
];

function actionLabel(action: UniversalReviewAction): string {
  if (action.action_type === "approve_candidate") return "Approved by user";
  if (action.action_type === "mark_review_later") return "Review later";
  if (action.action_type === "override_media_class") return `Media class override: ${formatToken(action.target_media_class || "unknown")}`;
  if (action.action_type === "override_identity") return "Identity override";
  if (action.action_type === "exclude_from_move_plan") return "Excluded from move plan";
  if (action.action_type === "block_candidate") return "Blocked by user";
  if (action.action_type === "split_candidate") return action.decision_status === "applied" ? "Child batch created" : "Will create child batch";
  if (action.action_type === "merge_candidates") return "Merge requested";
  return formatToken(action.action_type);
}
function hasCandidateAction(candidate: { active_actions?: UniversalReviewAction[] | null }, actionType: string): boolean {
  return (candidate.active_actions ?? []).some((action) => action.action_type === actionType && action.decision_status !== "cleared");
}

function hasAppliedCandidateAction(candidate: { active_actions?: UniversalReviewAction[] | null }, actionType: string): boolean {
  return (candidate.active_actions ?? []).some((action) => action.action_type === actionType && action.decision_status === "applied");
}

function childBatchActionLabel(candidate: { active_actions?: UniversalReviewAction[] | null }): string {
  if (hasAppliedCandidateAction(candidate, "approve_candidate") || hasAppliedCandidateAction(candidate, "split_candidate")) {
    return "Child batch created";
  }
  if (hasCandidateAction(candidate, "approve_candidate")) return "Will create child batch";
  return "Approve first";
}

function formatToken(value: string): string {
  return value.replace(/_/g, " ").replace(/\b\w/g, (letter) => letter.toUpperCase());
}

function decisionLabel(value: string): string {
  return DECISION_LABELS[value as UniversalDecisionName] ?? formatToken(value);
}

function candidateTitle(candidate: MediaIdentityCandidate): string {
  return candidate.candidate_title || candidate.candidate_key;
}

function memberDetail(member: MediaIdentityCandidate["members"][number]): string {
  const parts = [
    member.disc_number ? `Disc ${member.disc_number}` : null,
    member.track_number ? `Track ${member.track_number}` : null,
    member.season_number && member.episode_number ? `S${member.season_number}E${member.episode_number}` : null,
    member.title,
    member.artist_or_author,
    member.album_or_series,
  ].filter(Boolean);
  return parts.length > 0 ? parts.join(" | ") : member.relative_path;
}

export default function UniversalIngestionPanel({ batchId }: { batchId: number }) {
  const [review, setReview] = useState<BatchUniversalIngestion | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [savingAction, setSavingAction] = useState<number | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [mediaClassOverrides, setMediaClassOverrides] = useState<Record<number, string>>({});
  const [identityOverrides, setIdentityOverrides] = useState<Record<number, { title: string; creator: string; year: string }>>({});

  useEffect(() => {
    let active = true;
    setLoading(true);
    setError(null);
    api.getBatchUniversalIngestion(batchId, true)
      .then((result) => {
        if (active) setReview(result);
      })
      .catch((err: unknown) => {
        if (active) setError(err instanceof Error ? err.message : "Universal ingestion review unavailable");
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, [batchId]);

  const decisionsByCandidate = useMemo(() => {
    const map = new Map<number, string>();
    for (const decision of review?.reconstruction_decisions ?? []) {
      if (decision.candidate_id) map.set(decision.candidate_id, decision.decision);
    }
    return map;
  }, [review]);

  function refreshReview() {
    return api.getBatchUniversalIngestion(batchId, false).then(setReview);
  }

  function submitAction(candidate: MediaIdentityCandidate, update: UniversalReviewActionUpdate) {
    setSavingAction(candidate.id);
    setActionError(null);
    api.createUniversalIngestionAction(batchId, {
      candidate_id: candidate.id,
      ...update,
    })
      .then(() => refreshReview())
      .catch((err: unknown) => setActionError(err instanceof Error ? err.message : "Could not save review action"))
      .finally(() => setSavingAction(null));
  }

  function clearAction(action: UniversalReviewAction) {
    setSavingAction(action.candidate_id ?? -1);
    setActionError(null);
    api.clearUniversalIngestionAction(batchId, action.id)
      .then(() => refreshReview())
      .catch((err: unknown) => setActionError(err instanceof Error ? err.message : "Could not clear review action"))
      .finally(() => setSavingAction(null));
  }

  if (loading) {
    return (
      <section className="universal-ingestion-panel universal-ingestion-panel--loading">
        <div className="universal-ingestion-panel__heading">
          <span>Universal ingestion review</span>
          <h3>Loading source and candidate analysis</h3>
        </div>
      </section>
    );
  }

  if (error) {
    return (
      <section className="universal-ingestion-panel universal-ingestion-panel--error">
        <div className="universal-ingestion-panel__heading">
          <span>Universal ingestion review</span>
          <h3>Review unavailable</h3>
          <p>{error}</p>
        </div>
      </section>
    );
  }

  if (!review || review.analysis_status === "not_analyzed") {
    return (
      <section className="universal-ingestion-panel">
        <div className="universal-ingestion-panel__heading">
          <span>Universal ingestion review</span>
          <h3>No source-fragment analysis yet</h3>
        </div>
      </section>
    );
  }

  const summary = review.summary;
  const mediaCounts = Object.entries(summary.media_class_counts).sort((a, b) => b[1] - a[1]);
  const decisionCounts = Object.entries(summary.decision_counts);

  return (
    <section className={`universal-ingestion-panel universal-ingestion-panel--${summary.worst_decision}`}>
      <div className="universal-ingestion-panel__heading">
        <div>
          <span>Universal ingestion review</span>
          <h3>
            {summary.candidate_count} candidate groups | {summary.source_fragment_count} source fragments | {summary.mixed_media_flag_count} warnings
          </h3>
          <p>Source folder boundaries are evidence, not final library placement.</p>
        </div>
        <strong className={`universal-decision universal-decision--${summary.worst_decision}`}>
          Worst decision: {decisionLabel(summary.worst_decision)}
        </strong>
      </div>

      {actionError && <div className="universal-action-error">{actionError}</div>}

      <div className="universal-ingestion-counts">
        <div>
          <span>Media classes</span>
          <div>{mediaCounts.length ? mediaCounts.map(([key, count]) => <b key={key}>{formatToken(key)}: {count}</b>) : <b>None</b>}</div>
        </div>
        <div>
          <span>Decision states</span>
          <div>{decisionCounts.map(([key, count]) => <b key={key}>{decisionLabel(key)}: {count}</b>)}</div>
        </div>
      </div>

      <details className="universal-ingestion-section" open>
        <summary>Candidate Groups</summary>
        <div className="universal-candidate-list">
          {review.candidates.map((candidate) => {
            const decision = decisionsByCandidate.get(candidate.id) ?? "safe_group";
            return (
              <article key={candidate.id} className={`universal-candidate universal-candidate--${decision}`}>
                <div className="universal-candidate__top">
                  <div>
                    <span>{formatToken(candidate.candidate_media_type)}</span>
                    <h4>{candidateTitle(candidate)}</h4>
                    <p>{candidate.candidate_primary_creator || "Unknown creator"}</p>
                  </div>
                  <strong className={`universal-decision universal-decision--${decision}`}>
                    {decisionLabel(decision)}
                  </strong>
                </div>
                <div className="universal-candidate__meta">
                  <span>{candidate.candidate_confidence_label} confidence</span>
                  <span>{candidate.member_count} members</span>
                  <span>{candidate.source_fragment_count} source fragments</span>
                  {candidate.candidate_year && <span>{candidate.candidate_year}</span>}
                </div>
                <p className="universal-candidate__reason">{candidate.summary_reason || DECISION_HELP[decision as UniversalDecisionName]}</p>
                {candidate.recommended_action && (
                  <p className="universal-candidate__action"><strong>Recommended action:</strong> {candidate.recommended_action}</p>
                )}
                {(candidate.active_actions ?? []).length > 0 && (
                  <div className="universal-active-actions" aria-label="Active user actions">
                    {(candidate.active_actions ?? []).map((action) => (
                      <span key={action.id}>
                        {actionLabel(action)}
                        <button
                          type="button"
                          onClick={() => clearAction(action)}
                          disabled={savingAction === candidate.id}
                          title="Clear this review action"
                        >
                          Clear
                        </button>
                      </span>
                    ))}
                  </div>
                )}
                <div className="universal-action-bar" aria-label="Universal ingestion review actions">
                  <button
                    type="button"
                    onClick={() => submitAction(candidate, { action_type: "approve_candidate", reason: "User confirmed candidate grouping." })}
                    disabled={savingAction === candidate.id}
                  >
                    Approve
                  </button>
                  <button
                    type="button"
                    onClick={() => submitAction(candidate, { action_type: "mark_review_later", reason: "User marked candidate for later lookup." })}
                    disabled={savingAction === candidate.id}
                  >
                    Review later
                  </button>
                  <button
                    type="button"
                    onClick={() => submitAction(candidate, { action_type: "exclude_from_move_plan", reason: "User excluded candidate from current move plan without deleting files." })}
                    disabled={savingAction === candidate.id}
                  >
                    Exclude
                  </button>
                  <button
                    type="button"
                    onClick={() => submitAction(candidate, { action_type: "split_candidate", reason: "Candidate will create a child batch during parent materialization." })}
                    disabled={savingAction === candidate.id || !hasCandidateAction(candidate, "approve_candidate") || hasAppliedCandidateAction(candidate, "approve_candidate") || hasAppliedCandidateAction(candidate, "split_candidate")}
                  >
                    {childBatchActionLabel(candidate)}
                  </button>
                  <button
                    type="button"
                    onClick={() => submitAction(candidate, { action_type: "block_candidate", reason: "User blocked candidate because the conflict is unsafe." })}
                    disabled={savingAction === candidate.id}
                  >
                    Block
                  </button>
                </div>
                <details className="universal-action-drawer">
                  <summary>Overrides</summary>
                  <div className="universal-override-row">
                    <label>
                      <span>Media class</span>
                      <select
                        value={mediaClassOverrides[candidate.id] ?? candidate.candidate_media_type}
                        onChange={(event) => setMediaClassOverrides((current) => ({ ...current, [candidate.id]: event.target.value }))}
                      >
                        {MEDIA_CLASSES.map((mediaClass) => (
                          <option key={mediaClass} value={mediaClass}>{formatToken(mediaClass)}</option>
                        ))}
                      </select>
                    </label>
                    <button
                      type="button"
                      onClick={() => submitAction(candidate, {
                        action_type: "override_media_class",
                        target_media_class: mediaClassOverrides[candidate.id] ?? candidate.candidate_media_type,
                        reason: "User corrected the candidate media class.",
                      })}
                      disabled={savingAction === candidate.id}
                    >
                      Save class
                    </button>
                  </div>
                  <div className="universal-override-grid">
                    <label>
                      <span>Title</span>
                      <input
                        value={identityOverrides[candidate.id]?.title ?? candidate.candidate_title ?? ""}
                        onChange={(event) => setIdentityOverrides((current) => ({
                          ...current,
                          [candidate.id]: { ...(current[candidate.id] ?? { title: candidate.candidate_title ?? "", creator: candidate.candidate_primary_creator ?? "", year: candidate.candidate_year ?? "" }), title: event.target.value },
                        }))}
                      />
                    </label>
                    <label>
                      <span>Creator</span>
                      <input
                        value={identityOverrides[candidate.id]?.creator ?? candidate.candidate_primary_creator ?? ""}
                        onChange={(event) => setIdentityOverrides((current) => ({
                          ...current,
                          [candidate.id]: { ...(current[candidate.id] ?? { title: candidate.candidate_title ?? "", creator: candidate.candidate_primary_creator ?? "", year: candidate.candidate_year ?? "" }), creator: event.target.value },
                        }))}
                      />
                    </label>
                    <label>
                      <span>Year</span>
                      <input
                        value={identityOverrides[candidate.id]?.year ?? candidate.candidate_year ?? ""}
                        onChange={(event) => setIdentityOverrides((current) => ({
                          ...current,
                          [candidate.id]: { ...(current[candidate.id] ?? { title: candidate.candidate_title ?? "", creator: candidate.candidate_primary_creator ?? "", year: candidate.candidate_year ?? "" }), year: event.target.value },
                        }))}
                      />
                    </label>
                    <button
                      type="button"
                      onClick={() => {
                        const override = identityOverrides[candidate.id] ?? {
                          title: candidate.candidate_title ?? "",
                          creator: candidate.candidate_primary_creator ?? "",
                          year: candidate.candidate_year ?? "",
                        };
                        submitAction(candidate, {
                          action_type: "override_identity",
                          override_title: override.title || null,
                          override_primary_creator: override.creator || null,
                          override_year: override.year || null,
                          reason: "User corrected candidate identity fields.",
                        });
                      }}
                      disabled={savingAction === candidate.id}
                    >
                      Save identity
                    </button>
                  </div>
                </details>
                <details className="universal-member-drawer">
                  <summary>Members</summary>
                  <div className="universal-member-list">
                    {candidate.members.map((member) => (
                      <div key={member.id} className="universal-member-row">
                        <strong title={member.relative_path}>{member.filename}</strong>
                        <span>{formatToken(member.media_class)} | {formatToken(member.member_role)}</span>
                        <small>{memberDetail(member)}</small>
                        <code>{member.relative_path}</code>
                      </div>
                    ))}
                  </div>
                </details>
              </article>
            );
          })}
        </div>
      </details>

      <details className="universal-ingestion-section">
        <summary>Source Fragments</summary>
        <div className="universal-fragment-list">
          {review.source_fragments.map((fragment) => (
            <article key={fragment.id} className="universal-fragment">
              <span>Incoming Source Fragment</span>
              <h4>{fragment.fragment_label || fragment.source_path}</h4>
              <p>Not final library placement</p>
              <small>{fragment.file_count} files | group {fragment.fragment_group_key || "none"}</small>
              <div>
                {Object.entries(fragment.media_class_counts).map(([key, count]) => (
                  <b key={key}>{formatToken(key)}: {count}</b>
                ))}
              </div>
            </article>
          ))}
        </div>
      </details>

      {review.mixed_media_flags.length > 0 && (
        <details className="universal-ingestion-section" open>
          <summary>Warnings / Mixed Media Flags</summary>
          <div className="universal-flag-list">
            {review.mixed_media_flags.map((flag) => (
              <article key={flag.id} className="universal-flag">
                <strong>{formatToken(flag.flag_type)}</strong>
                <span>{flag.severity}</span>
                <p>{flag.message}</p>
                {flag.recommended_action && <small>Recommended action: {flag.recommended_action}</small>}
                {flag.example_paths.length > 0 && <code>{flag.example_paths.slice(0, 3).join(" | ")}</code>}
              </article>
            ))}
          </div>
        </details>
      )}
    </section>
  );
}