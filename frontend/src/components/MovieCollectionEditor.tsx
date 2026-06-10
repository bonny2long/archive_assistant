import { useState, useMemo } from "react";
import type {
  BatchSummary,
  MovieCollectionItem,
  MovieCollectionItemUpdate,
  MovieCollectionReviewUpdate,
} from "../types/archive";
import ReviewIssuesPanel from "./ReviewIssuesPanel";

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

// ── Single item card ─────────────────────────────────────────────────────────

type ItemCardProps = {
  sourceFile: string;
  item: MovieCollectionItemUpdate;
  onChange: (next: MovieCollectionItemUpdate) => void;
};

function CollectionItemCard({ sourceFile, item, onChange }: ItemCardProps) {
  const yearValid =
    item.year.trim() === "" || /^(19|20)\d{2}$/.test(item.year.trim());
  const titleValid = item.title.trim() !== "";

  const destPreview = useMemo(() => {
    if (!item.include) return null;
    return buildDestPreview(item.title, item.year, item.edition ?? "");
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
            onChange={(e) => onChange({ ...item, title: e.target.value })}
          />
          {item.include && !titleValid && (
            <p className="field-error">Title is required</p>
          )}
        </label>
        <label>
          Year
          <input
            value={item.year}
            disabled={!item.include}
            maxLength={4}
            onChange={(e) => onChange({ ...item, year: e.target.value })}
          />
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
    if (existing) {
      return {
        source_file: sourceFile,
        include: existing.include ?? true,
        title: existing.title ?? "",
        year: existing.year ?? "",
        edition: existing.edition ?? null,
        format: existing.format ?? null,
      };
    }
    // No prior data — start with empty fields so the user fills them in
    return {
      source_file: sourceFile,
      include: true,
      title: "",
      year: "",
      edition: null,
      format: null,
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
    () =>
      (batch.movie_items?.[0] as MovieCollectionItem | undefined)
        ?.title ?? "",
  );
  const [items, setItems] = useState<MovieCollectionItemUpdate[]>(
    () => buildInitialItems(batch),
  );

  const includedCount = items.filter((i) => i.include).length;
  const allValid = items.every(
    (item) =>
      !item.include ||
      (item.title.trim() !== "" &&
        /^(19|20)\d{2}$/.test(item.year.trim())),
  );

  const hasBlockers = (batch.blocking_review_items ?? []).length > 0;

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
        className="metadata-editor metadata-editor--wide"
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

          {/* Per-movie item cards */}
          <div className="collection-item-list">
            {items.map((item) => (
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
              All included movies need a title and a valid four-digit year.
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
