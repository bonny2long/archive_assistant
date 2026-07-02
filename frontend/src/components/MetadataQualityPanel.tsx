import { useEffect, useMemo, useState } from "react";
import { api } from "../api/client";
import type {
  BatchMetadataQuality,
  MetadataQualityDecision,
  MetadataQualityDecisionName,
} from "../types/archive";

const DECISION_LABELS: Record<MetadataQualityDecisionName, string> = {
  approved_ready: "Approved ready",
  review_recommended: "Review recommended",
  review_required: "Review required",
  blocked: "Blocked",
};

const DECISION_ORDER: Record<MetadataQualityDecisionName, number> = {
  blocked: 0,
  review_required: 1,
  review_recommended: 2,
  approved_ready: 3,
};

function formatToken(value: string): string {
  return value
    .replace(/_/g, " ")
    .replace(/\b\w/g, (letter) => letter.toUpperCase());
}

function profileText(item: MetadataQualityDecision): string {
  const profile = item.profile ?? {};
  const title = typeof profile.title === "string" ? profile.title : null;
  const artist = typeof profile.artist === "string" ? profile.artist : null;
  const album = typeof profile.album === "string" ? profile.album : null;
  const track = profile.track_number === null || profile.track_number === undefined
    ? null
    : String(profile.track_number);
  const parts = [track ? `Track ${track}` : null, title, artist, album].filter(Boolean);
  return parts.length > 0 ? parts.join(" | ") : "No normalized profile fields";
}

function sortedItems(items: MetadataQualityDecision[]): MetadataQualityDecision[] {
  return [...items].sort((left, right) => {
    const decisionDelta = DECISION_ORDER[left.decision] - DECISION_ORDER[right.decision];
    if (decisionDelta !== 0) return decisionDelta;
    return left.file_name.localeCompare(right.file_name);
  });
}

export default function MetadataQualityPanel({ batchId }: { batchId: number }) {
  const [quality, setQuality] = useState<BatchMetadataQuality | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let active = true;
    setLoading(true);
    setError(null);
    api.getBatchMetadataQuality(batchId)
      .then((result) => {
        if (active) setQuality(result);
      })
      .catch((err: unknown) => {
        if (active) setError(err instanceof Error ? err.message : "Metadata quality unavailable");
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, [batchId]);

  const items = useMemo(() => sortedItems(quality?.items ?? []), [quality]);
  const flagCounts = Object.entries(quality?.flag_counts ?? {})
    .sort((left, right) => right[1] - left[1] || left[0].localeCompare(right[0]));

  if (loading) {
    return (
      <section className="metadata-quality-panel metadata-quality-panel--loading">
        <div className="metadata-quality-panel__heading">
          <div>
            <span>Metadata quality</span>
            <h3>Loading quality decisions</h3>
          </div>
        </div>
      </section>
    );
  }

  if (error) {
    return (
      <section className="metadata-quality-panel metadata-quality-panel--error">
        <div className="metadata-quality-panel__heading">
          <div>
            <span>Metadata quality</span>
            <h3>Quality decisions unavailable</h3>
            <p>{error}</p>
          </div>
        </div>
      </section>
    );
  }

  if (!quality || quality.total_files === 0) {
    return (
      <section className="metadata-quality-panel">
        <div className="metadata-quality-panel__heading">
          <div>
            <span>Metadata quality</span>
            <h3>No quality decisions for this batch</h3>
          </div>
        </div>
      </section>
    );
  }

  return (
    <section className={`metadata-quality-panel metadata-quality-panel--${quality.worst_decision}`}>
      <div className="metadata-quality-panel__heading">
        <div>
          <span>Metadata quality</span>
          <h3>{DECISION_LABELS[quality.worst_decision]}</h3>
          <p>{quality.total_files} audio files evaluated by the metadata quality gate.</p>
        </div>
        <strong className={`metadata-quality-decision metadata-quality-decision--${quality.worst_decision}`}>
          {DECISION_LABELS[quality.worst_decision]}
        </strong>
      </div>

      <div className="metadata-quality-counts" aria-label="Metadata quality counts">
        <div><strong>{quality.blocked_count}</strong><span>Blocked</span></div>
        <div><strong>{quality.review_required_count}</strong><span>Required</span></div>
        <div><strong>{quality.review_recommended_count}</strong><span>Recommended</span></div>
        <div><strong>{quality.approved_ready_count}</strong><span>Ready</span></div>
      </div>

      {flagCounts.length > 0 && (
        <div className="metadata-quality-flags" aria-label="Metadata quality flags">
          {flagCounts.map(([flag, count]) => (
            <span key={flag}>{formatToken(flag)} ({count})</span>
          ))}
        </div>
      )}

      <div className="metadata-quality-files">
        {items.map((item) => {
          const reasons = item.reasons.length > 0
            ? item.reasons
            : [...item.blocking_flags, ...item.warning_flags];
          return (
            <article key={item.media_file_id} className={`metadata-quality-file metadata-quality-file--${item.decision}`}>
              <div>
                <strong title={item.relative_path ?? item.file_name}>{item.file_name}</strong>
                <span>{profileText(item)}</span>
              </div>
              <div className="metadata-quality-file__meta">
                <span className={`metadata-quality-decision metadata-quality-decision--${item.decision}`}>
                  {DECISION_LABELS[item.decision]}
                </span>
                {typeof item.score === "number" && <small>{Math.round(item.score)} score</small>}
              </div>
              {reasons.length > 0 && (
                <div className="metadata-quality-file__reasons">
                  {reasons.slice(0, 4).map((reason) => (
                    <span key={reason}>{formatToken(reason)}</span>
                  ))}
                </div>
              )}
            </article>
          );
        })}
      </div>
    </section>
  );
}