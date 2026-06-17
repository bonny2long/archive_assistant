import { useMemo, useState } from "react";
import type { BatchSummary, MovieMetadataUpdate } from "../types/archive";
import ReviewIssuesPanel from "./ReviewIssuesPanel";
import MetadataAssistStaleWarning from "./MetadataAssistStaleWarning";
import MetadataSuggestionChips from "./MetadataSuggestionChips";

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
  const [showAllVideos, setShowAllVideos] = useState(false);
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
  const [acceptedUnknownTitle, setAcceptedUnknownTitle] = useState(
    Boolean(batch.accepted_unknown_title),
  );
  const [acceptedUnknownYear, setAcceptedUnknownYear] = useState(
    Boolean(batch.accepted_unknown_year),
  );
  const [lookupLater, setLookupLater] = useState(Boolean(batch.lookup_later));
  const candidates = batch.metadata_candidates ?? {};

  const yearValid = year.trim() === "" || /^(19|20)\d{2}$/.test(year.trim());
  const titleValid = title.trim() !== "" || acceptedUnknownTitle;
  const valid = titleValid && yearValid;
  const preview = useMemo(() => {
    const base = `${year.trim() || "Unknown Year"} - ${title.trim() || "Unknown Title"}`;
    const folder = edition.trim() ? `${base} [${edition.trim()}]` : base;
    return `Movies/Library/${sanitizePathPart(folder)}`;
  }, [title, year, edition]);

  return (
    <div className="modal-backdrop" role="presentation" onMouseDown={onClose}>
      <form
        className="metadata-editor metadata-editor--wide"
        onMouseDown={(event) => event.stopPropagation()}
        onSubmit={(event) => {
          event.preventDefault();
          if (!valid) return;
          void onSave({
            title: title.trim() || "Unknown Movie",
            year: year.trim() || null,
            edition: edition.trim() || null,
            format: format.trim() || null,
            accepted_unknown_title: acceptedUnknownTitle,
            accepted_unknown_year: acceptedUnknownYear,
            lookup_later: lookupLater,
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
            {batch.video_files && batch.video_files.length > 1 && (
              <div>
                <button
                  type="button"
                  className="btn-sm"
                  onClick={() => setShowAllVideos((value) => !value)}
                >
                  {showAllVideos ? "Hide video files" : `Show all ${batch.video_files.length} video files`}
                </button>
                {showAllVideos && (
                  <ul style={{ margin: "0.25rem 0", paddingLeft: "1.25rem" }}>
                    {batch.video_files.map((vf) => (
                      <li key={vf}><code>{vf}</code></li>
                    ))}
                  </ul>
                )}
              </div>
            )}
            <div className="movie-editor__counts">
              <span>Video files: {batch.video_file_count}</span>
              <span>Resolution: {batch.resolution ?? "Unknown"}</span>
              <span>Source: {batch.source ?? "Unknown"}</span>
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
          <MetadataAssistStaleWarning batch={batch} />

          <section className="acceptance-controls">
            <div>
              <strong>Accepted unknown metadata</strong>
              <p>These decisions remain visible in the movie move manifest.</p>
            </div>
            <div className="acceptance-controls__buttons">
              <button type="button" className={`btn-sm${acceptedUnknownTitle ? " btn-sm--active" : ""}`} onClick={() => setAcceptedUnknownTitle((value) => !value)}>
                {acceptedUnknownTitle ? "Unknown Title Accepted" : "Accept Unknown Title"}
              </button>
              <button type="button" className={`btn-sm${acceptedUnknownYear ? " btn-sm--active" : ""}`} onClick={() => setAcceptedUnknownYear((value) => !value)}>
                {acceptedUnknownYear ? "Unknown Year Accepted" : "Accept Unknown Year"}
              </button>
              <button type="button" className={`btn-sm${lookupLater ? " btn-sm--active" : ""}`} onClick={() => setLookupLater((value) => !value)}>
                {lookupLater ? "Lookup Later Marked" : "Lookup Later"}
              </button>
            </div>
          </section>

          <div className="editor-grid editor-grid--full">
            <label>
              <span>Title</span>
              <input value={title} onChange={(event) => setTitle(event.target.value)} autoFocus />
              <MetadataSuggestionChips label="Movie title" field="title" candidates={candidates.title ?? []} currentValue={title} onApply={setTitle} />
            </label>
          </div>
          <div className="editor-grid">
            <label>
              <span>Year</span>
              <input value={year} maxLength={4} onChange={(event) => setYear(event.target.value)} />
              <MetadataSuggestionChips label="Movie year" field="year" candidates={candidates.year ?? []} currentValue={year} onApply={setYear} />
            </label>
            <label>
              <span>Edition / Version optional</span>
              <input value={edition} onChange={(event) => setEdition(event.target.value)} />
              <MetadataSuggestionChips label="Edition" field="edition" candidates={candidates.edition ?? []} currentValue={edition} onApply={setEdition} />
            </label>
          </div>
          <div className="editor-grid editor-grid--full">
            <label>
              <span>Format</span>
              <input value={format} onChange={(event) => setFormat(event.target.value)} />
              <MetadataSuggestionChips label="Format" field="format" candidates={candidates.format ?? []} currentValue={format} onApply={setFormat} />
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
