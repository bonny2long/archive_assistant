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
  const yearValid = year.trim() === "" || /^(19|20)\d{2}$/.test(year.trim());
  const valid = showTitle.trim() !== "" && yearValid;
  const preview = useMemo(
    () => `TV/Library/${sanitizePathPart(showTitle) || "Unknown TV Show"}`,
    [showTitle],
  );

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
            year: year.trim() || null,
          });
        }}
      >
        <div className="metadata-editor__header">
          <div>
            <h2>Correct TV metadata</h2>
            <p>Batch {batch.id}. Episode numbering remains read-only in this update.</p>
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
        <label>
          <span>Year optional</span>
          <input
            value={year}
            maxLength={4}
            onChange={(event) => setYear(event.target.value)}
          />
        </label>
        <div className="metadata-editor__preview">
          <span>Destination preview</span>
          <div><code>{preview}</code></div>
        </div>
        {!yearValid && (
          <p className="metadata-editor__error">Year must be a four-digit year.</p>
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
