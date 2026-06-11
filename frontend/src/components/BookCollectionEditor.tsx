import { useState } from "react";
import type {
  BatchSummary,
  BookCollectionItemUpdate,
  BookCollectionReviewUpdate,
} from "../types/archive";
import ReviewIssuesPanel from "./ReviewIssuesPanel";

type Props = {
  batch: BatchSummary;
  saving: boolean;
  onSave: (update: BookCollectionReviewUpdate) => Promise<void>;
  onConfirm: () => Promise<void>;
  onClose: () => void;
};

function initialItems(batch: BatchSummary): BookCollectionItemUpdate[] {
  return (batch.book_items ?? []).map((item) => ({
    source_file: item.source_file,
    include: item.include ?? true,
    title: item.title ?? "",
    author: item.author ?? "",
    year: item.year ?? null,
    format: item.format ?? null,
  }));
}

export default function BookCollectionEditor({
  batch,
  saving,
  onSave,
  onConfirm,
  onClose,
}: Props) {
  const [collectionTitle, setCollectionTitle] = useState(batch.collection_title ?? "");
  const [items, setItems] = useState(() => initialItems(batch));
  const valid = items.some((item) => item.include) && items.every((item) => (
    !item.include ||
    (
      item.title.trim() !== "" &&
      item.author.trim() !== "" &&
      (!item.year || /^(19|20)\d{2}$/.test(item.year))
    )
  ));

  const updateItem = (index: number, patch: Partial<BookCollectionItemUpdate>) => {
    setItems((current) => current.map((item, itemIndex) => (
      itemIndex === index ? { ...item, ...patch } : item
    )));
  };

  return (
    <div className="modal-backdrop" role="presentation" onMouseDown={onClose}>
      <form
        className="metadata-editor metadata-editor--wide"
        onMouseDown={(event) => event.stopPropagation()}
        onSubmit={(event) => {
          event.preventDefault();
          if (!valid) return;
          void onSave({
            collection_title: collectionTitle.trim() || null,
            books: items,
          });
        }}
      >
        <div className="editor-shell__header">
          <div>
            <h2>Review book collection</h2>
            <p>Batch {batch.id}. Each included book moves to its own author and title folder.</p>
          </div>
          <button type="button" className="btn-sm" title="Close" onClick={onClose}>
            <i className="ti ti-x" />
          </button>
        </div>
        <div className="editor-shell__body">
          <ReviewIssuesPanel
            batch={batch}
            saving={saving}
            confirmLabel="Confirm book collection"
            onConfirm={onConfirm}
          />
          <label className="editor-grid editor-grid--full">
            <span>Collection label optional</span>
            <input value={collectionTitle} onChange={(event) => setCollectionTitle(event.target.value)} />
          </label>
          <div className="collection-items-list">
            {items.map((item, index) => {
              const destination = `Books/${(item.format || "EPUB").toUpperCase()}/${item.author || "Unknown Author"}/${item.year || "Unknown Year"} - ${item.title || "Unknown Title"}`;
              return (
                <div className={`collection-item-card${item.include ? "" : " collection-item-card--excluded"}`} key={item.source_file}>
                  <div className="collection-item-card__header">
                    <code>{item.source_file}</code>
                    <label className="collection-item-card__include">
                      <input type="checkbox" checked={item.include} onChange={(event) => updateItem(index, { include: event.target.checked })} />
                      Include
                    </label>
                  </div>
                  <div className="collection-item-card__fields">
                    <label>Title<input disabled={!item.include} value={item.title} onChange={(event) => updateItem(index, { title: event.target.value })} /></label>
                    <label>Author<input disabled={!item.include} value={item.author} onChange={(event) => updateItem(index, { author: event.target.value })} /></label>
                    <label>Year optional<input disabled={!item.include} maxLength={4} value={item.year ?? ""} onChange={(event) => updateItem(index, { year: event.target.value || null })} /></label>
                    <label>Format<select disabled={!item.include} value={item.format ?? "EPUB"} onChange={(event) => updateItem(index, { format: event.target.value })}><option>EPUB</option><option>PDF</option></select></label>
                  </div>
                  {item.include && <div className="collection-item-card__dest"><span>Destination</span><code>{destination}</code></div>}
                </div>
              );
            })}
          </div>
        </div>
        <div className="editor-shell__footer">
          <button type="button" className="btn" disabled={saving} onClick={onClose}>Cancel</button>
          <button type="submit" className="btn btn--green" disabled={saving || !valid}>
            Save book collection
          </button>
        </div>
      </form>
    </div>
  );
}
