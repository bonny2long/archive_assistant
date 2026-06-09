import { useMemo, useState } from "react";
import type {
  BatchSummary,
  TvMetadataUpdate,
  TvEpisodeReviewPatch,
  TvEpisodeReviewUpdate,
} from "../types/archive";
import TvEpisodeReviewPanel from "./TvEpisodeReviewPanel";

type Props = {
  batch: BatchSummary;
  saving: boolean;
  onSave: (update: TvMetadataUpdate) => Promise<void>;
  onSaveEpisodeReview: (update: TvEpisodeReviewUpdate) => Promise<void>;
  onConfirm: () => Promise<void>;
  onClose: () => void;
};

function sanitizePathPart(value: string): string {
  return value.replace(/[<>:"/\\|?*]/g, "_").trim();
}

export default function TvMetadataEditor({
  batch,
  saving,
  onSave,
  onSaveEpisodeReview,
  onConfirm,
  onClose,
}: Props) {
  const [showTitle, setShowTitle] = useState(
    () => batch.suggested_metadata?.show_title ?? batch.show_title ?? "",
  );
  const [year, setYear] = useState(
    () => batch.suggested_metadata?.year ?? batch.year ?? "",
  );
  const initialSeason = batch.seasons[0];
  const multiSeason = batch.seasons.length > 1;
  const [seasonNumber, setSeasonNumber] = useState(
    () =>
      String(
        batch.suggested_metadata?.season_number ??
          initialSeason?.season_number ??
          "",
      ),
  );
  const [seasonTitle, setSeasonTitle] = useState(
    () =>
      batch.suggested_metadata?.season_title ?? initialSeason?.season_title ?? "",
  );
  const [patches, setPatches] = useState<TvEpisodeReviewPatch[]>([]);

  const hasBlockingItems = (batch.blocking_review_items ?? []).length > 0;
  const hasPatches = patches.length > 0;

  const yearValid = year.trim() === "" || /^(19|20)\d{2}$/.test(year.trim());
  const seasonValid =
    multiSeason || /^(?:0|[1-9]\d?)$/.test(seasonNumber.trim());
  const showLevelValid = showTitle.trim() !== "" && yearValid && seasonValid;

  const preview = useMemo(() => {
    const root = `TV/Library/${sanitizePathPart(showTitle) || "Unknown TV Show"}`;
    if (multiSeason) {
      return [
        root,
        ...batch.seasons.map(
          (season) =>
            `${root}/Season ${String(season.season_number).padStart(2, "0")}`,
        ),
      ];
    }
    return [`${root}/Season ${seasonNumber.trim().padStart(2, "0")}`];
  }, [batch.seasons, multiSeason, seasonNumber, showTitle]);

  const handleShowLevelSave = () => {
    if (!showLevelValid) return;
    void onSave({
      show_title: showTitle.trim(),
      season_number: multiSeason ? null : Number(seasonNumber),
      year: year.trim() || null,
      season_title: multiSeason ? null : seasonTitle.trim() || null,
    });
  };

  const handleEpisodeReviewSave = () => {
    void onSaveEpisodeReview({
      show_title: showTitle.trim() || null,
      year: year.trim() || null,
      patches,
      confirm_non_blocking_warnings: false,
    });
  };

  return (
    <div className="modal-backdrop" role="presentation" onMouseDown={onClose}>
      <div
        className="metadata-editor"
        onMouseDown={(event) => event.stopPropagation()}
      >
        {/* Header */}
        <div className="metadata-editor__header">
          <div>
            <h2>Review TV show</h2>
            <p>
              Batch {batch.id} · {batch.season_count} season
              {batch.season_count !== 1 ? "s" : ""} · {batch.episode_count}{" "}
              episode{batch.episode_count !== 1 ? "s" : ""}
            </p>
          </div>
          <button
            type="button"
            className="btn-sm"
            title="Close"
            onClick={onClose}
          >
            <i className="ti ti-x" />
          </button>
        </div>

        {/* Show-level fields */}
        <label>
          <span>Show title</span>
          <input
            value={showTitle}
            onChange={(event) => setShowTitle(event.target.value)}
            autoFocus
          />
        </label>
        {!multiSeason && (
          <label>
            <span>Season number</span>
            <input
              type="number"
              min="0"
              max="99"
              value={seasonNumber}
              onChange={(event) => setSeasonNumber(event.target.value)}
            />
          </label>
        )}
        <label>
          <span>Year (optional)</span>
          <input
            value={year}
            maxLength={4}
            onChange={(event) => setYear(event.target.value)}
          />
        </label>
        {!multiSeason && (
          <label>
            <span>Season title (optional)</span>
            <input
              value={seasonTitle}
              onChange={(event) => setSeasonTitle(event.target.value)}
            />
          </label>
        )}

        {/* Validation errors */}
        {!yearValid && (
          <p className="metadata-editor__error">
            Year must be a four-digit year.
          </p>
        )}
        {!multiSeason && !seasonValid && (
          <p className="metadata-editor__error">
            Season must be between 0 and 99.
          </p>
        )}

        {/* Destination preview */}
        <div className="metadata-editor__preview">
          <span>Destination preview</span>
          <div>
            {preview.map((path) => (
              <code key={path}>{path}</code>
            ))}
          </div>
        </div>

        {/* Episode repair panel — only shown when there are blocking or warning items */}
        {(hasBlockingItems || (batch.non_blocking_review_items ?? []).length > 0) && (
          <TvEpisodeReviewPanel
            batch={batch}
            patches={patches}
            onPatchChange={setPatches}
          />
        )}

        {/* Clean path — no blocking items, no patches needed */}
        {!hasBlockingItems && !hasPatches && !batch.review_confirmed && (
          <div className="tv-editor__confirm-area">
            <button
              type="button"
              className="btn btn--green"
              disabled={saving}
              onClick={() => void onConfirm()}
            >
              <i
                className={`ti ti-${saving ? "loader-2 spinner" : "checks"}`}
              />
              Confirm parsed episodes
            </button>
          </div>
        )}

        {/* Action bar */}
        <div className="metadata-editor__actions">
          <button
            type="button"
            className="btn"
            disabled={saving}
            onClick={onClose}
          >
            Cancel
          </button>

          {/* Show-level save — only useful when there are no blocking items or the show title needs fixing */}
          {!hasPatches && (
            <button
              type="button"
              className="btn"
              disabled={saving || !showLevelValid}
              onClick={handleShowLevelSave}
            >
              <i
                className={`ti ti-${saving ? "loader-2 spinner" : "device-floppy"}`}
              />
              Save show info
            </button>
          )}

          {/* Episode review save — primary action when patches exist */}
          {hasPatches && (
            <button
              type="button"
              className="btn btn--green"
              disabled={saving || !showLevelValid}
              onClick={handleEpisodeReviewSave}
            >
              <i
                className={`ti ti-${saving ? "loader-2 spinner" : "device-floppy"}`}
              />
              Save episode review
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
