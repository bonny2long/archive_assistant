import { useMemo, useState } from "react";
import type { AudiobookMetadataUpdate, BatchSummary } from "../types/archive";
import MetadataSuggestionChips from "./MetadataSuggestionChips";
import MetadataAssistStaleWarning from "./MetadataAssistStaleWarning";
import { destinationTitle } from "../utils/titleDisplay";

type Props = {
  batch: BatchSummary;
  saving: boolean;
  onSave: (update: AudiobookMetadataUpdate) => Promise<void>;
  onConfirm: () => Promise<void>;
  onClose: () => void;
};

function unknown(value: string): boolean {
  return [
    "",
    "unknown",
    "unknown author",
    "unknown narrator",
    "unknown title",
    "unknown year",
    "unkn",
  ].includes(
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
  const [acceptedUnknownAuthor, setAcceptedUnknownAuthor] = useState(
    Boolean(batch.accepted_unknown_author),
  );
  const [acceptedUnknownYear, setAcceptedUnknownYear] = useState(
    Boolean(batch.accepted_unknown_year),
  );
  const [acceptedUnknownNarrator, setAcceptedUnknownNarrator] = useState(
    Boolean(batch.accepted_unknown_narrator),
  );
  const [lookupLater, setLookupLater] = useState(
    Boolean(batch.lookup_later),
  );
  const [showAllChapters, setShowAllChapters] = useState(false);
  const [repairAuthor, setRepairAuthor] = useState("");
  const [repairNarrator, setRepairNarrator] = useState("");
  const [repairYear, setRepairYear] = useState("");
  const normalizedYear = year.trim();
  const yearUnknown = unknown(normalizedYear);
  const narratorUnknown = unknown(narrator);
  const yearValid = (
    normalizedYear === ""
    || /^(19|20)\d{2}$/.test(normalizedYear)
    || (yearUnknown && acceptedUnknownYear)
  );
  const blockers = [
    unknown(author) && !acceptedUnknownAuthor
      ? "Author is required or must be explicitly accepted as unknown."
      : null,
    unknown(title) ? "Title is required." : null,
    !yearValid ? "Year must be a four-digit year." : null,
  ].filter((value): value is string => Boolean(value));
  const warnings = [
    yearUnknown
      ? acceptedUnknownYear
        ? "Unknown year accepted."
        : "Year is missing; destination will use Unknown Year."
      : null,
    narratorUnknown
      ? acceptedUnknownNarrator
        ? "Unknown narrator accepted."
        : "Narrator is missing."
      : null,
    unknown(author) && acceptedUnknownAuthor
      ? "Unknown author accepted."
      : null,
    lookupLater ? "Metadata marked for later lookup." : null,
  ].filter((value): value is string => Boolean(value));
  const valid = blockers.length === 0;
  const preview = useMemo(
    () => `Audiobooks/Library/${safePart(author || "Unknown Author")}/${safePart(`${year || "Unknown Year"} - ${destinationTitle(title || "Unknown Title")}`)}`,
    [author, title, year],
  );
  const audioFiles = batch.audio_files ?? [];
  const candidates = batch.metadata_candidates ?? {};
  const chapterCandidates = batch.chapter_candidates ?? [];
  const containedBooks = batch.contained_books ?? [];
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
        ignored: true,
        generic: true,
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
            author: unknown(author) ? "Unknown Author" : author.trim(),
            title: title.trim(),
            year: yearUnknown ? null : normalizedYear,
            narrator: narratorUnknown ? null : narrator.trim(),
            series: series.trim() || null,
            series_index: seriesIndex.trim() || null,
            format: format.trim().toUpperCase() || null,
            accepted_unknown_author: acceptedUnknownAuthor,
            accepted_unknown_year: acceptedUnknownYear,
            accepted_unknown_narrator: acceptedUnknownNarrator,
            lookup_later: lookupLater,
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
              <span>
                Artwork: {batch.artwork_count} matched
                {batch.artwork_files?.[0]
                  ? ` · ${batch.artwork_files[0]}`
                  : ""}
              </span>
              <span>Sidecars: {batch.ignored_sidecar_count}</span>
            </div>
          </div>

          {containedBooks.length > 0 && (
            <section className="audiobook-set-preview">
              <div>
                <strong>
                  Detected multi-book audiobook set: {containedBooks.length} books
                </strong>
                <p>Preview only. Files remain one audiobook batch.</p>
              </div>
              <ol>
                {containedBooks.map((book) => (
                  <li key={`${book.series_index}:${book.title}`}>
                    <strong>{book.series_index}</strong>
                    <span>{book.title}</span>
                  </li>
                ))}
              </ol>
            </section>
          )}

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
          <MetadataAssistStaleWarning batch={batch} />
          <p className="metadata-assist-copy">
            Metadata suggestions are assistive only. Suggestions fill fields only.
            Save confirms metadata. Move approved files only after review.
          </p>

          <section className="acceptance-controls">
            <div>
              <strong>Accepted unknown metadata</strong>
              <p>These choices are explicit and remain visible in move manifests.</p>
            </div>
            <div className="acceptance-controls__buttons">
              <button
                type="button"
                className={`btn-sm${acceptedUnknownAuthor ? " btn-sm--active" : ""}`}
                onClick={() => {
                  setAcceptedUnknownAuthor((value) => {
                    const next = !value;
                    if (next && unknown(author)) setAuthor("Unknown Author");
                    return next;
                  });
                }}
              >
                {acceptedUnknownAuthor ? "Unknown Author Accepted" : "Accept Unknown Author"}
              </button>
              <button
                type="button"
                className={`btn-sm${acceptedUnknownNarrator ? " btn-sm--active" : ""}`}
                onClick={() => {
                  setAcceptedUnknownNarrator((value) => {
                    const next = !value;
                    if (next && narratorUnknown) {
                      setNarrator("Unknown Narrator");
                    }
                    return next;
                  });
                }}
              >
                {acceptedUnknownNarrator ? "Unknown Narrator Accepted" : "Accept Unknown Narrator"}
              </button>
              <button
                type="button"
                className={`btn-sm${acceptedUnknownYear ? " btn-sm--active" : ""}`}
                onClick={() => {
                  setAcceptedUnknownYear((value) => {
                    const next = !value;
                    if (next && yearUnknown) setYear("Unknown Year");
                    return next;
                  });
                }}
              >
                {acceptedUnknownYear ? "Unknown Year Accepted" : "Accept Unknown Year"}
              </button>
              <button
                type="button"
                className={`btn-sm${lookupLater ? " btn-sm--active" : ""}`}
                onClick={() => setLookupLater((value) => !value)}
              >
                {lookupLater ? "Lookup Later Marked" : "Lookup Later"}
              </button>
            </div>
          </section>

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
                <span>{batch.generic_audio_tag_count ?? batch.candidate_warning_count} generic candidate(s) filtered</span>
              )}
            </div>
            <div className="audiobook-editor__helpers">
              <label>
                <span>Manual author</span>
                <input value={repairAuthor} onChange={(event) => setRepairAuthor(event.target.value)} />
                <button type="button" className="btn-sm" disabled={!repairAuthor.trim()} onClick={() => setAuthor(repairAuthor.trim().replace(/\s+/g, " "))}>Apply author</button>
              </label>
              <label>
                <span>Manual narrator</span>
                <input value={repairNarrator} onChange={(event) => setRepairNarrator(event.target.value)} />
                <button type="button" className="btn-sm" disabled={!repairNarrator.trim()} onClick={() => setNarrator(repairNarrator.trim().replace(/\s+/g, " "))}>Apply narrator</button>
              </label>
              <label>
                <span>Manual year</span>
                <input maxLength={4} value={repairYear} onChange={(event) => setRepairYear(event.target.value)} />
                <button type="button" className="btn-sm" disabled={!/^(19|20)\d{2}$/.test(repairYear.trim())} onClick={() => setYear(repairYear.trim())}>Apply year</button>
              </label>
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

          {valid && (
            <section className="final-review-panel">
              <strong>
                {warnings.length > 0
                  ? "Ready for approval with warnings"
                  : "Ready for approval"}
              </strong>
              <span>Title: {title || "Unknown Title"}</span>
              <span>
                Author: {author || "Unknown Author"}
                {acceptedUnknownAuthor ? " · accepted" : ""}
              </span>
              <span>
                Year: {year || "Unknown Year"}
                {acceptedUnknownYear ? " · accepted" : ""}
              </span>
              <span>
                Narrator: {narrator || "Unknown Narrator"}
                {acceptedUnknownNarrator ? " · accepted" : ""}
              </span>
              <span>Artwork: {batch.artwork_count} matched</span>
              <span>Generic tags hidden: {batch.generic_audio_tag_count ?? 0}</span>
              <span>Discs: {batch.detected_disc_count ?? 0} · Files: {batch.audiobook_file_count ?? 0}</span>
              {containedBooks.length > 0 && (
                <span>
                  Detected contained books: {containedBooks.length} · Files remain one audiobook batch
                </span>
              )}
            </section>
          )}

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
                  <thead><tr><th>Disc</th><th>Track</th><th>File name</th><th>Candidate title</th><th>Status</th></tr></thead>
                  <tbody>
                    {visibleChapterRows.map((candidate, index) => (
                      <tr key={`${candidate.source_file}:${candidate.suggested_title}`}>
                        <td>{candidate.disc_number ?? "—"}</td>
                        <td>{candidate.track_number ?? index + 1}</td>
                        <td><code>{candidate.source_file}</code></td>
                        <td>{candidate.suggested_title || "No embedded chapter title"}</td>
                        <td>
                          <small>
                            {candidate.ignored || candidate.generic || !candidate.suggested_title
                              ? "Ignored / generic"
                              : candidate.confidence_label}
                          </small>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </section>
          )}

          {valid
            && !batch.review_confirmed
            && (batch.blocking_review_items ?? []).length === 0
            && (
            <button type="button" className="btn btn--compact" disabled={saving} onClick={() => void onConfirm()}>
              Confirm audiobook metadata
            </button>
            )}
        </div>

        <div className="editor-shell__footer">
          <button type="button" className="btn" disabled={saving} onClick={onClose}>Cancel</button>
          <button type="submit" className="btn btn--green" disabled={saving || !valid}>
            Save review
          </button>
        </div>
      </form>
    </div>
  );
}
