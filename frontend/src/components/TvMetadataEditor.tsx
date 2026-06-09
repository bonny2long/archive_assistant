import { useMemo, useState } from "react";
import type { BatchSummary, TvMetadataUpdate } from "../types/archive";

type Props = {
  batch: BatchSummary;
  saving: boolean;
  onSave: (update: TvMetadataUpdate) => Promise<void>;
  onClose: () => void;
};

function sanitizePathPart(value: string): string {
  return value.replace(/[<>:"/\\|?*]/g, "_").trim();
}

export default function TvMetadataEditor({
  batch,
  saving,
  onSave,
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
    () => String(
      batch.suggested_metadata?.season_number
      ?? initialSeason?.season_number
      ?? "",
    ),
  );
  const [seasonTitle, setSeasonTitle] = useState(
    () => batch.suggested_metadata?.season_title ?? initialSeason?.season_title ?? "",
  );
  const yearValid = year.trim() === "" || /^(19|20)\d{2}$/.test(year.trim());
  const seasonValid = multiSeason
    || /^(?:0|[1-9]\d?)$/.test(seasonNumber.trim());
  const valid = showTitle.trim() !== "" && yearValid && seasonValid;
  const preview = useMemo(() => {
    const root = `TV/Library/${sanitizePathPart(showTitle) || "Unknown TV Show"}`;
    if (multiSeason) {
      return [
        root,
        ...batch.seasons.map(
          (season) => `${root}/Season ${String(season.season_number).padStart(2, "0")}`,
        ),
      ];
    }
    return [
      `${root}/Season ${seasonNumber.trim().padStart(2, "0")}`,
    ];
  }, [batch.seasons, multiSeason, seasonNumber, showTitle]);
  const episodes = batch.seasons.flatMap((season) => season.episodes);

  return (
    <div className="modal-backdrop" role="presentation" onMouseDown={onClose}>
      <form
        className="metadata-editor"
        onMouseDown={(event) => event.stopPropagation()}
        onSubmit={(event) => {
          event.preventDefault();
          if (!valid) return;
          void onSave({
            show_title: showTitle.trim(),
            season_number: multiSeason ? null : Number(seasonNumber),
            year: year.trim() || null,
            season_title: multiSeason ? null : seasonTitle.trim() || null,
          });
        }}
      >
        <div className="metadata-editor__header">
          <div>
            <h2>Correct TV metadata</h2>
            <p>Batch {batch.id}. Episode numbers remain read-only.</p>
          </div>
          <button type="button" className="btn-sm" title="Close" onClick={onClose}>
            <i className="ti ti-x" />
          </button>
        </div>
        <div className="movie-editor__context">
          <div className="movie-editor__counts">
            <span>Seasons: {batch.season_count}</span>
            <span>Episodes: {batch.episode_count}</span>
            <span>Subtitles: {batch.subtitle_count}</span>
            <span>Artwork: {batch.artwork_count}</span>
            <span>Ignored sidecars: {batch.ignored_sidecar_count}</span>
          </div>
        </div>
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
          <span>Year optional</span>
          <input
            value={year}
            maxLength={4}
            onChange={(event) => setYear(event.target.value)}
          />
        </label>
        {!multiSeason && (
          <label>
            <span>Season title optional</span>
            <input
              value={seasonTitle}
              onChange={(event) => setSeasonTitle(event.target.value)}
            />
          </label>
        )}
        {multiSeason && (
          <div className="tv-editor__seasons">
            <span>Season summary</span>
            {batch.seasons.map((season) => (
              <code key={season.season_number}>
                Season {String(season.season_number).padStart(2, "0")} · {season.episode_count} episodes
              </code>
            ))}
          </div>
        )}
        <div className="metadata-editor__preview">
          <span>Destination preview</span>
          <div>
            {preview.map((path) => <code key={path}>{path}</code>)}
          </div>
        </div>
        {!yearValid && (
          <p className="metadata-editor__error">Year must be a four-digit year.</p>
        )}
        {!multiSeason && !seasonValid && (
          <p className="metadata-editor__error">Season must be between 0 and 99.</p>
        )}
        {episodes.length > 0 && (
          <div className="tv-editor__episodes">
            <span>Episode preview</span>
            {episodes.slice(0, 10).map((episode) => (
              <code key={`${episode.episode_code}-${episode.source_file}`}>
                {episode.episode_code ?? "Episode"} - {episode.episode_title ?? episode.source_file}
              </code>
            ))}
          </div>
        )}
        <div className="metadata-editor__actions">
          <button type="button" className="btn" disabled={saving} onClick={onClose}>
            Cancel
          </button>
          <button type="submit" className="btn btn--green" disabled={saving || !valid}>
            <i className={`ti ti-${saving ? "loader-2 spinner" : "device-floppy"}`} />
            Save TV show
          </button>
        </div>
      </form>
    </div>
  );
}
