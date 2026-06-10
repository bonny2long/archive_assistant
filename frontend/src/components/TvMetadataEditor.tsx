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
  const hasNonBlocking = (batch.non_blocking_review_items ?? []).length > 0;
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
        className="metadata-editor metadata-editor--tv"
        onMouseDown={(e) => e.stopPropagation()}
      >
        {/* ── Header ── */}
        <div className="tv-editor__header">
          <div>
            <h2>Review TV show</h2>
            <p>
              Batch {batch.id} · {batch.season_count} season
              {batch.season_count !== 1 ? "s" : ""} · {batch.episode_count}{" "}
              episode{batch.episode_count !== 1 ? "s" : ""}
              {batch.special_episode_count != null && batch.special_episode_count > 0 && (
                <> · {batch.special_episode_count} special</>
              )}
              {batch.unresolved_video_count != null && batch.unresolved_video_count > 0 && (
                <> · {batch.unresolved_video_count} unresolved</>
              )}
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

        {/* ── Body: left + right ── */}
        <div className="tv-editor__body">

          {/* LEFT: show-level fields + season overview */}
          <div className="tv-editor__left">
            <label>
              <span>Show title</span>
              <input
                value={showTitle}
                onChange={(e) => setShowTitle(e.target.value)}
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
                  onChange={(e) => setSeasonNumber(e.target.value)}
                />
              </label>
            )}

            <label>
              <span>Year (optional)</span>
              <input
                value={year}
                maxLength={4}
                onChange={(e) => setYear(e.target.value)}
              />
            </label>

            {!multiSeason && (
              <label>
                <span>Season title (optional)</span>
                <input
                  value={seasonTitle}
                  onChange={(e) => setSeasonTitle(e.target.value)}
                />
              </label>
            )}

            {!yearValid && (
              <p className="tv-editor__error">Year must be a four-digit year.</p>
            )}
            {!multiSeason && !seasonValid && (
              <p className="tv-editor__error">Season must be between 0 and 99.</p>
            )}

            {/* Destination preview */}
            <div className="tv-editor__dest-preview">
              <span>Destination</span>
              {preview.map((path) => (
                <code key={path}>{path}</code>
              ))}
            </div>

            {/* Season summary + expand */}
            <TvSeasonSidebar batch={batch} />
          </div>

          {/* RIGHT: repair cards */}
          <div className="tv-editor__right">
            <TvEpisodeReviewPanel
              batch={batch}
              patches={patches}
              onPatchChange={setPatches}
            />
            {!hasBlockingItems && !hasNonBlocking && (
              <div className="tv-editor__confirm-area">
                {!batch.review_confirmed && (
                  <button
                    type="button"
                    className="btn btn--green"
                    disabled={saving}
                    onClick={() => void onConfirm()}
                  >
                    <i className={`ti ti-${saving ? "loader-2 spinner" : "checks"}`} />
                    Confirm parsed episodes
                  </button>
                )}
              </div>
            )}
          </div>
        </div>

        {/* ── Footer ── */}
        <div className="tv-editor__footer">
          <button
            type="button"
            className="btn"
            disabled={saving}
            onClick={onClose}
          >
            Cancel
          </button>

          {!hasPatches && (
            <button
              type="button"
              className="btn"
              disabled={saving || !showLevelValid}
              onClick={handleShowLevelSave}
            >
              <i className={`ti ti-${saving ? "loader-2 spinner" : "device-floppy"}`} />
              Save show info
            </button>
          )}

          {hasPatches && (
            <button
              type="button"
              className="btn btn--green"
              disabled={saving || !showLevelValid}
              onClick={handleEpisodeReviewSave}
            >
              <i className={`ti ti-${saving ? "loader-2 spinner" : "device-floppy"}`} />
              Save episode review
            </button>
          )}
        </div>
      </div>
    </div>
  );
}

// ── Season sidebar (left panel, below fields) ────────────────────────────────

type SeasonSidebarProps = { batch: BatchSummary };

function TvSeasonSidebar({ batch }: SeasonSidebarProps) {
  const [expanded, setExpanded] = useState(false);

  const issuesByCode = new Set(
    (batch.blocking_review_items ?? [])
      .filter((i) => i.episode_code)
      .map((i) => i.episode_code),
  );
  const issuesByFile = new Set(
    (batch.blocking_review_items ?? [])
      .filter((i) => i.file_name)
      .map((i) => i.file_name),
  );

  return (
    <div className="tv-season-preview">
      <span className="tv-season-preview__label">Season overview</span>
      <div className="tv-season-preview__list">
        {batch.seasons.map((season) => {
          const issueCount = season.episodes.filter(
            (ep) =>
              issuesByFile.has(ep.source_file) ||
              (ep.episode_code != null && issuesByCode.has(ep.episode_code)),
          ).length;
          return (
            <div
              key={season.season_number ?? "specials"}
              className="tv-season-preview__row"
            >
              <code>
                S{season.season_number != null
                  ? String(season.season_number).padStart(2, "0")
                  : "??"}
              </code>
              <span>{season.episode_count} ep</span>
              {issueCount > 0 ? (
                <span className="tv-season-preview__issue">
                  · {issueCount} issue{issueCount !== 1 ? "s" : ""}
                </span>
              ) : (
                <span className="tv-season-preview__clean">· clean</span>
              )}
            </div>
          );
        })}
      </div>

      {batch.special_episode_count != null && batch.special_episode_count > 0 && (
        <div className="tv-season-preview__ignored">
          <i className="ti ti-disc" />
          <span>Specials / OADs / OVAs: {batch.special_episode_count}</span>
          <small>Review in the right panel</small>
        </div>
      )}

      {batch.unresolved_video_count != null && batch.unresolved_video_count > 0 && (
        <div className="tv-season-preview__ignored">
          <i className="ti ti-question-mark" />
          <span>Unresolved videos: {batch.unresolved_video_count}</span>
          <small>Requires classification before approval</small>
        </div>
      )}

      {batch.ignored_corrupt_video_count > 0 && (
        <div className="tv-season-preview__ignored">
          <i className="ti ti-file-x" />
          <span>
            Ignored corrupt videos: {batch.ignored_corrupt_video_count}
          </span>
          <small>Preserved in _INGEST for cleanup review</small>
        </div>
      )}

      {batch.episode_count > 0 && (
        <button
          type="button"
          className="btn-sm"
          onClick={() => setExpanded((v) => !v)}
        >
          {expanded ? "Hide episodes" : "View all episodes"}
        </button>
      )}

      {expanded && (
        <div className="tv-episode-readonly-list">
          {batch.seasons.map((season) =>
            season.episodes.map((ep) => (
              <code
                key={`${ep.source_file}||${ep.relative_source ?? ""}`}
                className="tv-episode-readonly-list__row"
              >
                {ep.episode_code ?? "—"} · {ep.episode_title ?? ep.source_file}
              </code>
            )),
          )}
        </div>
      )}
    </div>
  );
}
