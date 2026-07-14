import { useCallback, useEffect, useRef, useState } from "react";
import type {
  BatchMetadataUpdate,
  AudiobookMetadataUpdate,
  BatchMoveSummary,
  BatchReview,
  BatchSummary,
  BookCollectionReviewUpdate,
  BookMetadataUpdate,
  DiscographyMetadataUpdate,
  DuplicateFragmentResolutionRequest,
  DuplicateFragmentReview,
  IngestBatch,
  LibrarySummary as LibrarySummaryData,
  MovieCollectionReviewUpdate,
  MovieMetadataUpdate,
  MoveResult,
  ScanJobStatus,
  SelectedMoveResult,
  SystemTimeResponse,
  TabKey,
  TvMetadataUpdate,
  TvEpisodeReviewUpdate,
  UniversalReviewActionUpdate,
} from "./types/archive";
import { api } from "./api/client";
import ActionBar from "./components/ActionBar";
import SuiteNav from "./components/SuiteNav";
import BatchTable from "./components/BatchTable";
import StatusTabs from "./components/StatusTabs";
import Toast from "./components/Toast";
import LibrarySummary from "./components/LibrarySummary";
import BulkApproveModal from "./components/BulkApproveModal";
import MediaReviewRouter from "./components/MediaReviewRouter";
import ReviewWorkspace from "./components/ReviewWorkspace";
import DuplicateFragmentReviewWorkspace from "./components/DuplicateFragmentReviewWorkspace";
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
  auditRecords?: string[];
  notices?: string[];
  warnings?: string[];
  errors?: string[];
};

const AUDIO_FILE_EXTENSIONS = new Set([
  ".aac", ".aiff", ".alac", ".flac", ".m4a", ".m4b", ".mp3",
  ".ogg", ".opus", ".wav", ".wma",
]);

function attachedAudioFileIds(batch: IngestBatch): number[] {
  return batch.files
    .filter((file) => AUDIO_FILE_EXTENSIONS.has(file.extension.toLowerCase()))
    .map((file) => file.id);
}

function isProcessedContainerBatch(batch: BatchSummary): boolean {
  return Boolean(batch.parent_media_extraction_complete || batch.parent_is_drained || batch.parent_container_state === "drained_parent" || batch.display_state === "drained_parent");
}

function isPendingReviewBatch(batch: BatchSummary): boolean {
  return !isProcessedContainerBatch(batch) && batch.status === "pending_review";
}

function isNeedsMetadataBatch(batch: BatchSummary): boolean {
  return !isProcessedContainerBatch(batch) && (
    batch.status === "needs_metadata_review"
    || (batch.status === "pending_review" && batch.confidence < 0.6)
  );
}
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
  const [isInitialLoadingBatches, setIsInitialLoadingBatches] = useState(false);
  const [isRefreshingBatches, setIsRefreshingBatches] = useState(false);
  const [isScanningIngest, setIsScanningIngest] = useState(false);
  const [hasLoadedBatches, setHasLoadedBatches] = useState(false);
  const [bulkLoading, setBulkLoading] = useState(false);
  const [showBulkApprove, setShowBulkApprove] = useState(false);
  const [batchLoadError, setBatchLoadError] = useState<string | null>(null);
  const [tab, setTab] = useState<TabKey>("all");
  const [selected, setSelected] = useState<Set<number>>(new Set());
  const [toast, setToast] = useState<ToastState | null>(null);
  const [loadingAction, setLoadingAction] = useState<ActionKey | null>(null);
  const [editingBatch, setEditingBatch] = useState<BatchSummary | null>(null);
  const [workspaceBatch, setWorkspaceBatch] = useState<BatchSummary | null>(null);
  const [workspaceDetail, setWorkspaceDetail] = useState<IngestBatch | null>(null);
  const [workspaceError, setWorkspaceError] = useState<string | null>(null);
  const [duplicateReviewBatch, setDuplicateReviewBatch] = useState<BatchSummary | null>(null);
  const [duplicateReview, setDuplicateReview] = useState<DuplicateFragmentReview | null>(null);
  const [duplicateReviewError, setDuplicateReviewError] = useState<string | null>(null);
  const [savingMetadata, setSavingMetadata] = useState(false);
  const [devToolsEnabled, setDevToolsEnabled] = useState(false);
  const [librarySummary, setLibrarySummary] = useState<LibrarySummaryData>(EMPTY_LIBRARY_SUMMARY);
  const [qaSummary, setQaSummary] = useState<QaSummary | null>(null);
  const [systemTime, setSystemTime] = useState<SystemTimeResponse | null>(null);
  const [ingestPath, setIngestPath] = useState<string | null>(null);
  const [scanStatus, setScanStatus] = useState<ScanJobStatus | null>(null);
  const batchLoadRequestId = useRef(0);
  const hasLoadedBatchesRef = useRef(false);
  const initialLoadStartedRef = useRef(false);

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

  const loadBatches = useCallback(async (options: { resetCachedDetails?: boolean; mode?: "initial" | "refresh" } = {}): Promise<BatchSummary[]> => {
    const requestId = batchLoadRequestId.current + 1;
    batchLoadRequestId.current = requestId;
    const initialLoad = options.mode === "initial" || !hasLoadedBatchesRef.current;

    if (initialLoad) {
      setIsInitialLoadingBatches(true);
    } else {
      setIsRefreshingBatches(true);
    }
    setBatchLoadError(null);

    const applyItems = (items: BatchSummary[]) => {
      if (requestId !== batchLoadRequestId.current) return false;
      setBatches(items);
      hasLoadedBatchesRef.current = true;
      setHasLoadedBatches(true);
      if (options.resetCachedDetails) {
        setDetails({});
        setMoveSummaries({});
        setReviews({});
      }
      return true;
    };

    try {
      const response = await api.listBatches();
      const items = response.items.filter((batch) => batch.status !== "merged");
      return applyItems(items) ? items : [];
    } catch (primaryError: unknown) {
      if (requestId === batchLoadRequestId.current) {
        setBatchLoadError(
          primaryError instanceof Error
            ? primaryError.message
            : "Could not load batches. Backend may be unavailable.",
        );
      }
      return [];
    } finally {
      if (requestId === batchLoadRequestId.current) {
        await loadLibrarySummary();
        setIsInitialLoadingBatches(false);
        setIsRefreshingBatches(false);
      }
    }
  }, [loadLibrarySummary]);

  useEffect(() => {
    if (initialLoadStartedRef.current) return;
    initialLoadStartedRef.current = true;
    void loadBatches({ resetCachedDetails: true, mode: "initial" });
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
    void api.scanStatus()
      .then((status) => setScanStatus(status))
      .catch(() => setScanStatus(null));
  }, [loadBatches]);

  useEffect(() => {
    if (scanStatus?.status !== "running" || !scanStatus.job_id) return;

    let cancelled = false;
    let lastBatchReload = 0;

    const applyCompletedScan = async (status: ScanJobStatus) => {
      const items = await loadBatches({ mode: "refresh" });
      if (cancelled) return;
      const result = status.result;
      if (!result) return;
      const warnings = items.flatMap((batch) => batch.metadata_warnings);
      const tvCounts = result.tv_shows_found > 0
        ? ` | TV shows found: ${result.tv_shows_found} | TV episodes found: ${result.tv_episodes_found}`
        : "";
      setQaSummary({
        title: "Scan summary",
        text: `Movies found: ${result.movie_batches_found}${tvCounts} | Audiobooks found: ${result.audiobook_batches_found} | Music albums found: ${result.music_albums_found} | Discographies found: ${result.discographies_found} | Unknown items: ${result.unknown_items} | Unsupported files: ${result.unsupported_files}`,
        notices: [`Audiobook files found: ${result.audiobook_files_found} | Ignored system files: ${result.ignored_system_files} | Sidecar-only folders skipped: ${result.ignored_sidecar_only_folders} | Artwork files found: ${result.artwork_files_found} | Subtitle files found: ${result.subtitle_files_found} | ${warnings.filter((warning) => warning === "release_folder_grouping_used").length} release-folder grouping used`],
      });
      showToast(`Scan complete - ${result.created} new, ${result.skipped_duplicates} skipped duplicate(s)`);
    };

    const poll = async () => {
      try {
        const next = await api.scanStatus();
        if (cancelled) return;
        setScanStatus(next);
        const now = Date.now();
        if (next.status === "running" && now - lastBatchReload >= 4500) {
          lastBatchReload = now;
          void loadBatches({ mode: "refresh" });
        } else if (next.status === "completed") {
          setIsScanningIngest(false);
          await applyCompletedScan(next);
        } else if (next.status === "failed") {
          setIsScanningIngest(false);
          showToast(next.error_message || "Scan failed", "error");
        }
      } catch {
        if (!cancelled) showToast("Unable to read scan status", "error");
      }
    };

    void poll();
    const intervalId = window.setInterval(() => void poll(), 1500);
    return () => {
      cancelled = true;
      window.clearInterval(intervalId);
    };
  }, [scanStatus?.job_id, scanStatus?.status, loadBatches, showToast]);

  const filtered = batches.filter((batch) => {
    if (tab === "all") return true;
    if (tab === "pending") return isPendingReviewBatch(batch);
    if (tab === "needs_metadata") return isNeedsMetadataBatch(batch);
    if (tab === "quarantine") {
      return ["needs_quarantine_review", "quarantined"].includes(batch.status);
    }
    return batch.status === tab;
  });

  const counts: Record<TabKey, number> = {
    all: batches.length,
    pending: batches.filter(isPendingReviewBatch).length,
    needs_metadata: batches.filter(isNeedsMetadataBatch).length,
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
    setSelected(checked ? new Set(filtered.filter((batch) => !isProcessedContainerBatch(batch)).map((batch) => batch.id)) : new Set());
  };

  const selectedBatches = batches.filter((batch) => selected.has(batch.id));
  const workspaceErrorMessage = workspaceBatch ? workspaceError ?? detailErrors[workspaceBatch.id] ?? null : null;

  const duplicateMatchCount = (batch: BatchSummary) => Math.max(batch.possible_fragment_count ?? 0, batch.possible_duplicate_count ?? 0);
  const hasActiveDuplicateReview = (batch: BatchSummary) => Boolean(batch.requires_duplicate_review && duplicateMatchCount(batch) > 0);
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
  const handleOpenWorkspace = async (batch: BatchSummary, forceUniversal = false) => {
    if (!forceUniversal && hasActiveDuplicateReview(batch)) {
      setWorkspaceBatch(null);
      setWorkspaceDetail(null);
      setWorkspaceError(null);
      setDuplicateReviewBatch(batch);
      setDuplicateReview(null);
      setDuplicateReviewError(null);
      try {
        const review = await api.getBatchDuplicateFragmentReview(batch.id);
        if (review.active_cluster === false || review.clusters.length === 0) {
          setDuplicateReviewBatch(null);
          setDuplicateReview(null);
          setWorkspaceBatch(batch);
          setWorkspaceDetail(null);
          setWorkspaceError(null);
          const detail = details[batch.id] ?? await api.getBatch(batch.id);
          setDetails((previous) => ({ ...previous, [batch.id]: detail }));
          setWorkspaceDetail(detail);
          void handleLoadDetail(batch.id);
          return;
        }
        setDuplicateReview(review);
      } catch (openError: unknown) {
        const message = openError instanceof Error ? openError.message : "Unable to open Duplicate / Fragment Review";
        setDuplicateReviewError(message);
        showToast(message, "error");
      }
      return;
    }

    setDuplicateReviewBatch(null);
    setDuplicateReview(null);
    setDuplicateReviewError(null);
    setWorkspaceBatch(batch);
    setWorkspaceDetail(null);
    setWorkspaceError(null);
    try {
      const detail = details[batch.id] ?? await api.getBatch(batch.id);
      setDetails((previous) => ({ ...previous, [batch.id]: detail }));
      setWorkspaceDetail(detail);
      void handleLoadDetail(batch.id);
    } catch (openError: unknown) {
      const message = openError instanceof Error ? openError.message : "Unable to open Review Workspace";
      setWorkspaceError(message);
      showToast(message, "error");
    }
  };

  const handleDuplicateReviewResolution = async (batchId: number, update: DuplicateFragmentResolutionRequest) => {
    const result = await api.resolveDuplicateFragmentReview(batchId, update);
    showToast(result.message);
    const refreshedBatches = await loadBatches();
    if (result.canonical_batch_id) {
      try {
        const canonicalId = result.canonical_batch_id;
        const [detail] = await Promise.all([
          api.getBatch(canonicalId),
          api.getBatchUniversalIngestion(canonicalId, false),
        ]);
        setDetails((previous) => ({ ...previous, [canonicalId]: detail }));
        if (update.action === "merge_into_one_batch" || update.action === "append_to_existing_canonical_batch") {
          const canonicalSummary = refreshedBatches.find((batch) => batch.id === canonicalId) ?? null;
          setDuplicateReviewBatch(null);
          setDuplicateReview(null);
          setDuplicateReviewError(null);
          setWorkspaceBatch(canonicalSummary);
          setWorkspaceDetail(canonicalSummary ? detail : null);
          setWorkspaceError(null);
        } else {
          setWorkspaceDetail((current) => current?.id === canonicalId ? detail : current);
        }
      } catch {
        // Dashboard refresh still succeeded; stale detail will reload when opened.
      }
    }
    try {
      const review = await api.getBatchDuplicateFragmentReview(batchId);
      setDuplicateReview(review);
      if (review.clusters.length === 0) {
        setDuplicateReviewBatch(null);
        setDuplicateReview(null);
      }
    } catch {
      setDuplicateReviewBatch(null);
      setDuplicateReview(null);
    }
    return result;
  };
  const handleWorkspaceAction = async (batchId: number, update: UniversalReviewActionUpdate) => {
    await api.createUniversalIngestionAction(batchId, update);
    if (update.action_type === "override_media_class") {
      const detail = await api.getBatch(batchId);
      setDetails((previous) => ({ ...previous, [batchId]: detail }));
      setWorkspaceDetail((current) => current?.id === batchId ? detail : current);
      const refreshedBatches = await loadBatches({ mode: "refresh" });
      const refreshedSummary = refreshedBatches.find((batch) => batch.id === batchId);
      if (refreshedSummary) setWorkspaceBatch(refreshedSummary);
    }
  };

  const handleWorkspaceClearAction = async (batchId: number, actionId: number) => {
    await api.clearUniversalIngestionAction(batchId, actionId);
  };

  const handleWorkspaceSplitCandidate = async (batchId: number, candidateId: number) => {
    const result = await api.splitCandidate(batchId, candidateId);
    showToast(`Extracted ${result.artist ?? "artist"} - ${result.album ?? "album"}`);
    try {
      const response = await api.listBatches();
      setBatches(response.items.filter((batch) => batch.status !== "merged"));
    } catch {
      const fallback = await api.listPending();
      setBatches(fallback.items.filter((batch) => batch.status !== "merged"));
    }
    await loadLibrarySummary();
    return result;
  };

  const handleWorkspaceMaterializeApprovedCandidates = async (batchId: number) => {
    const result = await api.createUniversalIngestionChildBatches(batchId);
    showToast(result.message);
    await loadBatches();
    await handleLoadDetail(batchId);
    await loadLibrarySummary();
    return result;
  };
  const handleApprove = async (id: number) => {
    try {
      const result = await api.approveBatch(id);
      if (result.status !== "approved") {
        showToast(result.message, "error");
      } else {
        showToast(`Batch ${id} approved`);
      }
      await loadBatches({ mode: "refresh" });
    } catch {
      showToast("Approve failed", "error");
    }
  };

  const handleReject = async (id: number) => {
    try {
      await api.rejectBatch(id);
      showToast(`Batch ${id} rejected`);
      await loadBatches({ mode: "refresh" });
    } catch {
      showToast("Reject failed", "error");
    }
  };

  const handleRecovery = async (id: number) => {
    try {
      await api.sendToRecovery(id);
      showToast(`Batch ${id} sent to recovery`);
      await loadBatches({ mode: "refresh" });
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
      await loadBatches({ mode: "refresh" });
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
      await loadBatches({ mode: "refresh" });
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
      await loadBatches({ mode: "refresh" });
    } catch (saveError: unknown) {
      showToast(
        saveError instanceof Error ? saveError.message : "Metadata update failed",
        "error",
      );
    } finally {
      setSavingMetadata(false);
    }
  };

  const handleMediaTypeChange = async (target: "music_album" | "audiobook") => {
    if (!editingBatch) return;
    const targetLabel = target === "audiobook" ? "Audiobook" : "Music album";
    let currentBatch: IngestBatch;
    try {
      currentBatch = details[editingBatch.id] ?? await api.getBatch(editingBatch.id);
    } catch {
      showToast("Could not load the current attached-file scope. Refresh and try again.", "error");
      return;
    }
    const audioFileIds = attachedAudioFileIds(currentBatch);
    if (!audioFileIds.length) {
      showToast("This batch has no attached audio files to convert.", "error");
      return;
    }
    const confirmed = window.confirm(
      `Change this entire scoped batch and all ${audioFileIds.length} attached audio files to ${targetLabel}? `
      + "Only continue if every attached audio file belongs to this one media object. "
      + "This updates roles and destination, but does not move, delete, or retag files.",
    );
    if (!confirmed) return;
    const batchId = editingBatch.id;
    setSavingMetadata(true);
    try {
      const result = await api.updateBatchMediaType(batchId, target, audioFileIds);
      showToast(result.action_message ?? ("Media type changed to " + target.replace("_", " ")));
      setEditingBatch(result);
      await loadBatches({ mode: "refresh" });
    } catch (saveError: unknown) {
      showToast(
        saveError instanceof Error ? saveError.message : "Media type correction failed",
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
      await loadBatches({ mode: "refresh" });
    } catch (saveError: unknown) {
      showToast(
        saveError instanceof Error ? saveError.message : "Discography update failed",
        "error",
      );
    } finally {
      setSavingMetadata(false);
    }
  };

  const handleDiscographyCreateChildren = async (update: DiscographyMetadataUpdate) => {
    if (!editingBatch) return;
    const batchId = editingBatch.id;
    setSavingMetadata(true);
    try {
      await api.updateDiscographyMetadata(batchId, update);
      const result = await api.splitDiscographyReleases(batchId);
      showToast(result.message);
      setEditingBatch(null);
      await loadBatches({ mode: "refresh" });
    } catch (saveError: unknown) {
      showToast(
        saveError instanceof Error ? saveError.message : "Discography child batch creation failed",
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
      await loadBatches({ mode: "refresh" });
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
      await loadBatches({ mode: "refresh" });
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
      await loadBatches({ mode: "refresh" });
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
      await loadBatches({ mode: "refresh" });
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
      await loadBatches({ mode: "refresh" });
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
      const savedMessage = result.action_message ?? "Audiobook metadata updated";
      showToast(`${savedMessage} Next: approve this batch from the dashboard.`);
      setEditingBatch(null);
      await loadBatches({ mode: "refresh" });
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
      await loadBatches({ mode: "refresh" });
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
      await loadBatches({ mode: "refresh" });
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
      await loadBatches({ mode: "refresh" });
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
      await loadBatches({ mode: "refresh" });
    } finally {
      setBulkLoading(false);
    }
  };

  const handleRefresh = async () => {
    setLoadingAction("refresh");
    try {
      await loadBatches({ mode: "refresh" });
    } finally {
      setLoadingAction(null);
    }
  };

  const handleScan = async () => {
    setLoadingAction("scan");
    setIsScanningIngest(true);
    try {
      const status = await api.scanMusic();
      setScanStatus(status);
      setIsScanningIngest(status.status === "running");
      if (status.already_running) {
        showToast("Scan already running");
      } else {
        showToast("Scan started");
      }
    } catch (scanError: unknown) {
      setIsScanningIngest(false);
      showToast(
        scanError instanceof Error ? scanError.message : "Scan failed",
        "error",
      );
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
      await loadBatches({ mode: "refresh" });
    } catch (resetError: unknown) {
      showToast(
        resetError instanceof Error ? resetError.message : "Reset failed",
        "error",
      );
    } finally {
      setLoadingAction(null);
    }
  };

  const applyMoveResult = async (
    result: MoveResult | SelectedMoveResult,
    label: string,
  ) => {
    const selectedResult = "results" in result ? result : null;
    const notMoved = selectedResult
      ? selectedResult.results.filter((item) => !item.moved).length
      : 0;
    const hasProblems = (
      result.errors.length > 0
      || result.failed_moves > 0
      || notMoved > 0
    );
    showToast(
      `${label}: moved ${result.moved} batch(es)${notMoved ? `; ${notMoved} blocked or failed` : ""}.`,
      hasProblems ? "error" : "info",
    );
    await loadBatches({ mode: "refresh" });
    const summary = await api.getLibrarySummary();
    setLibrarySummary(summary);
    const hasFailedMoves = result.failed_moves > 0;
    const title = hasFailedMoves
      ? result.files_moved > 0 ? "Move partially complete" : "Move failed"
      : result.warnings.length > 0 ? "Move complete with warnings"
      : result.notices.length > 0 ? "Move complete with notices"
      : "Move complete";
    setQaSummary({
      title,
      text: `${result.moved} batches moved | ${result.files_moved} files moved | ${result.failed_moves} failed moves${notMoved ? ` | ${notMoved} blocked or failed batches` : ""}`,
      auditRecords: result.audit_records,
      notices: result.notices,
      warnings: result.warnings,
      errors: result.errors,
    });
  };

  const runSelectedMove = async () => {
    const ids = selectedBatches.map((batch) => batch.id);
    if (ids.length === 0) return;
    setBulkLoading(true);
    try {
      const preflight = await api.preflightSelectedMove(ids);
      if (preflight.ready_count === 0) {
        const blocker = preflight.batches.flatMap((batch) => batch.blockers)[0];
        showToast(blocker ?? "No selected batches are ready to move.", "error");
        return;
      }
      const confirmed = window.confirm(
        `Move ${preflight.ready_count} approved batch(es) containing exactly ${preflight.source_file_count} source file(s)?`
        + (preflight.blocked_count
          ? `\n\n${preflight.blocked_count} selected batch(es) are blocked and will not move.`
          : "")
        + "\n\nNo destination files will be overwritten.",
      );
      if (!confirmed) return;
      const result = await api.moveSelected(ids);
      await applyMoveResult(result, "Selected move");
      setSelected(new Set());
    } catch (moveError: unknown) {
      showToast(
        moveError instanceof Error ? moveError.message : "Selected move failed",
        "error",
      );
    } finally {
      setBulkLoading(false);
    }
  };

  const handleMoveBatch = async (batchId: number) => {
    setBulkLoading(true);
    try {
      const preflight = await api.preflightSelectedMove([batchId]);
      const check = preflight.batches[0];
      if (!check?.ready) {
        showToast(check?.blockers.join(" ") || "This batch is not ready to move.", "error");
        return;
      }
      if (!window.confirm(
        `Move batch ${batchId} containing exactly ${check.source_file_count} source file(s)?\n\nDestination:\n${check.destination}`,
      )) return;
      const result = await api.moveBatch(batchId);
      await applyMoveResult(result, `Batch ${batchId}`);
    } catch (moveError: unknown) {
      showToast(
        moveError instanceof Error ? moveError.message : "Batch move failed",
        "error",
      );
    } finally {
      setBulkLoading(false);
    }
  };

  const handleMove = async () => {
    setLoadingAction("move");
    try {
      const result = await api.moveApproved();
      await applyMoveResult(result, "Bulk move");
    } catch {
      showToast("Move failed", "error");
    } finally {
      setLoadingAction(null);
    }
  };

  return (
    <main className="app-shell">
      <SuiteNav />
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
        isScanningIngest={isScanningIngest}
      />
      {scanStatus && scanStatus.status !== "idle" && (
        <section className={`scan-status scan-status--${scanStatus.status}`}>
          <div>
            <strong>
              {scanStatus.status === "running"
                ? "Scan running"
                : scanStatus.status === "failed"
                ? "Scan failed"
                : "Scan complete"}
            </strong>
            <span>{scanStatus.phase || scanStatus.message || "Waiting for scan status"}</span>
          </div>
          <small>
            {scanStatus.message ? `${scanStatus.message} | ` : ""}
            {typeof scanStatus.elapsed_seconds === "number"
              ? `${scanStatus.elapsed_seconds.toFixed(1)}s elapsed`
              : "elapsed time unavailable"}
            {scanStatus.current_path ? ` | ${scanStatus.current_path}` : ""}
          </small>
          {scanStatus.error_message ? <small>{scanStatus.error_message}</small> : null}
        </section>
      )}
      <div className="app-content">
        <LibrarySummary summary={librarySummary} />
        {qaSummary && (
          <section className="qa-summary">
            <div>
              <strong>{qaSummary.title}</strong>
              <span>{qaSummary.text}</span>
            </div>
            {qaSummary.auditRecords?.length ? <small>Move manifests written: {qaSummary.auditRecords.join(" | ")}</small> : null}
            {qaSummary.notices?.length ? <small>Notices: {qaSummary.notices.join(" | ")}</small> : null}
            {qaSummary.warnings?.length ? <small>Warnings: {qaSummary.warnings.join(" | ")}</small> : null}
            {qaSummary.errors?.length ? <small>Errors: {qaSummary.errors.join(" | ")}</small> : null}
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
          isInitialLoading={isInitialLoadingBatches}
          isRefreshing={isRefreshingBatches}
          hasLoaded={hasLoadedBatches}
          error={batchLoadError ?? undefined}
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
          onOpenWorkspace={(batch, forceUniversal) => void handleOpenWorkspace(batch, forceUniversal)}
          onBulkApprove={() => {
            setShowBulkApprove(true);
            return Promise.resolve();
          }}
          onBulkReject={runBulkReject}
          onMoveSelected={runSelectedMove}
          onMoveBatch={handleMoveBatch}
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
      {duplicateReviewBatch && !duplicateReview && (
        <div className="review-workspace" role="dialog" aria-modal="true" aria-label="Duplicate Fragment Review loading">
          <div className="review-workspace__state">
            {duplicateReviewError ? (
              <>
                <i className="ti ti-alert-triangle" /> {duplicateReviewError}
                <button
                  className="btn-sm"
                  onClick={() => { setDuplicateReviewBatch(null); setDuplicateReview(null); setDuplicateReviewError(null); }}
                >
                  Close
                </button>
              </>
            ) : (
              <>
                <i className="ti ti-loader-2 spinner" /> Loading Duplicate / Fragment Review...
              </>
            )}
          </div>
        </div>
      )}
      {duplicateReviewBatch && duplicateReview && (
        <DuplicateFragmentReviewWorkspace
          review={duplicateReview}
          selectedBatchId={duplicateReviewBatch.id}
          onClose={() => { setDuplicateReviewBatch(null); setDuplicateReview(null); setDuplicateReviewError(null); }}
          onResolve={handleDuplicateReviewResolution}
          onOpenNormalReview={() => {
            const batch = duplicateReviewBatch;
            setDuplicateReviewBatch(null);
            setDuplicateReview(null);
            setDuplicateReviewError(null);
            setWorkspaceBatch(batch);
            setWorkspaceDetail(null);
            setWorkspaceError(null);
            void (async () => {
              try {
                const detail = details[batch.id] ?? await api.getBatch(batch.id);
                setDetails((previous) => ({ ...previous, [batch.id]: detail }));
                setWorkspaceDetail(detail);
                void handleLoadDetail(batch.id);
              } catch (error: unknown) {
                setWorkspaceError(error instanceof Error ? error.message : "Unable to open Review Workspace");
              }
            })();
          }}
        />
      )}
      {workspaceBatch && !workspaceDetail && (
        <div className="review-workspace" role="dialog" aria-modal="true" aria-label="Review Workspace loading">
          <div className="review-workspace__state">
            {workspaceErrorMessage ? (
              <>
                <i className="ti ti-alert-triangle" /> {workspaceErrorMessage}
                <button
                  className="btn-sm"
                  onClick={() => { setWorkspaceBatch(null); setWorkspaceDetail(null); setWorkspaceError(null); }}
                >
                  Close
                </button>
              </>
            ) : (
              <>
                <i className="ti ti-loader-2 spinner" /> Loading Review Workspace...
              </>
            )}
          </div>
        </div>
      )}
      {workspaceBatch && workspaceDetail && (
        <ReviewWorkspace
          batch={workspaceDetail}
          onClose={() => { setWorkspaceBatch(null); setWorkspaceDetail(null); setWorkspaceError(null); }}
          onSaveAction={handleWorkspaceAction}
          onClearAction={handleWorkspaceClearAction}
          onSplitCandidate={workspaceDetail.detected_type === "music_discography" ? handleWorkspaceSplitCandidate : undefined}
          onMaterializeApprovedCandidates={handleWorkspaceMaterializeApprovedCandidates}
          onApprove={async (batchId) => {
            await handleApprove(batchId);
            setWorkspaceBatch(null);
            setWorkspaceDetail(null);
            setWorkspaceError(null);
          }}
          onOpenFullEditor={() => {
            if (workspaceBatch) setEditingBatch(workspaceBatch);
            setWorkspaceBatch(null);
            setWorkspaceDetail(null);
            setWorkspaceError(null);
          }}
        />
      )}
      {editingBatch && (
        <MediaReviewRouter
          batch={editingBatch}
          saving={savingMetadata}
          onMetadataSave={handleMetadataSave}
          onMediaTypeChange={handleMediaTypeChange}
          onDiscographySave={handleDiscographySave}
          onDiscographyCreateChildren={handleDiscographyCreateChildren}
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
