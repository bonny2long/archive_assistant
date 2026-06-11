import { useMemo, useState } from "react";
import type { AudiobookMetadataUpdate, BatchSummary } from "../types/archive";

type Props = {
  batch: BatchSummary;
  saving: boolean;
  onSave: (update: AudiobookMetadataUpdate) => Promise<void>;
  onConfirm: () => Promise<void>;
  onClose: () => void;
};

function unknown(value: string): boolean {
  return ["", "unknown", "unknown author", "unknown title", "unkn"].includes(
    value.trim().toLowerCase(),
  );
}

function safePart(value: string): string {
  return value.replace(/[<>:"/\\|?*]/g, "_").trim() || "Unknown";
}

export default function AudiobookMetadataEditor({
  batch,
  saving,
  onSave,
  onConfirm,
  onClose,
}: Props) {
  const [author, setAuthor] = useState(
    () => batch.suggested_metadata?.author ?? batch.author ?? "",
  );
  const [title, setTitle] = useState(
    () => batch.suggested_metadata?.title ?? batch.title ?? "",
  );
  const [year, setYear] = useState(
    () => batch.suggested_metadata?.year ?? batch.year ?? "",
  );
  const [narrator, setNarrator] = useState(
    () => batch.suggested_metadata?.narrator ?? batch.narrator ?? "",
  );
  const [series, setSeries] = useState(
    () => batch.suggested_metadata?.series ?? batch.series ?? "",
  );
  const [seriesIndex, setSeriesIndex] = useState(
    () => batch.suggested_metadata?.series_index ?? batch.series_index ?? "",
  );
  const [format, setFormat] = useState(
    () => batch.suggested_metadata?.format ?? batch.format ?? "MP3",
  );
  const yearValid = year.trim() === "" || /^(19|20)\d{2}$/.test(year.trim());
  const blockers = [
    unknown(author) ? "Author is required." : null,
    unknown(title) ? "Title is required." : null,
    !yearValid ? "Year must be a four-digit year." : null,
  ].filter((value): value is string => Boolean(value));
  const warnings = [
    !year.trim() ? "Year is missing; destination will use Unknown Year." : null,
    !narrator.trim() ? "Narrator is missing." : null,
  ].filter((value): value is string => Boolean(value));
  const valid = blockers.length === 0;
  const preview = useMemo(
    () => `Audiobooks/Library/${safePart(author || "Unknown Author")}/${safePart(`${year || "Unknown Year"} - ${title || "Unknown Title"}`)}`,
    [author, title, year],
  );
  const audioFiles = batch.audio_files ?? [];

  return (
    <div className="modal-backdrop" role="presentation" onMouseDown={onClose}>
      <form
        className="metadata-editor metadata-editor--wide"
        onMouseDown={(event) => event.stopPropagation()}
        onSubmit={(event) => {
          event.preventDefault();
          if (!valid) return;
          void onSave({
            author: author.trim(),
            title: title.trim(),
            year: year.trim() || null,
            narrator: narrator.trim() || null,
            series: series.trim() || null,
            series_index: seriesIndex.trim() || null,
            format: format.trim().toUpperCase() || null,
          });
        }}
      >
        <div className="editor-shell__header">
          <div>
            <h2>Review audiobook</h2>
            <p>
              Batch {batch.id} · {batch.audiobook_file_count ?? 0} audio file(s)
            </p>
          </div>
          <button type="button" className="btn-sm" title="Close" onClick={onClose}>
            <i className="ti ti-x" />
          </button>
        </div>

        <div className="editor-shell__body">
          <div className="movie-editor__context">
            <div>
              <span>Primary audio file</span>
              <strong>{batch.primary_audio_file ?? "Audiobook folder"}</strong>
            </div>
            <div className="movie-editor__counts">
              <span>Chapters: {batch.chapter_count ?? 0}</span>
              <span>Artwork: {batch.artwork_count}</span>
              <span>Sidecars: {batch.ignored_sidecar_count}</span>
            </div>
          </div>

          <div className={`review-summary ${blockers.length ? "review-summary--warning" : "review-summary--clean"}`}>
            <div>
              <strong>{blockers.length ? "Correction required" : "Review available"}</strong>
              <p>
                {blockers.length
                  ? blockers.join(" ")
                  : "Author, title, and optional year are valid."}
              </p>
            </div>
            <span>{blockers.length} blocker(s) · {warnings.length} warning(s)</span>
          </div>

          {warnings.length > 0 && (
            <div className="tv-review-panel__warnings">
              <span>Warnings</span>
              {warnings.map((warning) => (
                <p className="tv-review-panel__warning-row" key={warning}>
                  {warning}
                </p>
              ))}
            </div>
          )}

          <div className="editor-grid">
            <label>
              <span>Author</span>
              <input value={author} onChange={(event) => setAuthor(event.target.value)} autoFocus />
            </label>
            <label>
              <span>Title</span>
              <input value={title} onChange={(event) => setTitle(event.target.value)} />
            </label>
            <label>
              <span>Year optional</span>
              <input value={year} maxLength={4} onChange={(event) => setYear(event.target.value)} />
            </label>
            <label>
              <span>Narrator optional</span>
              <input value={narrator} onChange={(event) => setNarrator(event.target.value)} />
            </label>
            <label>
              <span>Series optional</span>
              <input value={series} onChange={(event) => setSeries(event.target.value)} />
            </label>
            <label>
              <span>Series index optional</span>
              <input value={seriesIndex} onChange={(event) => setSeriesIndex(event.target.value)} />
            </label>
            <label>
              <span>Format</span>
              <input value={format} onChange={(event) => setFormat(event.target.value)} />
            </label>
          </div>

          <div className="metadata-editor__preview">
            <span>Destination preview</span>
            <div><code>{preview}</code></div>
          </div>

          {audioFiles.length > 0 && (
            <section className="track-preview">
              <div className="track-preview__header">
                <h3>Audio preview</h3>
                <span>Showing {Math.min(audioFiles.length, 10)} of {audioFiles.length}</span>
              </div>
              <div className="track-preview__table">
                <table>
                  <thead><tr><th>#</th><th>Audio file</th></tr></thead>
                  <tbody>
                    {audioFiles.slice(0, 10).map((file, index) => (
                      <tr key={file}><td>{index + 1}</td><td><code>{file}</code></td></tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </section>
          )}

          {valid && !batch.review_confirmed && (
            <button type="button" className="btn btn--compact" disabled={saving} onClick={() => void onConfirm()}>
              Confirm audiobook metadata
            </button>
          )}
        </div>

        <div className="editor-shell__footer">
          <button type="button" className="btn" disabled={saving} onClick={onClose}>Cancel</button>
          <button type="submit" className="btn btn--green" disabled={saving || !valid}>
            Save audiobook
          </button>
        </div>
      </form>
    </div>
  );
}
