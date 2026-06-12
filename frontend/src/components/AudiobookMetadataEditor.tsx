import { useMemo, useState } from "react";
import type { AudiobookMetadataUpdate, BatchSummary } from "../types/archive";
import MetadataSuggestionChips from "./MetadataSuggestionChips";

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
  const [showAllChapters, setShowAllChapters] = useState(false);
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
  const candidates = batch.metadata_candidates ?? {};
  const chapterCandidates = batch.chapter_candidates ?? [];
  const chapterRows = chapterCandidates.length > 0
    ? chapterCandidates
    : audioFiles.map((file, index) => ({
        source_file: file,
        current_name: file,
        suggested_title: "",
        source: "filename_order",
        source_label: "Filename order",
        confidence: 0,
        confidence_label: "low" as const,
        track_number: index + 1,
        disc_number: null,
      }));
  const visibleChapterRows = showAllChapters
    ? chapterRows
    : chapterRows.slice(0, 25);

  return (
    <div className="modal-backdrop" role="presentation" onMouseDown={onClose}>
      <form
        className="metadata-editor metadata-editor--wide audiobook-editor"
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
              <span>Audio files: {batch.audiobook_file_count ?? 0}</span>
              <span>Discs: {batch.detected_disc_count ?? 0}</span>
              <span>Chapter suggestions: {chapterCandidates.length}</span>
              <span>Generic tags hidden: {batch.generic_audio_tag_count ?? 0}</span>
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

          <section className="audiobook-editor__metadata">
            <div className="audiobook-editor__section-heading">
              <div>
                <strong>Main metadata</strong>
                <p>Suggestions fill fields only. Save remains the confirmation step.</p>
              </div>
              {(batch.candidate_warning_count ?? 0) > 0 && (
                <span>{batch.candidate_warning_count} generic candidate(s) filtered</span>
              )}
            </div>
            <div className="editor-grid audiobook-editor__grid">
            <label>
              <span>Author</span>
              <input value={author} onChange={(event) => setAuthor(event.target.value)} autoFocus />
              <MetadataSuggestionChips label="Author" field="author" candidates={candidates.author ?? []} currentValue={author} onApply={setAuthor} />
            </label>
            <label>
              <span>Title</span>
              <input value={title} onChange={(event) => setTitle(event.target.value)} />
              <MetadataSuggestionChips label="Title" field="title" candidates={candidates.title ?? []} currentValue={title} onApply={setTitle} />
            </label>
            <label>
              <span>Year optional</span>
              <input value={year} maxLength={4} onChange={(event) => setYear(event.target.value)} />
              <MetadataSuggestionChips label="Year" field="year" candidates={candidates.year ?? []} currentValue={year} onApply={setYear} />
            </label>
            <label>
              <span>Narrator optional</span>
              <input value={narrator} onChange={(event) => setNarrator(event.target.value)} />
              <MetadataSuggestionChips label="Narrator" field="narrator" candidates={candidates.narrator ?? []} currentValue={narrator} onApply={setNarrator} />
            </label>
            <label>
              <span>Series optional</span>
              <input value={series} onChange={(event) => setSeries(event.target.value)} />
              <MetadataSuggestionChips label="Series" field="series" candidates={candidates.series ?? []} currentValue={series} onApply={setSeries} />
            </label>
            <label>
              <span>Series index optional</span>
              <input value={seriesIndex} onChange={(event) => setSeriesIndex(event.target.value)} />
              <MetadataSuggestionChips label="Series index" field="series_index" candidates={candidates.series_index ?? []} currentValue={seriesIndex} onApply={setSeriesIndex} />
            </label>
            <label>
              <span>Format</span>
              <input value={format} onChange={(event) => setFormat(event.target.value)} />
            </label>
            </div>
          </section>

          <div className="metadata-editor__preview">
            <span>Destination preview</span>
            <div><code>{preview}</code></div>
          </div>

          {chapterRows.length > 0 && (
            <section className="track-preview">
              <div className="track-preview__header">
                <div>
                  <h3>Chapter preview</h3>
                  <span>
                    {chapterRows.length} audio file(s) · {chapterCandidates.length} title suggestion(s) · no files will be renamed
                  </span>
                </div>
                {chapterRows.length > 25 && (
                  <button
                    type="button"
                    className="btn-sm"
                    onClick={() => setShowAllChapters((value) => !value)}
                  >
                    {showAllChapters ? "Show first 25" : `Show all chapters (${chapterRows.length})`}
                  </button>
                )}
              </div>
              <div className="track-preview__table">
                <table>
                  <thead><tr><th>Disc</th><th>Track</th><th>Current file</th><th>Suggested chapter</th><th>Confidence</th></tr></thead>
                  <tbody>
                    {visibleChapterRows.map((candidate, index) => (
                      <tr key={`${candidate.source_file}:${candidate.suggested_title}`}>
                        <td>{candidate.disc_number ?? "—"}</td>
                        <td>{candidate.track_number ?? index + 1}</td>
                        <td><code>{candidate.source_file}</code></td>
                        <td>{candidate.suggested_title || "No embedded chapter title"}</td>
                        <td><small>{candidate.confidence_label}</small></td>
                      </tr>
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
