import { useMemo, useState } from "react";
import type { BatchSummary, MovieMetadataUpdate } from "../types/archive";
import ReviewIssuesPanel from "./ReviewIssuesPanel";

type Props = {
  batch: BatchSummary;
  saving: boolean;
  onSave: (update: MovieMetadataUpdate) => Promise<void>;
  onConfirm: () => Promise<void>;
  onClose: () => void;
};

function sanitizePathPart(value: string): string {
  return value.replace(/[<>:"/\\|?*]/g, "_").trim();
}

export default function MovieMetadataEditor({
  batch,
  saving,
  onSave,
  onConfirm,
  onClose,
}: Props) {
  const [title, setTitle] = useState(
    () => batch.suggested_metadata?.title ?? batch.title ?? "",
  );
  const [year, setYear] = useState(
    () => batch.suggested_metadata?.year ?? batch.year ?? "",
  );
  const [edition, setEdition] = useState(
    () => batch.suggested_metadata?.edition ?? batch.edition ?? "",
  );
  const [format, setFormat] = useState(
    () => batch.suggested_metadata?.format ?? batch.format ?? "",
  );

  const yearValid = year.trim() === "" || /^(19|20)\d{2}$/.test(year.trim());
  const valid = title.trim() !== "" && yearValid;
  const preview = useMemo(
    () => `Movies/Library/${sanitizePathPart(`${year.trim() || "Unknown Year"} - ${title}`)}`,
    [title, year],
  );

  return (
    <div className="modal-backdrop" role="presentation" onMouseDown={onClose}>
      <form
        className="metadata-editor metadata-editor--wide"
        onMouseDown={(event) => event.stopPropagation()}
        onSubmit={(event) => {
          event.preventDefault();
          if (!valid) return;
          void onSave({
            title: title.trim(),
            year: year.trim() || null,
            edition: edition.trim() || null,
            format: format.trim() || null,
          });
        }}
      >
        {/* ── Header ── */}
        <div className="editor-shell__header">
          <div>
            <h2>Correct movie metadata</h2>
            <p>Batch {batch.id}. Saving updates the movie destination plan.</p>
          </div>
          <button type="button" className="btn-sm" title="Close" onClick={onClose}>
            <i className="ti ti-x" />
          </button>
        </div>

        {/* ── Body ── */}
        <div className="editor-shell__body">
          <div className="movie-editor__context">
            <div>
              <span>Detected video file</span>
              <strong>{batch.primary_video_file ?? "Unknown video file"}</strong>
            </div>
            <div className="movie-editor__counts">
              <span>Artwork: {batch.artwork_count}</span>
              <span>Subtitles: {batch.subtitle_count}</span>
              <span>Ignored sidecars: {batch.ignored_sidecar_count}</span>
            </div>
          </div>
          <ReviewIssuesPanel
            batch={batch}
            saving={saving}
            confirmLabel="Confirm movie metadata"
            onConfirm={onConfirm}
          />

          <div className="editor-grid editor-grid--full">
            <label>
              <span>Title</span>
              <input value={title} onChange={(event) => setTitle(event.target.value)} autoFocus />
            </label>
          </div>
          <div className="editor-grid">
            <label>
              <span>Year</span>
              <input value={year} maxLength={4} onChange={(event) => setYear(event.target.value)} />
            </label>
            <label>
              <span>Edition / Version optional</span>
              <input value={edition} onChange={(event) => setEdition(event.target.value)} />
            </label>
          </div>
          <div className="editor-grid editor-grid--full">
            <label>
              <span>Format</span>
              <input value={format} onChange={(event) => setFormat(event.target.value)} />
            </label>
          </div>

          <div className="metadata-editor__preview">
            <span>Destination preview</span>
            <div><code>{preview}</code></div>
          </div>
          {!year.trim() && (
            <p className="metadata-editor__warning">
              Movie year missing. Review before approval.
            </p>
          )}
          {!yearValid && (
            <p className="metadata-editor__error">Year must be a four-digit year.</p>
          )}
        </div>

        {/* ── Footer ── */}
        <div className="editor-shell__footer">
          <button type="button" className="btn" disabled={saving} onClick={onClose}>Cancel</button>
          <button type="submit" className="btn btn--green" disabled={saving || !valid}>
            <i className={`ti ti-${saving ? "loader-2 spinner" : "device-floppy"}`} />
            Save movie
          </button>
        </div>
      </form>
    </div>
  );
}
