import { useState, useMemo } from "react";
import type {
  BatchSummary,
  MovieCollectionItemUpdate,
  MovieCollectionReviewUpdate,
} from "../types/archive";
import ReviewIssuesPanel from "./ReviewIssuesPanel";
import MetadataAssistStaleWarning from "./MetadataAssistStaleWarning";
import MetadataSuggestionChips from "./MetadataSuggestionChips";

type Props = {
  batch: BatchSummary;
  saving: boolean;
  onSave: (update: MovieCollectionReviewUpdate) => Promise<void>;
  onConfirm: () => Promise<void>;
  onClose: () => void;
};

function sanitizePath(value: string): string {
  return value.replace(/[<>:"/\\|?*]/g, "_").trim();
}

function buildDestPreview(
  title: string,
  year: string,
  edition: string,
): string {
  const t = title.trim() || "Unknown Title";
  const y = year.trim() || "Unknown Year";
  const base = `${y} - ${t}`;
  const folder = edition.trim() ? `${base} [${edition.trim()}]` : base;
  return `Movies/Library/${sanitizePath(folder)}`;
}

export function parseMovieFilename(sourceFile: string): {
  title: string;
  year: string | null;
  edition: string | null;
  format: string | null;
} {
  const fileName = sourceFile.split(/[\\/]/).pop() ?? sourceFile;
  const extensionMatch = fileName.match(/\.([a-z0-9]{2,5})$/i);
  const format = extensionMatch?.[1]?.toUpperCase() ?? null;
  const stem = extensionMatch
    ? fileName.slice(0, -extensionMatch[0].length)
    : fileName;
  const yearMatches = Array.from(
    stem.matchAll(/(?:^|\D)((?:19|20)\d{2})(?!\d)/g),
  );
  const yearMatch = yearMatches.length > 0
    ? yearMatches[yearMatches.length - 1]
    : undefined;
  const year = yearMatch?.[1] ?? null;
  const yearIndex = yearMatch?.index ?? -1;
  const titleSource = yearIndex >= 0 ? stem.slice(0, yearIndex) : stem;
  const title = titleSource
    .replace(/[._]+/g, " ")
    .replace(/\s*-\s*/g, " ")
    .replace(/\s+/g, " ")
    .trim();

  let edition: string | null = null;
  if (yearMatch) {
    edition = stem
      .slice(yearIndex + yearMatch[0].length)
      .replace(
        /\b(?:2160p|1080p|720p|480p|4k|uhd|hdr10?|dv|bluray|brrip|bdrip|web[ ._-]?dl|web|webrip|hdrip|dvdrip|x264|x265|h264|h265|hevc|aac|dts|truehd|atmos)\b/gi,
        " ",
      )
      .replace(/\b\d\.\d\b/g, " ")
      .replace(/\b(?:BONE|YIFY|YTS|RARBG)\b/gi, " ")
      .replace(/[._]+/g, " ")
      .replace(/\s+/g, " ")
      .trim() || null;
  }

  return { title, year, edition, format };
}

// ── Single item card ─────────────────────────────────────────────────────────

type ItemCardProps = {
  sourceFile: string;
  item: MovieCollectionItemUpdate;
  onChange: (next: MovieCollectionItemUpdate) => void;
};

function CollectionItemCard({ sourceFile, item, onChange }: ItemCardProps) {
  const yearValid =
    !item.year || /^(19|20)\d{2}$/.test(item.year.trim());
  const titleValid = item.title.trim() !== "" || item.accepted_unknown_title;

  const destPreview = useMemo(() => {
    if (!item.include) return null;
    return buildDestPreview(item.title, item.year ?? "", item.edition ?? "");
  }, [item.include, item.title, item.year, item.edition]);

  return (
    <div
      className={`collection-item-card${!item.include ? " collection-item-card--excluded" : ""}`}
    >
      {/* Header: filename + include toggle */}
      <div className="collection-item-card__header">
        <code>{sourceFile}</code>
        <label className="collection-item-card__include">
          <input
            type="checkbox"
            checked={item.include}
            onChange={(e) => onChange({ ...item, include: e.target.checked })}
          />
          Include
        </label>
      </div>

      {/* Fields */}
      <div className="collection-item-card__fields">
        <label className="full">
          Title
          <input
            value={item.title}
            disabled={!item.include}
            autoComplete="off"
            onChange={(e) => onChange({
              ...item,
              title: e.target.value,
              accepted_unknown_title: e.target.value.trim()
                ? false
                : item.accepted_unknown_title,
            })}
          />
          <MetadataSuggestionChips label={`Title for ${sourceFile}`} field="title" candidates={item.metadata_candidates?.title ?? []} currentValue={item.title} onApply={(value) => onChange({ ...item, title: value })} maxVisible={2} />
          {item.include && !titleValid && (
            <p className="field-error">Title is required</p>
          )}
        </label>
        <label>
          Year
          <input
            value={item.year ?? ""}
            disabled={!item.include}
            maxLength={4}
            onChange={(e) => onChange({
              ...item,
              year: e.target.value || null,
              accepted_unknown_year: e.target.value.trim()
                ? false
                : item.accepted_unknown_year,
            })}
          />
          <MetadataSuggestionChips label={`Year for ${sourceFile}`} field="year" candidates={item.metadata_candidates?.year ?? []} currentValue={item.year ?? ""} onApply={(value) => onChange({ ...item, year: value })} maxVisible={2} />
          {item.include && !yearValid && (
            <p className="field-error">Must be four-digit year</p>
          )}
        </label>
        <label>
          Edition / Version
          <input
            value={item.edition ?? ""}
            disabled={!item.include}
            placeholder="optional"
            onChange={(e) =>
              onChange({ ...item, edition: e.target.value || null })
            }
          />
        </label>
        <label>
          Format
          <input
            value={item.format ?? ""}
            disabled={!item.include}
            placeholder="optional"
            onChange={(e) =>
              onChange({ ...item, format: e.target.value || null })
            }
          />
        </label>
      </div>

      <div className="collection-item-card__actions acceptance-controls__buttons">
        <button type="button" className={`btn-sm${item.accepted_unknown_title ? " btn-sm--active" : ""}`} onClick={() => onChange({ ...item, accepted_unknown_title: !item.accepted_unknown_title })}>
          {item.accepted_unknown_title ? "Unknown Title Accepted" : "Accept Unknown Title"}
        </button>
        <button type="button" className={`btn-sm${item.accepted_unknown_year ? " btn-sm--active" : ""}`} onClick={() => onChange({ ...item, accepted_unknown_year: !item.accepted_unknown_year })}>
          {item.accepted_unknown_year ? "Unknown Year Accepted" : "Accept Unknown Year"}
        </button>
        <button type="button" className={`btn-sm${item.lookup_later ? " btn-sm--active" : ""}`} onClick={() => onChange({ ...item, lookup_later: !item.lookup_later })}>
          {item.lookup_later ? "Lookup Later Marked" : "Lookup Later"}
        </button>
      </div>

      {/* Destination preview */}
      {item.include && (
        <div className="collection-item-card__dest">
          <span>Destination</span>
          <code
            className={
              !titleValid || !yearValid ? "dest--incomplete" : undefined
            }
          >
            {destPreview ?? "Fill in title and year above"}
          </code>
        </div>
      )}
      {!item.include && (
        <div className="collection-item-card__dest">
          <code className="dest--incomplete">Excluded — will not be moved</code>
        </div>
      )}
    </div>
  );
}

// ── Main component ───────────────────────────────────────────────────────────

function buildInitialItems(batch: BatchSummary): MovieCollectionItemUpdate[] {
  // If the batch already has movie_items from a prior review save, use those
  const existingItems = batch.movie_items ?? [];
  const existingByFile = new Map(
    existingItems.map((item) => [
      (item.source_file ?? "").toLowerCase(),
      item,
    ]),
  );

  const videoFiles = batch.video_files ?? [];
  return videoFiles.map((sourceFile) => {
    const key = sourceFile.toLowerCase();
    const existing = existingByFile.get(key);
    const parsed = parseMovieFilename(sourceFile);
    if (existing) {
      return {
        source_file: sourceFile,
        include: existing.include ?? true,
        title: existing.title
          || (existing.accepted_unknown_title ? "" : parsed.title),
        year: existing.year
          || (existing.accepted_unknown_year ? null : parsed.year),
        edition: existing.edition ?? parsed.edition,
        format: existing.format ?? parsed.format,
        metadata_candidates: existing.metadata_candidates ?? {},
        accepted_unknown_title: existing.accepted_unknown_title ?? false,
        accepted_unknown_year: existing.accepted_unknown_year ?? false,
        lookup_later: existing.lookup_later ?? false,
      };
    }
    // No prior data — start with empty fields so the user fills them in
    return {
      source_file: sourceFile,
      include: true,
      title: parsed.title,
      year: parsed.year,
      edition: parsed.edition,
      format: parsed.format,
      metadata_candidates: {},
      accepted_unknown_title: false,
      accepted_unknown_year: false,
      lookup_later: false,
    };
  });
}

export default function MovieCollectionEditor({
  batch,
  saving,
  onSave,
  onConfirm,
  onClose,
}: Props) {
  const [collectionTitle, setCollectionTitle] = useState(
    () => batch.collection_title ?? "",
  );
  const [items, setItems] = useState<MovieCollectionItemUpdate[]>(
    () => buildInitialItems(batch),
  );
  const [filter, setFilter] = useState<"repair" | "included" | "excluded" | "all">("repair");

  const includedCount = items.filter((i) => i.include).length;
  const allValid = includedCount > 0 && items.every(
    (item) =>
      !item.include ||
      ((item.title.trim() !== "" || item.accepted_unknown_title) &&
        (
          (Boolean(item.year) && /^(19|20)\d{2}$/.test(item.year!.trim()))
          || (!item.year && item.accepted_unknown_year)
        )),
  );
  const visibleItems = items.filter((item) => {
    if (filter === "included") return item.include;
    if (filter === "excluded") return !item.include;
    if (filter === "repair") {
      return item.include && (
        (!item.title.trim() && !item.accepted_unknown_title)
        || (!item.year && !item.accepted_unknown_year)
        || item.lookup_later
      );
    }
    return true;
  });

  const handleItemChange = (
    sourceFile: string,
    next: MovieCollectionItemUpdate,
  ) => {
    setItems((prev) =>
      prev.map((item) =>
        item.source_file === sourceFile ? next : item,
      ),
    );
  };

  const handleSave = () => {
    if (!allValid) return;
    void onSave({
      collection_title: collectionTitle.trim() || null,
      movies: items,
      confirm_non_blocking_warnings: false,
    });
  };

  return (
    <div className="modal-backdrop" role="presentation" onMouseDown={onClose}>
      <div
        className="metadata-editor metadata-editor--collection"
        onMouseDown={(e) => e.stopPropagation()}
      >
        {/* ── Header ── */}
        <div className="editor-shell__header">
          <div>
            <h2>Review movie collection</h2>
            <p>
              Batch {batch.id} · {batch.video_file_count} video file
              {batch.video_file_count !== 1 ? "s" : ""} · each movie moves to
              its own folder
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

        {/* ── Body ── */}
        <div className="editor-shell__body">
          {/* Source context */}
          <div className="movie-editor__context">
            <div>
              <span>Source folder</span>
              <strong>{batch.original_release_name ?? "Unknown folder"}</strong>
            </div>
            <div className="movie-editor__counts">
              <span>Video files: {batch.video_file_count}</span>
              <span>Included: {includedCount}</span>
              <span>Artwork: {batch.artwork_count}</span>
              <span>Subtitles: {batch.subtitle_count}</span>
              <span>Ignored sidecars: {batch.ignored_sidecar_count}</span>
            </div>
            {batch.artwork_count > 0 || batch.subtitle_count > 0 ? (
              <p style={{ fontSize: "11px", color: "var(--text-muted)", marginTop: "4px" }}>
                Artwork and subtitles will be placed in a shared{" "}
                <code>_collection_sidecars/</code> folder. They can be
                manually sorted per-movie after the move.
              </p>
            ) : null}
          </div>

          {/* Blockers / warnings */}
          <ReviewIssuesPanel
            batch={batch}
            saving={saving}
            confirmLabel="Confirm collection review"
            onConfirm={onConfirm}
          />
          <MetadataAssistStaleWarning batch={batch} />

          {/* Optional collection label */}
          <div className="editor-grid editor-grid--full">
            <label>
              <span>Collection label (optional)</span>
              <input
                value={collectionTitle}
                placeholder="e.g. Harold and Kumar Trilogy"
                onChange={(e) => setCollectionTitle(e.target.value)}
              />
            </label>
          </div>

          <div className="collection-editor__bulk-actions">
            {(["repair", "included", "excluded", "all"] as const).map((value) => (
              <button type="button" className={`btn-sm${filter === value ? " btn-sm--active" : ""}`} key={value} onClick={() => setFilter(value)}>
                {value === "repair" ? "Needs repair" : value[0].toUpperCase() + value.slice(1)}
              </button>
            ))}
            <button type="button" className="btn-sm" onClick={() => {
              const visible = new Set(visibleItems.map((item) => item.source_file));
              setItems((current) => current.map((item) => visible.has(item.source_file)
                ? { ...item, accepted_unknown_year: true }
                : item));
            }}>Accept unknown years for visible</button>
            <button type="button" className="btn-sm" onClick={() => {
              const visible = new Set(visibleItems.map((item) => item.source_file));
              setItems((current) => current.map((item) => visible.has(item.source_file)
                ? { ...item, lookup_later: true }
                : item));
            }}>Mark visible lookup later</button>
            <button type="button" className="btn-sm" onClick={() => {
              const visible = new Set(visibleItems.map((item) => item.source_file));
              setItems((current) => current.map((item) => visible.has(item.source_file)
                ? { ...item, include: false }
                : item));
            }}>Exclude visible</button>
          </div>

          {/* Per-movie item cards */}
          <div className="collection-item-list">
            {visibleItems.map((item) => (
              <CollectionItemCard
                key={item.source_file}
                sourceFile={item.source_file}
                item={item}
                onChange={(next) =>
                  handleItemChange(item.source_file, next)
                }
              />
            ))}
          </div>

          {!allValid && (
            <p className="metadata-editor__error">
              Include at least one movie. Each included movie needs a title and year, or an explicit accepted-unknown decision.
            </p>
          )}
        </div>

        {/* ── Footer ── */}
        <div className="editor-shell__footer">
          <button
            type="button"
            className="btn"
            disabled={saving}
            onClick={onClose}
          >
            Cancel
          </button>
          <button
            type="button"
            className="btn btn--green"
            disabled={saving || !allValid || items.length === 0}
            onClick={handleSave}
          >
            <i
              className={`ti ti-${saving ? "loader-2 spinner" : "device-floppy"}`}
            />
            Save collection review
          </button>
        </div>
      </div>
    </div>
  );
}
