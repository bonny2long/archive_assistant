import { useState } from "react";
import { api } from "../api/client";
import type {
  MetadataEnrichmentApplyResponse,
  MetadataEnrichmentCandidate,
  MetadataEnrichmentPreview,
} from "../types/archive";

type Props = {
  batchId: number;
  onApplied: (result: MetadataEnrichmentApplyResponse) => void;
};

function percent(value: number): string {
  return String(Math.round(value * 100)) + "%";
}

function candidateLabel(candidate: MetadataEnrichmentCandidate): string {
  const year = candidate.year ? " · " + candidate.year : "";
  const type = candidate.release_type ? " · " + candidate.release_type : "";
  return candidate.artist + " · " + candidate.title + year + type;
}

export default function MusicMetadataEnrichmentPanel({ batchId, onApplied }: Props) {
  const [preview, setPreview] = useState<MetadataEnrichmentPreview | null>(null);
  const [loading, setLoading] = useState(false);
  const [applyingReleaseId, setApplyingReleaseId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);

  const findMetadata = async () => {
    setLoading(true);
    setError(null);
    setMessage(null);
    try {
      setPreview(await api.previewMetadataEnrichment(batchId));
    } catch (lookupError: unknown) {
      setError(lookupError instanceof Error ? lookupError.message : "Metadata lookup failed.");
    } finally {
      setLoading(false);
    }
  };

  const applyMatch = async (candidate: MetadataEnrichmentCandidate) => {
    setApplyingReleaseId(candidate.release_id);
    setError(null);
    setMessage(null);
    try {
      const result = await api.applyMetadataEnrichment(batchId, candidate.release_id);
      onApplied(result);
      setMessage(result.message);
    } catch (applyError: unknown) {
      setError(applyError instanceof Error ? applyError.message : "Metadata match could not be applied.");
    } finally {
      setApplyingReleaseId(null);
    }
  };

  return (
    <section className="metadata-card metadata-enrichment-card">
      <div className="metadata-card__heading">
        <div>
          <h3>Metadata enrichment</h3>
          <p>Find catalog metadata from the attached files and current release clues. Files and embedded tags stay untouched.</p>
        </div>
        <button type="button" className="btn-sm btn-sm--active" disabled={loading} onClick={() => void findMetadata()}>
          <i className={"ti ti-" + (loading ? "loader-2 spinner" : "search")} />
          {loading ? "Finding metadata..." : "Find metadata"}
        </button>
      </div>

      {error && <p className="metadata-enrichment__message metadata-enrichment__message--error">{error}</p>}
      {message && <p className="metadata-enrichment__message metadata-enrichment__message--success">{message}</p>}

      {!preview && !error && (
        <p className="metadata-card__empty">
          Search MusicBrainz using the release title, year, track names, and track positions already attached to this batch.
        </p>
      )}

      {preview && preview.candidates.length === 0 && (
        <p className="metadata-card__empty">{preview.message}</p>
      )}

      {preview && preview.candidates.length > 0 && (
        <div className="metadata-enrichment__results">
          <div className="metadata-enrichment__query">
            <span>Search clues</span>
            <strong>{preview.query.raw_release_title || preview.query.release_title || "Attached files"}</strong>
            {preview.query.year && <small>{preview.query.year}</small>}
          </div>
          {preview.candidates.map((candidate) => (
            <div className="metadata-enrichment__candidate" key={candidate.release_id}>
              <div className="metadata-enrichment__candidate-main">
                <strong>{candidateLabel(candidate)}</strong>
                <span>
                  {percent(candidate.match_confidence)} match · {candidate.matched_track_count}/{candidate.local_track_count} files matched
                </span>
                {candidate.track_matches.length > 0 && (
                  <small>
                    {candidate.track_matches
                      .slice(0, 6)
                      .map((track) => String(track.track_number ?? "?") + " " + track.title)
                      .join(" · ")}
                  </small>
                )}
              </div>
              <button
                type="button"
                className="btn-sm"
                disabled={applyingReleaseId !== null}
                title="Apply this catalog match as a review suggestion. Save metadata review to confirm it."
                onClick={() => void applyMatch(candidate)}
              >
                <i className={"ti ti-" + (applyingReleaseId === candidate.release_id ? "loader-2 spinner" : "sparkles")} />
                {applyingReleaseId === candidate.release_id ? "Applying..." : "Apply match"}
              </button>
            </div>
          ))}
        </div>
      )}
    </section>
  );
}