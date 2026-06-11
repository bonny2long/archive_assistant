import { useMemo, useState } from "react";
import type { BatchSummary, BookMetadataUpdate } from "../types/archive";
import ReviewIssuesPanel from "./ReviewIssuesPanel";

type Props = {
  batch: BatchSummary;
  saving: boolean;
  onSave: (update: BookMetadataUpdate) => Promise<void>;
  onConfirm: () => Promise<void>;
  onClose: () => void;
};

function safePart(value: string): string {
  return value.replace(/[<>:"/\\|?*]/g, "_").trim();
}

function unknown(value: string): boolean {
  return ["", "unknown", "unknown author", "unknown title", "unkn"].includes(
    value.trim().toLowerCase(),
  );
}

export default function BookMetadataEditor({
  batch,
  saving,
  onSave,
  onConfirm,
  onClose,
}: Props) {
  const [title, setTitle] = useState(
    () => batch.suggested_metadata?.title ?? batch.title ?? "",
  );
  const [author, setAuthor] = useState(
    () => batch.suggested_metadata?.author ?? batch.author ?? "",
  );
  const [year, setYear] = useState(
    () => batch.suggested_metadata?.year ?? batch.year ?? "",
  );
  const [format, setFormat] = useState(
    () => batch.suggested_metadata?.format ?? batch.format ?? "EPUB",
  );
  const yearValid = year.trim() === "" || /^(19|20)\d{2}$/.test(year.trim());
  const valid = !unknown(title) && !unknown(author) && yearValid;
  const preview = useMemo(
    () => `Books/${safePart(format.toUpperCase() || "EPUB")}/${safePart(author || "Unknown Author")}/${safePart(`${year || "Unknown Year"} - ${title || "Unknown Title"}`)}`,
    [author, format, title, year],
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
            author: author.trim(),
            year: year.trim() || null,
            format: format.trim().toUpperCase() || null,
          });
        }}
      >
        <div className="editor-shell__header">
          <div>
            <h2>Correct book metadata</h2>
            <p>Batch {batch.id}. EPUB and PDF files move without content changes.</p>
          </div>
          <button type="button" className="btn-sm" title="Close" onClick={onClose}>
            <i className="ti ti-x" />
          </button>
        </div>
        <div className="editor-shell__body">
          <div className="movie-editor__context">
            <div>
              <span>Primary book file</span>
              <strong>{batch.primary_book_file ?? "Unknown book file"}</strong>
            </div>
            <div className="movie-editor__counts">
              <span>Book files: {batch.book_file_count ?? 0}</span>
              <span>Artwork: {batch.artwork_count}</span>
              <span>Sidecars: {batch.ignored_sidecar_count}</span>
            </div>
          </div>
          <ReviewIssuesPanel
            batch={batch}
            saving={saving}
            confirmLabel="Confirm book metadata"
            onConfirm={onConfirm}
          />
          <div className="editor-grid">
            <label>
              <span>Title</span>
              <input value={title} onChange={(event) => setTitle(event.target.value)} autoFocus />
            </label>
            <label>
              <span>Author</span>
              <input value={author} onChange={(event) => setAuthor(event.target.value)} />
            </label>
            <label>
              <span>Year optional</span>
              <input value={year} maxLength={4} onChange={(event) => setYear(event.target.value)} />
            </label>
            <label>
              <span>Format</span>
              <select value={format} onChange={(event) => setFormat(event.target.value)}>
                <option value="EPUB">EPUB</option>
                <option value="PDF">PDF</option>
              </select>
            </label>
          </div>
          <div className="metadata-editor__preview">
            <span>Destination preview</span>
            <div><code>{preview}</code></div>
          </div>
          {!yearValid && <p className="metadata-editor__error">Year must be a four-digit year.</p>}
        </div>
        <div className="editor-shell__footer">
          <button type="button" className="btn" disabled={saving} onClick={onClose}>Cancel</button>
          <button type="submit" className="btn btn--green" disabled={saving || !valid}>
            <i className={`ti ti-${saving ? "loader-2 spinner" : "device-floppy"}`} />
            Save book
          </button>
        </div>
      </form>
    </div>
  );
}
