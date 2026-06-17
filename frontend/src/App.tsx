import { useCallback, useEffect, useState } from "react";
import type {
  BatchMetadataUpdate,
  AudiobookMetadataUpdate,
  BatchMoveSummary,
  BatchReview,
  BatchSummary,
  BookCollectionReviewUpdate,
  BookMetadataUpdate,
  DiscographyMetadataUpdate,
  IngestBatch,
  LibrarySummary as LibrarySummaryData,
  MovieCollectionReviewUpdate,
  MovieMetadataUpdate,
  SystemTimeResponse,
  TabKey,
  TvMetadataUpdate,
  TvEpisodeReviewUpdate,
} from "./types/archive";
import { api } from "./api/client";
import ActionBar from "./components/ActionBar";
import BatchTable from "./components/BatchTable";
import StatusTabs from "./components/StatusTabs";
import Toast from "./components/Toast";
import LibrarySummary from "./components/LibrarySummary";
import BulkApproveModal from "./components/BulkApproveModal";
import MediaReviewRouter from "./components/MediaReviewRouter";
import {
  archiveTimezone,
  configureArchiveTimezone,
  formatArchiveTime,
} from "./utils/archiveTime";

type ToastState = { msg: string; type: "info" | "error" };
type ActionKey = "refresh" | "scan" | "move" | "reset";
type QaSummary = {
  title: string;
  text: string;
  warnings?: string;
};

const EMPTY_LIBRARY_SUMMARY: LibrarySummaryData = {
  moved_albums: 0,
  moved_tracks: 0,
  moved_batches: 0,
  moved_files: 0,
  failed_moves: 0,
  approved_waiting: 0,
  needs_metadata: 0,
};

export default function App() {
  const [batches, setBatches] = useState<BatchSummary[]>([]);
  const [details, setDetails] = useState<Record<number, IngestBatch>>({});
  const [moveSummaries, setMoveSummaries] = useState<Record<number, BatchMoveSummary>>({});
  const [reviews, setReviews] = useState<Record<number, BatchReview>>({});
  const [detailLoading, setDetailLoading] = useState<Set<number>>(new Set());
  const [detailErrors, setDetailErrors] = useState<Record<number, string>>({});
  const [loading, setLoading] = useState(false);
  const [bulkLoading, setBulkLoading] = useState(false);
  const [showBulkApprove, setShowBulkApprove] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [tab, setTab] = useState<TabKey>("all");
  const [selected, setSelected] = useState<Set<number>>(new Set());
  const [toast, setToast] = useState<ToastState | null>(null);
  const [loadingAction, setLoadingAction] = useState<ActionKey | null>(null);
  const [editingBatch, setEditingBatch] = useState<BatchSummary | null>(null);
  const [savingMetadata, setSavingMetadata] = useState(false);
  const [devToolsEnabled, setDevToolsEnabled] = useState(false);
  const [librarySummary, setLibrarySummary] = useState<LibrarySummaryData>(EMPTY_LIBRARY_SUMMARY);
  const [qaSummary, setQaSummary] = useState<QaSummary | null>(null);
  const [systemTime, setSystemTime] = useState<SystemTimeResponse | null>(null);
  const [ingestPath, setIngestPath] = useState<string | null>(null);

  const showToast = useCallback((msg: string, type: ToastState["type"] = "info") => {
    setToast({ msg, type });
  }, []);

  const loadLibrarySummary = useCallback(async () => {
    try {
      setLibrarySummary(await api.getLibrarySummary());
    } catch {
      setLibrarySummary(EMPTY_LIBRARY_SUMMARY);
    }
  }, []);

  const loadBatches = useCallback(async (): Promise<BatchSummary[]> => {
    setLoading(true);
    setError(null);
    try {
      const response = await api.listBatches();
      const items = response.items.filter((batch) => batch.status !== "merged");
      setBatches(items);
      setDetails({});
      setMoveSummaries({});
      setReviews({});
      return items;
    } catch (primaryError: unknown) {
      try {
        const fallback = await api.listPending();
        const items = fallback.items.filter((batch) => batch.status !== "merged");
        setBatches(items);
        setDetails({});
        setMoveSummaries({});
        setReviews({});
        return items;
      } catch {
        setError(primaryError instanceof Error ? primaryError.message : "Unable to load batches");
        return [];
      }
    } finally {
      await loadLibrarySummary();
      setLoading(false);
    }
  }, [loadLibrarySummary]);

  useEffect(() => {
    void loadBatches();
    void api.health()
      .then((health) => setDevToolsEnabled(health.dev_tools_enabled))
      .catch(() => setDevToolsEnabled(false));
    void api.systemTime()
      .then((time) => {
        configureArchiveTimezone(time.server_timezone);
        setSystemTime(time);
      })
      .catch(() => configureArchiveTimezone(null));
    void api.systemPaths()
      .then((paths) => setIngestPath(paths.ingest_root))
      .catch(() => setIngestPath(null));
  }, [loadBatches]);

  const filtered = batches.filter((batch) => {
    if (tab === "all") return true;
    if (tab === "pending") return batch.status === "pending_review";
    if (tab === "needs_metadata") {
      return batch.status === "needs_metadata_review"
        || (batch.status === "pending_review" && batch.confidence < 0.6);
    }
    if (tab === "quarantine") {
      return ["needs_quarantine_review", "quarantined"].includes(batch.status);
    }
    return batch.status === tab;
  });

  const counts: Record<TabKey, number> = {
    all: batches.length,
    pending: batches.filter((batch) => batch.status === "pending_review").length,
    needs_metadata: batches.filter((batch) => (
      batch.status === "needs_metadata_review"
      || (batch.status === "pending_review" && batch.confidence < 0.6)
    )).length,
    quarantine: batches.filter(
      (batch) => ["needs_quarantine_review", "quarantined"].includes(batch.status),
    ).length,
    approved: batches.filter((batch) => batch.status === "approved").length,
    moved: batches.filter((batch) => batch.status === "moved").length,
  };

  const handleSelectOne = (id: number, checked: boolean) => {
    setSelected((previous) => {
      const next = new Set(previous);
      if (checked) next.add(id);
      else next.delete(id);
      return next;
    });
  };

  const handleSelectAll = (checked: boolean) => {
    setSelected(checked ? new Set(filtered.map((batch) => batch.id)) : new Set());
  };

  const selectedBatches = batches.filter((batch) => selected.has(batch.id));

  const handleLoadDetail = async (id: number) => {
    if (details[id] || detailLoading.has(id)) return;
    setDetailLoading((previous) => new Set(previous).add(id));
    setDetailErrors((previous) => {
      const next = { ...previous };
      delete next[id];
      return next;
    });
    try {
      const [detail, moves] = await Promise.all([
        api.getBatch(id),
        api.getBatchMoves(id),
      ]);
      setDetails((previous) => ({ ...previous, [id]: detail }));
      setMoveSummaries((previous) => ({ ...previous, [id]: moves }));
      if (!["video_movie", "video_tv_show"].includes(detail.detected_type)) {
        const review = await api.getBatchReview(id);
        setReviews((previous) => ({ ...previous, [id]: review }));
      }
    } catch (loadError: unknown) {
      const message = loadError instanceof Error ? loadError.message : "Unable to load batch details";
      setDetailErrors((previous) => ({ ...previous, [id]: message }));
    } finally {
      setDetailLoading((previous) => {
        const next = new Set(previous);
        next.delete(id);
        return next;
      });
    }
  };

  const handleApprove = async (id: number) => {
    try {
      const result = await api.approveBatch(id);
      if (result.status !== "approved") {
        showToast(result.message, "error");
      } else {
        showToast(`Batch ${id} approved`);
      }
      await loadBatches();
    } catch {
      showToast("Approve failed", "error");
    }
  };

  const handleReject = async (id: number) => {
    try {
      await api.rejectBatch(id);
      showToast(`Batch ${id} rejected`);
      await loadBatches();
    } catch {
      showToast("Reject failed", "error");
    }
  };

  const handleRecovery = async (id: number) => {
    try {
      await api.sendToRecovery(id);
      showToast(`Batch ${id} sent to recovery`);
      await loadBatches();
    } catch {
      showToast("Recovery failed", "error");
    }
  };

  const handleQuarantine = async (id: number) => {
    const confirmed = window.confirm(
      "Move this item to quarantine?\n\n"
      + "This does not delete anything. It moves the item out of _INGEST "
      + "so it can be reviewed later.",
    );
    if (!confirmed) return;
    try {
      const result = await api.quarantineBatch(id);
      showToast(result.action_message ?? "Item moved to quarantine");
      await loadBatches();
    } catch (quarantineError: unknown) {
      showToast(
        quarantineError instanceof Error
          ? quarantineError.message
          : "Quarantine move failed",
        "error",
      );
    }
  };

  const handleRestoreQuarantine = async (id: number) => {
    const confirmed = window.confirm(
      "Restore this quarantined item to _INGEST?\n\n"
      + "The old quarantine batch will be retired so a new scan can classify it again.",
    );
    if (!confirmed) return;
    try {
      const result = await api.restoreQuarantinedBatch(id);
      showToast(result.action_message ?? "Item restored to ingest");
      await loadBatches();
    } catch (restoreError: unknown) {
      showToast(
        restoreError instanceof Error
          ? restoreError.message
          : "Restore from quarantine failed",
        "error",
      );
    }
  };

  const handleMetadataSave = async (update: BatchMetadataUpdate) => {
    if (!editingBatch) return;
    setSavingMetadata(true);
    try {
      const result = await api.updateBatchMetadata(editingBatch.id, update);
      showToast(result.action_message ?? `Batch ${editingBatch.id} metadata updated`);
      setEditingBatch(null);
      await loadBatches();
    } catch (saveError: unknown) {
      showToast(
        saveError instanceof Error ? saveError.message : "Metadata update failed",
        "error",
      );
    } finally {
      setSavingMetadata(false);
    }
  };

  const handleDiscographySave = async (update: DiscographyMetadataUpdate) => {
    if (!editingBatch) return;
    setSavingMetadata(true);
    try {
      const result = await api.updateDiscographyMetadata(editingBatch.id, update);
      showToast(result.action_message ?? "Discography metadata updated");
      setEditingBatch(null);
      await loadBatches();
    } catch (saveError: unknown) {
      showToast(
        saveError instanceof Error ? saveError.message : "Discography update failed",
        "error",
      );
    } finally {
      setSavingMetadata(false);
    }
  };

  const handleMovieSave = async (update: MovieMetadataUpdate) => {
    if (!editingBatch) return;
    setSavingMetadata(true);
    try {
      const result = await api.updateMovieMetadata(editingBatch.id, update);
      showToast(result.action_message ?? "Movie metadata updated");
      setEditingBatch(null);
      await loadBatches();
    } catch (saveError: unknown) {
      showToast(
        saveError instanceof Error ? saveError.message : "Movie metadata update failed",
        "error",
      );
    } finally {
      setSavingMetadata(false);
    }
  };

  const handleMovieCollectionSave = async (update: MovieCollectionReviewUpdate) => {
    if (!editingBatch) return;
    setSavingMetadata(true);
    try {
      const result = await api.updateMovieCollectionReview(editingBatch.id, update);
      showToast(result.action_message ?? "Movie collection review saved");
      setEditingBatch(null);
      await loadBatches();
    } catch (saveError: unknown) {
      showToast(
        saveError instanceof Error ? saveError.message : "Movie collection review save failed",
        "error",
      );
    } finally {
      setSavingMetadata(false);
    }
  };

  const handleTvSave = async (update: TvMetadataUpdate) => {
    if (!editingBatch) return;
    setSavingMetadata(true);
    try {
      const result = await api.updateTvMetadata(editingBatch.id, update);
      showToast(result.action_message ?? "TV metadata updated");
      setEditingBatch(null);
      await loadBatches();
    } catch (saveError: unknown) {
      showToast(
        saveError instanceof Error ? saveError.message : "TV metadata update failed",
        "error",
      );
    } finally {
      setSavingMetadata(false);
    }
  };

  const handleBookSave = async (update: BookMetadataUpdate) => {
    if (!editingBatch) return;
    setSavingMetadata(true);
    try {
      const result = await api.updateBookMetadata(editingBatch.id, update);
      showToast(result.action_message ?? "Book metadata updated");
      setEditingBatch(null);
      await loadBatches();
    } catch (saveError: unknown) {
      showToast(
        saveError instanceof Error ? saveError.message : "Book metadata update failed",
        "error",
      );
    } finally {
      setSavingMetadata(false);
    }
  };

  const handleBookCollectionSave = async (update: BookCollectionReviewUpdate) => {
    if (!editingBatch) return;
    setSavingMetadata(true);
    try {
      const result = await api.updateBookCollectionReview(editingBatch.id, update);
      showToast(result.action_message ?? "Book collection review saved");
      setEditingBatch(null);
      await loadBatches();
    } catch (saveError: unknown) {
      showToast(
        saveError instanceof Error ? saveError.message : "Book collection review failed",
        "error",
      );
    } finally {
      setSavingMetadata(false);
    }
  };

  const handleAudiobookSave = async (update: AudiobookMetadataUpdate) => {
    if (!editingBatch) return;
    setSavingMetadata(true);
    try {
      const result = await api.updateAudiobookMetadata(editingBatch.id, update);
      showToast(result.action_message ?? "Audiobook metadata updated");
      setEditingBatch(null);
      await loadBatches();
    } catch (saveError: unknown) {
      showToast(
        saveError instanceof Error
          ? saveError.message
          : "Audiobook metadata update failed",
        "error",
      );
    } finally {
      setSavingMetadata(false);
    }
  };

  const handleTvEpisodeReviewSave = async (update: TvEpisodeReviewUpdate) => {
    if (!editingBatch) return;
    setSavingMetadata(true);
    try {
      const result = await api.updateTvEpisodeReview(editingBatch.id, update);
      showToast(result.action_message ?? "TV episode review saved");
      setEditingBatch(null);
      await loadBatches();
    } catch (saveError: unknown) {
      showToast(
        saveError instanceof Error ? saveError.message : "TV episode review save failed",
        "error",
      );
    } finally {
      setSavingMetadata(false);
    }
  };

  const handleReviewConfirm = async () => {
    if (!editingBatch) return;
    setSavingMetadata(true);
    try {
      const result = await api.updateReviewConfirmation(editingBatch.id, {
        confirmed: true,
        accept_non_blocking_warnings: true,
      });
      showToast(result.action_message ?? "Review confirmed");
      setEditingBatch(null);
      await loadBatches();
    } catch (confirmError: unknown) {
      showToast(
        confirmError instanceof Error ? confirmError.message : "Review confirmation failed",
        "error",
      );
    } finally {
      setSavingMetadata(false);
    }
  };

  const runBulkApprove = async () => {
    const ids = [...selected];
    if (ids.length === 0) return;
    setBulkLoading(true);
    try {
      const result = await api.approveSelected(ids);
      const skippedMetadata = result.errors.filter(
        (error) => error.reason === "metadata_not_confirmed",
      ).length;
      const skippedOther = result.skipped.length - skippedMetadata;
      const parts = [`Approved ${result.approved.length} batch(es).`];
      if (skippedMetadata) parts.push(`Skipped ${skippedMetadata} that need metadata.`);
      if (skippedOther) parts.push(`Skipped ${skippedOther} blocked or invalid batch(es).`);
      showToast(parts.join(" "), result.skipped.length ? "error" : "info");
      setSelected(new Set());
      setShowBulkApprove(false);
      await loadBatches();
    } catch (bulkError: unknown) {
      showToast(
        bulkError instanceof Error ? bulkError.message : "Bulk approval failed",
        "error",
      );
    } finally {
      setBulkLoading(false);
    }
  };

  const runBulkReject = async () => {
    const ids = selectedBatches
      .filter((batch) => batch.status !== "moved")
      .map((batch) => batch.id);
    if (ids.length === 0) return;
    if (!window.confirm(`Reject ${ids.length} selected batch(es)? No files will be deleted.`)) {
      return;
    }
    setBulkLoading(true);
    try {
      const results = await Promise.allSettled(ids.map((id) => api.rejectBatch(id)));
      const completed = results.filter((result) => result.status === "fulfilled").length;
      const failures = results.length - completed;
      showToast(
        `Rejected ${completed} batch(es).${failures ? ` ${failures} failed.` : ""}`,
        failures ? "error" : "info",
      );
      setSelected(new Set());
      await loadBatches();
    } finally {
      setBulkLoading(false);
    }
  };

  const handleRefresh = async () => {
    setLoadingAction("refresh");
    try {
      await loadBatches();
    } finally {
      setLoadingAction(null);
    }
  };

  const handleScan = async () => {
    setLoadingAction("scan");
    try {
      const result = await api.scanMusic();
      const items = await loadBatches();
      const warnings = items.flatMap((batch) => batch.metadata_warnings);
      const tvCounts = result.tv_shows_found > 0
        ? ` | TV shows found: ${result.tv_shows_found} | TV episodes found: ${result.tv_episodes_found}`
        : "";
      setQaSummary({
        title: "Scan summary",
        text: `Movies found: ${result.movie_batches_found}${tvCounts} | Audiobooks found: ${result.audiobook_batches_found} | Music albums found: ${result.music_albums_found} | Discographies found: ${result.discographies_found} | Unknown items: ${result.unknown_items} | Unsupported files: ${result.unsupported_files}`,
        warnings: `Audiobook files found: ${result.audiobook_files_found} | Ignored system files: ${result.ignored_system_files} | Sidecar-only folders skipped: ${result.ignored_sidecar_only_folders} | Artwork files found: ${result.artwork_files_found} | Subtitle files found: ${result.subtitle_files_found} | ${warnings.filter((warning) => warning === "release_folder_grouping_used").length} release-folder grouping used`,
      });
      showToast(`Scan complete - ${result.created} new, ${result.skipped_duplicates} skipped duplicate(s)`);
    } catch {
      showToast("Scan failed", "error");
    } finally {
      setLoadingAction(null);
    }
  };

  const handleReset = async () => {
    const confirmed = window.confirm(
      "Reset all local ingest test data? This restores moved and quarantined "
      + "media to _INGEST, clears every review batch, archive row, report, "
      + "and move log. Reset preserves media files. Media moved out of active "
      + "test folders will be placed in _RECOVERY.",
    );
    if (!confirmed) return;

    setLoadingAction("reset");
    try {
      const result = await api.resetTestData();
      showToast(result.message);
      setQaSummary({
        title: "Reset summary",
        text: `${result.restored_files} files restored · ${result.recovered_media_files ?? 0} existing ingest media files moved to _RECOVERY · ${result.untracked_library_media_files ?? 0} untracked library media files preserved · ${result.cleared_batches} batches cleared · ${result.removed_move_logs} move logs removed · ${result.removed_library_metadata} stale library metadata items removed`,
      });
      setTab("all");
      setSelected(new Set());
      await loadBatches();
    } catch (resetError: unknown) {
      showToast(
        resetError instanceof Error ? resetError.message : "Reset failed",
        "error",
      );
    } finally {
      setLoadingAction(null);
    }
  };

  const handleMove = async () => {
    setLoadingAction("move");
    try {
      const result = await api.moveApproved();
      const errors = result.errors.length ? ` - ${result.errors.join(" | ")}` : "";
      showToast(`Moved ${result.moved} batch(es)${errors}`, result.errors.length ? "error" : "info");
      await loadBatches();
      const summary = await api.getLibrarySummary();
      setLibrarySummary(summary);
      const manifestNames = result.manifests
        .map((manifest) => manifest.markdown_path ?? manifest.json_path)
        .join(" | ");
      setQaSummary({
        title: "Move complete",
        text: `${result.moved} batches moved | ${result.files_moved} files moved | ${result.failed_moves} failed moves`,
        warnings: manifestNames
          ? `Manifests created: ${manifestNames}`
          : "No move manifests were created.",
      });
    } catch {
      showToast("Move failed", "error");
    } finally {
      setLoadingAction(null);
    }
  };

  return (
    <main className="app-shell">
      <ActionBar
        onScan={handleScan}
        onMove={handleMove}
        onRefresh={handleRefresh}
        onReset={handleReset}
        loadingAction={loadingAction}
        devToolsEnabled={devToolsEnabled}
        serverTime={systemTime
          ? `Server time: ${formatArchiveTime(systemTime.server_utc)} ${archiveTimezone()}`
          : null}
        ingestPath={ingestPath}
      />
      <div className="app-content">
        <LibrarySummary summary={librarySummary} />
        {qaSummary && (
          <section className="qa-summary">
            <div>
              <strong>{qaSummary.title}</strong>
              <span>{qaSummary.text}</span>
            </div>
            {qaSummary.warnings && <small>Warnings: {qaSummary.warnings}</small>}
          </section>
        )}
        <StatusTabs
          active={tab}
          counts={counts}
          onChange={(nextTab) => {
            setTab(nextTab);
            setSelected(new Set());
          }}
        />
        <BatchTable
          batches={filtered}
          selected={selected}
          details={details}
          moveSummaries={moveSummaries}
          reviews={reviews}
          detailLoading={detailLoading}
          detailErrors={detailErrors}
          loading={loading}
          error={error ?? undefined}
          bulkLoading={bulkLoading}
          onSelectOne={handleSelectOne}
          onSelectAll={handleSelectAll}
          onLoadDetail={handleLoadDetail}
          onApprove={(id) => void handleApprove(id)}
          onReject={(id) => void handleReject(id)}
          onRecovery={(id) => void handleRecovery(id)}
          onQuarantine={(id) => void handleQuarantine(id)}
          onRestoreQuarantine={(id) => void handleRestoreQuarantine(id)}
          onEdit={setEditingBatch}
          onBulkApprove={() => {
            setShowBulkApprove(true);
            return Promise.resolve();
          }}
          onBulkReject={runBulkReject}
        />
      </div>
      <footer className="app-footer">
        <div className="app-footer__identity">
          <strong>Archive Assistant</strong>
          <span className="app-footer__version">v2.066B</span>
          <span>Move manifest audit trail</span>
        </div>
        <div className="app-footer__notes" aria-label="Application guarantees">
          <span><i className="ti ti-device-desktop" /> Local-first processing</span>
          <span><i className="ti ti-user-check" /> Human approval required</span>
          <span><i className="ti ti-shield-check" /> No automatic moves</span>
        </div>
        <small>Deterministic media review for your NAS library.</small>
      </footer>
      {toast && (
        <Toast
          message={toast.msg}
          type={toast.type}
          visible
          onHide={() => setToast(null)}
        />
      )}
      {editingBatch && (
        <MediaReviewRouter
          batch={editingBatch}
          saving={savingMetadata}
          onMetadataSave={handleMetadataSave}
          onDiscographySave={handleDiscographySave}
          onMovieSave={handleMovieSave}
          onMovieCollectionSave={handleMovieCollectionSave}
          onBookSave={handleBookSave}
          onBookCollectionSave={handleBookCollectionSave}
          onAudiobookSave={handleAudiobookSave}
          onTvSave={handleTvSave}
          onTvEpisodeReviewSave={handleTvEpisodeReviewSave}
          onConfirm={handleReviewConfirm}
          onClose={() => {
            if (!savingMetadata) setEditingBatch(null);
          }}
        />
      )}
      {showBulkApprove && (
        <BulkApproveModal
          batches={selectedBatches}
          loading={bulkLoading}
          onConfirm={() => void runBulkApprove()}
          onClose={() => {
            if (!bulkLoading) setShowBulkApprove(false);
          }}
        />
      )}
    </main>
  );
}
