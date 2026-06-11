import { useState } from "react";
import type {
  BatchSummary,
  BookCollectionItemUpdate,
  BookCollectionReviewUpdate,
} from "../types/archive";

type Props = {
  batch: BatchSummary;
  saving: boolean;
  onSave: (update: BookCollectionReviewUpdate) => Promise<void>;
  onConfirm: () => Promise<void>;
  onClose: () => void;
};

function normalized(value: string | null | undefined): string {
  return String(value ?? "").trim();
}

function isUnknownAuthor(value: string | null | undefined): boolean {
  const text = normalized(value).toLowerCase();
  return text === "" || text === "unknown" || text === "unknown author" || text === "unkn";
}

function isMissingTitle(value: string | null | undefined): boolean {
  const text = normalized(value).toLowerCase();
  return text === "" || text === "unknown" || text === "unknown title" || text === "unkn";
}

function isInvalidYear(value: string | null | undefined): boolean {
  const text = normalized(value);
  return text !== "" && !/^(19|20)\d{2}$/.test(text);
}

function itemRepairReasons(item: BookCollectionItemUpdate): string[] {
  if (!item.include) return [];
  const reasons: string[] = [];
  if (isMissingTitle(item.title)) reasons.push("missing_title");
  if (isUnknownAuthor(item.author)) reasons.push("missing_author");
  if (isInvalidYear(item.year)) reasons.push("invalid_year");
  return reasons;
}

function itemNeedsRepair(item: BookCollectionItemUpdate): boolean {
  return itemRepairReasons(item).length > 0;
}

function destinationForBookItem(item: BookCollectionItemUpdate): string {
  if (!item.include) return "Excluded - will not be moved";
  const format = normalized(item.format || "EPUB").toUpperCase() || "EPUB";
  const author = normalized(item.author) || "Unknown Author";
  const title = normalized(item.title) || "Unknown Title";
  const year = normalized(item.year) || "Unknown Year";
  return `Books/${format}/${author}/${year} - ${title}`;
}

function reasonLabel(reason: string): string {
  switch (reason) {
    case "missing_title":
      return "Title missing";
    case "missing_author":
      return "Author missing";
    case "invalid_year":
      return "Year must be four digits";
    default:
      return reason;
  }
}

function initialItems(batch: BatchSummary): BookCollectionItemUpdate[] {
  return (batch.book_items ?? []).map((item) => ({
    source_file: item.source_file,
    include: item.include ?? true,
    title: item.title ?? "",
    author: item.author ?? "",
    year: item.year ?? null,
    format: item.format ?? null,
    series: item.series ?? null,
    series_index: item.series_index ?? null,
  }));
}

function BookCollectionIssueSummary({
  repairCount,
  warnings,
}: {
  repairCount: number;
  warnings: string[];
}) {
  return (
    <div className={`review-summary ${repairCount > 0 ? "review-summary--warning" : "review-summary--clean"}`}>
      <div>
        <strong>{repairCount > 0 ? "Repair required" : "Review available"}</strong>
        <p>
          {repairCount > 0
            ? `${repairCount} included book${repairCount === 1 ? "" : "s"} need metadata fixes before approval.`
            : "No blocking book metadata problems."}
        </p>
      </div>
      <span>{repairCount} blocking item(s) · {warnings.length} warning(s)</span>
    </div>
  );
}

type BookRepairCardProps = {
  item: BookCollectionItemUpdate;
  index: number;
  reasons: string[];
  onChange: (index: number, patch: Partial<BookCollectionItemUpdate>) => void;
};

function BookRepairCard({
  item,
  index,
  reasons,
  onChange,
}: BookRepairCardProps) {
  return (
    <div className="book-repair-card">
      <div className="book-repair-card__header">
        <div>
          <strong>{reasons.length ? reasons.map(reasonLabel).join(" · ") : "Ready"}</strong>
          <code>{item.source_file}</code>
        </div>
        <label className="collection-item-card__include">
          <input
            type="checkbox"
            checked={item.include}
            onChange={(event) => onChange(index, { include: event.target.checked })}
          />
          Include
        </label>
      </div>
      <div className="book-repair-card__fields">
        <label>
          Title
          <input
            disabled={!item.include}
            value={item.title}
            onChange={(event) => onChange(index, { title: event.target.value })}
          />
        </label>
        <label>
          Author
          <input
            disabled={!item.include}
            value={item.author}
            onChange={(event) => onChange(index, { author: event.target.value })}
          />
        </label>
        <label>
          Year optional
          <input
            disabled={!item.include}
            maxLength={4}
            value={item.year ?? ""}
            onChange={(event) => onChange(index, { year: event.target.value || null })}
          />
        </label>
        <label>
          Format
          <select
            disabled={!item.include}
            value={item.format ?? "EPUB"}
            onChange={(event) => onChange(index, { format: event.target.value })}
          >
            <option>EPUB</option>
            <option>PDF</option>
          </select>
        </label>
      </div>
      <details className="optional-metadata-fields">
        <summary>Series info optional</summary>
        <div className="book-repair-card__fields">
          <label>
            Series
            <input
              disabled={!item.include}
              value={item.series ?? ""}
              onChange={(event) => onChange(index, { series: event.target.value || null })}
            />
          </label>
          <label>
            Series index
            <input
              disabled={!item.include}
              value={item.series_index ?? ""}
              onChange={(event) => onChange(index, { series_index: event.target.value || null })}
            />
          </label>
        </div>
      </details>
      <div className="book-repair-card__dest">
        <span>Destination</span>
        <code>{destinationForBookItem(item)}</code>
      </div>
    </div>
  );
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
  const [showAllBooks, setShowAllBooks] = useState(false);
  const [showCleanPreview, setShowCleanPreview] = useState(false);
  const [bulkAuthor, setBulkAuthor] = useState("");

  const indexedItems = items.map((item, index) => ({ item, index }));
  const repairItems = indexedItems.filter(({ item }) => itemNeedsRepair(item));
  const cleanItems = indexedItems.filter(({ item }) => item.include && !itemNeedsRepair(item));
  const excludedItems = indexedItems.filter(({ item }) => !item.include);
  const includedCount = items.filter((item) => item.include).length;
  const repairCount = repairItems.length;
  const cleanCount = cleanItems.length;
  const excludedCount = excludedItems.length;
  const valid = includedCount > 0 && repairCount === 0;
  const warningMessages = (batch.non_blocking_review_items ?? []).map((item) => item.message);

  const updateItem = (index: number, patch: Partial<BookCollectionItemUpdate>) => {
    setItems((current) => current.map((item, itemIndex) => (
      itemIndex === index ? { ...item, ...patch } : item
    )));
  };

  const applyAuthorToRepairItems = () => {
    const author = bulkAuthor.trim();
    if (!author) return;
    setItems((current) => current.map((item) => {
      if (!item.include || !itemNeedsRepair(item) || !isUnknownAuthor(item.author)) {
        return item;
      }
      return { ...item, author };
    }));
  };

  const excludeRepairItems = () => {
    setItems((current) => current.map((item) => (
      itemNeedsRepair(item) ? { ...item, include: false } : item
    )));
  };

  const includeAllItems = () => {
    setItems((current) => current.map((item) => ({ ...item, include: true })));
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
            <p>
              Batch {batch.id} · {items.length} books · {repairCount} need repair · {includedCount} included
              {excludedCount > 0 ? ` · ${excludedCount} excluded` : ""}
            </p>
          </div>
          <button type="button" className="btn-sm" title="Close" onClick={onClose}>
            <i className="ti ti-x" />
          </button>
        </div>

        <div className="editor-shell__body">
          <BookCollectionIssueSummary repairCount={repairCount} warnings={warningMessages} />

          <label className="editor-grid editor-grid--full">
            <span>Collection label optional</span>
            <input value={collectionTitle} onChange={(event) => setCollectionTitle(event.target.value)} />
          </label>

          <section className="book-review-panel">
            <div className="book-review-panel__header">
              <div>
                <strong>Repair queue</strong>
                <p>{repairCount} book{repairCount === 1 ? "" : "s"} need repair. Clean books are hidden by default.</p>
              </div>
              <div className="book-review-panel__actions">
                <button type="button" className="btn-sm" onClick={() => setShowAllBooks((value) => !value)}>
                  {showAllBooks ? "Hide all books" : "Show all books"}
                </button>
                <button type="button" className="btn-sm" onClick={() => setShowCleanPreview((value) => !value)}>
                  {showCleanPreview ? "Hide clean preview" : "Show clean preview"}
                </button>
                {excludedCount > 0 && (
                  <button type="button" className="btn-sm" onClick={includeAllItems}>
                    Include all
                  </button>
                )}
              </div>
            </div>

            {repairCount > 0 && (
              <div className="book-bulk-tools">
                <label>
                  Apply author to repair items with unknown author
                  <input
                    placeholder="e.g. Frank Herbert"
                    value={bulkAuthor}
                    onChange={(event) => setBulkAuthor(event.target.value)}
                  />
                </label>
                <button type="button" className="btn-sm" onClick={applyAuthorToRepairItems} disabled={!bulkAuthor.trim()}>
                  Apply author
                </button>
                <button type="button" className="btn-sm" onClick={excludeRepairItems}>
                  Exclude repair items
                </button>
              </div>
            )}

            {repairCount === 0 ? (
              <div className="book-clean-state">
                <strong>No blocking book metadata problems.</strong>
                <span>{cleanCount} included book{cleanCount === 1 ? "" : "s"} ready for approval.</span>
                {!batch.review_confirmed && (batch.blocking_review_items ?? []).length === 0 && (
                  <button type="button" className="btn-sm" disabled={saving} onClick={() => void onConfirm()}>
                    Confirm book collection
                  </button>
                )}
              </div>
            ) : (
              <div className="book-repair-list">
                {repairItems.map(({ item, index }) => (
                  <BookRepairCard
                    key={item.source_file}
                    item={item}
                    index={index}
                    reasons={itemRepairReasons(item)}
                    onChange={updateItem}
                  />
                ))}
              </div>
            )}
          </section>

          {showCleanPreview && (
            <section className="book-clean-preview">
              <div className="book-clean-preview__header">
                <strong>Clean books preview</strong>
                <span>{cleanCount} clean · {excludedCount} excluded</span>
              </div>
              <div className="book-clean-preview__table">
                <table>
                  <thead>
                    <tr><th>Format</th><th>Author</th><th>Title</th><th>Year</th><th>Destination</th></tr>
                  </thead>
                  <tbody>
                    {cleanItems.slice(0, 12).map(({ item }) => (
                      <tr key={`clean-${item.source_file}`}>
                        <td>{item.format ?? "EPUB"}</td>
                        <td>{item.author}</td>
                        <td>{item.title}</td>
                        <td>{item.year || "Unknown Year"}</td>
                        <td><code>{destinationForBookItem(item)}</code></td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              {cleanCount > 12 && (
                <p className="muted">Showing first 12 clean books. Use Show all books to edit everything.</p>
              )}
            </section>
          )}

          {showAllBooks && (
            <section className="book-all-editor">
              <div className="book-clean-preview__header">
                <strong>All books</strong>
                <span>{items.length} total</span>
              </div>
              <div className="book-repair-list">
                {indexedItems.map(({ item, index }) => (
                  <BookRepairCard
                    key={`all-${item.source_file}`}
                    item={item}
                    index={index}
                    reasons={itemRepairReasons(item)}
                    onChange={updateItem}
                  />
                ))}
              </div>
            </section>
          )}
        </div>

        <div className="editor-shell__footer">
          <button type="button" className="btn" disabled={saving} onClick={onClose}>Cancel</button>
          <button type="submit" className="btn btn--green" disabled={saving || !valid}>
            {repairCount > 0
              ? `Fix ${repairCount} book${repairCount === 1 ? "" : "s"} first`
              : "Save book collection"}
          </button>
        </div>
      </form>
    </div>
  );
}
