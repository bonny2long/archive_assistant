import { useCallback, useEffect, useState } from "react";
import type {
  BatchMetadataUpdate,
  BatchMoveSummary,
  BatchReview,
  BatchSummary,
  IngestBatch,
  LibrarySummary as LibrarySummaryData,
  TabKey,
} from "./types/archive";
import { api } from "./api/client";
import ActionBar from "./components/ActionBar";
import BatchTable from "./components/BatchTable";
import StatusTabs from "./components/StatusTabs";
import Toast from "./components/Toast";
import MetadataEditor from "./components/MetadataEditor";
import LibrarySummary from "./components/LibrarySummary";

type ToastState = { msg: string; type: "info" | "error" };
type ActionKey = "refresh" | "scan" | "move" | "reset";

const EMPTY_LIBRARY_SUMMARY: LibrarySummaryData = {
  moved_albums: 0,
  moved_tracks: 0,
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
  const [error, setError] = useState<string | null>(null);
  const [tab, setTab] = useState<TabKey>("all");
  const [selected, setSelected] = useState<Set<number>>(new Set());
  const [toast, setToast] = useState<ToastState | null>(null);
  const [loadingAction, setLoadingAction] = useState<ActionKey | null>(null);
  const [editingBatch, setEditingBatch] = useState<BatchSummary | null>(null);
  const [savingMetadata, setSavingMetadata] = useState(false);
  const [devToolsEnabled, setDevToolsEnabled] = useState(false);
  const [librarySummary, setLibrarySummary] = useState<LibrarySummaryData>(EMPTY_LIBRARY_SUMMARY);

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

  const loadBatches = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const response = await api.listBatches();
      setBatches(response.items.filter((batch) => batch.status !== "merged"));
      setDetails({});
      setMoveSummaries({});
      setReviews({});
    } catch (primaryError: unknown) {
      try {
        const fallback = await api.listPending();
        setBatches(fallback.items.filter((batch) => batch.status !== "merged"));
        setDetails({});
        setMoveSummaries({});
        setReviews({});
      } catch {
        setError(primaryError instanceof Error ? primaryError.message : "Unable to load batches");
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
  }, [loadBatches]);

  const filtered = batches.filter((batch) => {
    if (tab === "all") return true;
    if (tab === "pending") return batch.status === "pending_review";
    if (tab === "needs_metadata") {
      return batch.status === "needs_metadata_review"
        || (batch.status === "pending_review" && batch.confidence < 0.6);
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
      const review = await api.getBatchReview(id);
      setDetails((previous) => ({ ...previous, [id]: detail }));
      setMoveSummaries((previous) => ({ ...previous, [id]: moves }));
      setReviews((previous) => ({ ...previous, [id]: review }));
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

  const runBulkAction = async (action: "approve" | "reject") => {
    const ids = [...selected];
    if (ids.length === 0) return;
    setBulkLoading(true);
    try {
      const results = await Promise.allSettled(ids.map((id) => (
        action === "approve" ? api.approveBatch(id) : api.rejectBatch(id)
      )));
      const failures = results.filter((result) => (
        result.status === "rejected"
        || (action === "approve" && result.status === "fulfilled" && result.value.status !== "approved")
      )).length;
      const completed = ids.length - failures;
      showToast(
        `${completed} batch(es) ${action === "approve" ? "approved" : "rejected"}${failures ? `, ${failures} failed` : ""}`,
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
      showToast(
        `Scan complete - ${result.created} new, ${result.skipped_duplicates} skipped duplicate(s)`,
      );
      await loadBatches();
    } catch {
      showToast("Scan failed", "error");
    } finally {
      setLoadingAction(null);
    }
  };

  const handleReset = async () => {
    const confirmed = window.confirm(
      "Reset local music test data? This restores moved test tracks to _INGEST "
      + "and clears music test batches. It will not delete your source tracks.",
    );
    if (!confirmed) return;

    setLoadingAction("reset");
    try {
      const result = await api.resetMusicTest();
      showToast(result.message);
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
      />
      <div className="app-content">
        <LibrarySummary summary={librarySummary} />
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
          onEdit={setEditingBatch}
          onBulkApprove={() => runBulkAction("approve")}
          onBulkReject={() => runBulkAction("reject")}
        />
      </div>
      {toast && (
        <Toast
          message={toast.msg}
          type={toast.type}
          visible
          onHide={() => setToast(null)}
        />
      )}
      {editingBatch && (
        <MetadataEditor
          batch={editingBatch}
          saving={savingMetadata}
          onSave={handleMetadataSave}
          onClose={() => {
            if (!savingMetadata) setEditingBatch(null);
          }}
        />
      )}
    </main>
  );
}
