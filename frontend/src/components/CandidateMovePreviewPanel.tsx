import { useEffect, useState } from "react";
import { api } from "../api/client";
import type { CandidateMovePreview, CandidateMovePreviewGroup } from "../types/archive";

interface CandidateMovePreviewPanelProps {
  batchId: number;
  compact?: boolean;
}

function formatToken(value: string): string {
  return value.replace(/_/g, " ").replace(/\b\w/g, (letter) => letter.toUpperCase());
}

function groupClass(group: CandidateMovePreviewGroup): string {
  if (group.blocked) return "candidate-move-preview-card candidate-move-preview-card--blocked";
  if (group.requires_review) return "candidate-move-preview-card candidate-move-preview-card--review";
  return "candidate-move-preview-card";
}

export default function CandidateMovePreviewPanel({ batchId, compact = false }: CandidateMovePreviewPanelProps) {
  const [preview, setPreview] = useState<CandidateMovePreview | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  function load(snapshot = false) {
    setLoading(true);
    setError(null);
    api.getCandidateMovePreview(batchId, snapshot)
      .then(setPreview)
      .catch((err: unknown) => setError(err instanceof Error ? err.message : "Could not load candidate move preview"))
      .finally(() => setLoading(false));
  }

  useEffect(() => {
    load(false);
  }, [batchId]);

  if (loading) {
    return <section className="candidate-move-preview"><div className="candidate-move-preview__eyebrow">Candidate move preview</div><div className="candidate-move-preview__title">Loading preview</div></section>;
  }
  if (error) {
    return <section className="candidate-move-preview"><div className="candidate-move-preview__eyebrow">Candidate move preview</div><div className="candidate-move-preview__title">Preview unavailable</div><p>{error}</p></section>;
  }
  if (!preview || preview.status === "not_analyzed") {
    return (
      <section className="candidate-move-preview">
        <div className="candidate-move-preview__header">
          <div>
            <div className="candidate-move-preview__eyebrow">Candidate move preview</div>
            <div className="candidate-move-preview__title">No candidate preview yet</div>
          </div>
          <button type="button" className="candidate-move-preview__button" onClick={() => load(true)}>Run preview analysis</button>
        </div>
      </section>
    );
  }

  const mediaCounts = Object.entries(preview.summary.media_class_counts).sort((a, b) => b[1] - a[1]);
  return (
    <section className={`candidate-move-preview candidate-move-preview--${preview.status} ${compact ? "candidate-move-preview--compact" : ""}`}>
      <div className="candidate-move-preview__header">
        <div>
          <div className="candidate-move-preview__eyebrow">Candidate move preview</div>
          <div className="candidate-move-preview__title">{preview.summary.candidate_count} candidates | {preview.summary.member_count} members</div>
          <div className="candidate-move-preview__chips">
            <span className="candidate-move-preview__chip">Actions: {preview.summary.active_action_count}</span>
            {preview.summary.mixed_media && <span className="candidate-move-preview__chip">Mixed media</span>}
            {preview.summary.music_only_fragmented && <span className="candidate-move-preview__chip">Music-only fragmented</span>}
            <span className="candidate-move-preview__chip">Review: {preview.summary.review_required_count}</span>
            <span className="candidate-move-preview__chip">Blocked: {preview.summary.blocked_conflict_count}</span>
            {mediaCounts.map(([key, count]) => <span key={key} className="candidate-move-preview__chip">{formatToken(key)}: {count}</span>)}
          </div>
        </div>
      </div>

      {preview.global_warnings.length > 0 && (
        <div className="candidate-move-preview__warnings">
          {preview.global_warnings.map((warning) => <span key={warning} className="candidate-move-preview__chip">{formatToken(warning)}</span>)}
        </div>
      )}
      {preview.next_actions.length > 0 && (
        <div className="candidate-move-preview__next-actions">
          {preview.next_actions.map((action) => <span key={action} className="candidate-move-preview__chip">{action}</span>)}
        </div>
      )}

      <div className="candidate-move-preview__groups">
        {preview.preview_groups.map((group) => (
          <article key={group.candidate_id} className={groupClass(group)}>
            <div className="candidate-move-preview-card__top">
              <div>
                <div className="candidate-move-preview-card__media">{formatToken(group.candidate_media_type || "unknown")}</div>
                <div className="candidate-move-preview-card__title">{group.candidate_title || "Unknown title"}</div>
                <div className="candidate-move-preview-card__creator">{group.candidate_primary_creator || "Unknown creator"}{group.candidate_year ? ` | ${group.candidate_year}` : ""}</div>
              </div>
              <div className="candidate-move-preview__chip">{group.target_library}</div>
            </div>
            <div className="candidate-move-preview-card__destination">{group.destination_preview}</div>
            <div className="candidate-move-preview-card__badges">
              <span className="candidate-move-preview__chip">{group.member_count} members</span>
              <span className="candidate-move-preview__chip">{group.source_fragment_count} fragments</span>
              {group.active_action && <span className="candidate-move-preview__chip">Action: {formatToken(String(group.active_action.action_type ?? "active"))}</span>}
              {group.blocked && <span className="candidate-move-preview__chip">Blocked</span>}
              {group.requires_review && <span className="candidate-move-preview__chip">Review required</span>}
              {group.warnings.map((warning) => <span key={warning} className="candidate-move-preview__chip">{formatToken(warning)}</span>)}
            </div>
          </article>
        ))}
      </div>
    </section>
  );
}