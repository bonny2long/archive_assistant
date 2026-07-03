import { useEffect, useState } from "react";
import { api } from "../api/client";
import type {
  BatchUniversalIngestion,
  CandidateMember,
  CandidateMovePreview,
  MediaIdentityCandidate,
  SplitCandidateResult,
  UniversalReviewActionType,
  UniversalReviewActionUpdate,
} from "../types/archive";
import type { CandidateViewModel } from "./ReviewWorkspace";

type Props = {
  vm: CandidateViewModel | null;
  ingestion: BatchUniversalIngestion;
  batchId: number;
  workspaceRefreshKey: number;
  savingActionId: number | null;
  actionError: string | null;
  onAction: (
    candidateId: number,
    actionType: UniversalReviewActionType,
    overrides?: Partial<UniversalReviewActionUpdate>,
  ) => Promise<void>;
  onClear: (actionId: number, candidateId: number) => Promise<void>;
  onSplitCandidate?: (candidateId: number) => Promise<SplitCandidateResult>;
  showTech: boolean;
  onCloseTech: () => void;
  onOpenFullEditor?: () => void;
};

type EvidenceCandidate = MediaIdentityCandidate & {
  identity_evidence_json?: Record<string, unknown> | null;
};

type PreviewEntry = CandidateMovePreview["preview_groups"][number] & {
  suggested_destination?: string;
  destination?: string;
};

type CandidateMovePreviewWithFallbacks = CandidateMovePreview & {
  candidates?: PreviewEntry[];
  items?: PreviewEntry[];
};

const BOOK_LIKE_TYPES = new Set(["audiobook", "ebook", "comic"]);

const MEDIA_CLASS_OPTIONS: Array<{ value: string; label: string }> = [
  { value: "music_audio", label: "Music" },
  { value: "audiobook_audio", label: "Audiobook" },
  { value: "ebook", label: "Ebook" },
  { value: "comic", label: "Comic" },
  { value: "movie", label: "Movie" },
  { value: "tv_episode", label: "TV Episode" },
  { value: "artwork", label: "Artwork" },
  { value: "sidecar_metadata", label: "Sidecar / Metadata" },
  { value: "unknown", label: "Unknown" },
];

function mediaClassLabel(value: string | null | undefined): string {
  const match = MEDIA_CLASS_OPTIONS.find((option) => option.value === value);
  return match?.label ?? value ?? "Unknown";
}

function formatActionLabel(action: { action_type: string; target_media_class?: string | null }): string {
  const labels: Record<string, string> = {
    approve_candidate: "Approved for move plan",
    mark_review_later: "Marked for later review",
    override_identity: "Identity override saved",
    exclude_from_move_plan: "Excluded from move plan",
    block_candidate: "Blocked by user",
    split_candidate: "Split required",
    merge_candidates: "Merge requested",
  };
  if (action.action_type === "override_media_class") {
    return `Media type changed to ${mediaClassLabel(action.target_media_class)}`;
  }
  return labels[action.action_type] ?? action.action_type.replace(/_/g, " ");
}

function memberLabel(member: CandidateMember): string {
  const parts = [member.title, member.artist_or_author, member.album_or_series].filter(Boolean);
  return parts.length ? parts.join(" | ") : member.filename;
}

function DestinationPreview({
  batchId,
  candidateId,
  refreshKey,
}: {
  batchId: number;
  candidateId: number;
  refreshKey: number;
}) {
  const [preview, setPreview] = useState<CandidateMovePreview | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    api.getCandidateMovePreview(batchId)
      .then((data) => {
        if (!cancelled) setPreview(data);
      })
      .catch((previewError: unknown) => {
        if (!cancelled) {
          setError(previewError instanceof Error ? previewError.message : "Could not load destination preview");
        }
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [batchId, refreshKey]);

  const previewWithFallbacks = preview as CandidateMovePreviewWithFallbacks | null;
  const entry = (
    previewWithFallbacks?.preview_groups.find((group) => group.candidate_id === candidateId)
    ?? previewWithFallbacks?.candidates?.find((candidate) => candidate.candidate_id === candidateId)
    ?? previewWithFallbacks?.items?.find((item) => item.candidate_id === candidateId)
    ?? null
  ) as PreviewEntry | null;
  const destination = entry?.destination_preview
    ?? entry?.suggested_destination
    ?? entry?.destination
    ?? "Destination pending";

  return (
    <section className="workspace-inspector__section">
      <h3>Destination Preview</h3>
      {loading && <small className="workspace-inspector__preview-loading"><i className="ti ti-loader-2 spinner" /> Loading...</small>}
      {!loading && error && <small className="workspace-inspector__preview-error">{error}</small>}
      {!loading && !error && entry && (
        <code className="workspace-inspector__dest-path">{destination}</code>
      )}
      {!loading && !error && !entry && (
        <small className="workspace-inspector__preview-empty">No destination preview available for this candidate.</small>
      )}
      <small>Backend move planning is authoritative. This preview updates after identity changes.</small>
    </section>
  );
}

function EvidenceRows({ candidate }: { candidate: EvidenceCandidate }) {
  const evidence = candidate.identity_evidence_json ?? {};
  const evidenceEntries = Object.entries(evidence);
  return (
    <section className="workspace-inspector__section">
      <h3>Identity Evidence</h3>
      <dl className="workspace-inspector__evidence">
        <div><dt>Candidate key</dt><dd>{candidate.candidate_key}</dd></div>
        <div><dt>Confidence</dt><dd>{candidate.candidate_confidence_label}</dd></div>
        <div><dt>Reason</dt><dd>{candidate.summary_reason || "No summary reason"}</dd></div>
        {evidenceEntries.slice(0, 6).map(([key, value]) => (
          <div key={key}><dt>{key}</dt><dd>{String(value)}</dd></div>
        ))}
      </dl>
    </section>
  );
}

function isCollectionCandidate(vm: CandidateViewModel): boolean {
  return vm.fileCount > 3 && vm.sourceFragmentCount >= 1;
}

function SimpleFileList({ members }: { members: CandidateMember[] }) {
  return (
    <section className="workspace-inspector__section">
      <h3>Files</h3>
      <div className="workspace-inspector__files">
        {members.slice(0, 12).map((member) => (
          <div key={member.id} className="workspace-inspector__file-row">
            <strong>{memberLabel(member)}</strong>
            <small>{member.relative_path}</small>
          </div>
        ))}
        {members.length > 12 && (
          <small className="workspace-inspector__files-more">{members.length - 12} more file(s)</small>
        )}
      </div>
    </section>
  );
}

function CollectionMembersPanel({
  vm,
  saving,
  onAction,
}: {
  vm: CandidateViewModel;
  saving: boolean;
  onAction: (
    candidateId: number,
    actionType: UniversalReviewActionType,
    overrides?: Partial<UniversalReviewActionUpdate>,
  ) => Promise<void>;
}) {
  const members = vm.rawCandidate.members ?? [];
  const grouped = members.reduce<Record<string, CandidateMember[]>>((acc, member) => {
    const key = member.album_or_series || member.title || member.filename;
    if (!acc[key]) acc[key] = [];
    acc[key].push(member);
    return acc;
  }, {});
  const groups = Object.entries(grouped);
  const [excluded, setExcluded] = useState<Set<string>>(new Set());

  function toggleGroup(key: string) {
    const memberIds = grouped[key].map((member) => member.id);
    const include = excluded.has(key);
    setExcluded((current) => {
      const next = new Set(current);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });
    void onAction(vm.id, "override_identity", {
      note: JSON.stringify({ member_group_key: key, member_ids: memberIds, include }),
      reason: "workspace_member_group_toggle",
    });
  }

  function excludeAll() {
    setExcluded(new Set(groups.map(([key]) => key)));
    void onAction(vm.id, "override_identity", {
      note: JSON.stringify({ member_group_key: "__all__", include: false }),
      reason: "workspace_exclude_all_members",
    });
  }

  function includeAll() {
    setExcluded(new Set());
    void onAction(vm.id, "override_identity", {
      note: JSON.stringify({ member_group_key: "__all__", include: true }),
      reason: "workspace_include_all_members",
    });
  }

  if (groups.length <= 1) {
    return <SimpleFileList members={members} />;
  }

  return (
    <section className="workspace-inspector__section workspace-inspector__collection-panel">
      <div className="workspace-inspector__collection-header">
        <h3>Releases ({groups.length})</h3>
        <div className="workspace-inspector__collection-bulk">
          <button className="btn-sm" disabled={saving} onClick={includeAll}>Include all</button>
          <button className="btn-sm" disabled={saving} onClick={excludeAll}>Exclude all</button>
        </div>
      </div>
      <div className="workspace-inspector__collection-list">
        {groups.map(([key, groupMembers]) => {
          const isExcluded = excluded.has(key);
          const title = groupMembers[0]?.album_or_series || groupMembers[0]?.title || key;
          const creator = groupMembers[0]?.artist_or_author ?? "";
          const fileCount = groupMembers.length;
          return (
            <div
              key={key}
              className={`workspace-inspector__collection-item${isExcluded ? " workspace-inspector__collection-item--excluded" : ""}`}
            >
              <div className="workspace-inspector__collection-item-info">
                <strong>{title}</strong>
                <small>{[creator, `${fileCount} file${fileCount !== 1 ? "s" : ""}`].filter(Boolean).join(" | ")}</small>
              </div>
              <button
                className={`btn-sm${isExcluded ? "" : " btn-sm--active"}`}
                disabled={saving}
                onClick={() => toggleGroup(key)}
                title={isExcluded ? "Click to include" : "Click to exclude"}
              >
                <i className={`ti ti-${isExcluded ? "eye-off" : "check"}`} />
                {isExcluded ? "Excluded" : "Include"}
              </button>
            </div>
          );
        })}
      </div>
      <small className="workspace-inspector__collection-note">
        These are logical groupings of files. Use the full editor for detailed per-release correction.
      </small>
    </section>
  );
}

function IdentityEditForm({
  vm,
  saving,
  onCancel,
  onSave,
}: {
  vm: CandidateViewModel;
  saving: boolean;
  onCancel: () => void;
  onSave: (fields: {
    override_title: string;
    override_primary_creator: string;
    override_year: string;
    override_series?: string;
    override_series_index?: string;
  }) => void;
}) {
  const candidate = vm.rawCandidate;
  const isBookLike = BOOK_LIKE_TYPES.has(vm.mediaType);
  const [title, setTitle] = useState(candidate.candidate_title ?? "");
  const [creator, setCreator] = useState(candidate.candidate_primary_creator ?? "");
  const [year, setYear] = useState(candidate.candidate_year ?? "");
  const [series, setSeries] = useState(candidate.candidate_series ?? "");
  const [seriesIndex, setSeriesIndex] = useState(candidate.candidate_series_index ?? "");

  return (
    <section className="workspace-inspector__section workspace-inspector__identity-edit">
      <h3>Edit identity</h3>
      <label className="workspace-inspector__field">
        <span>Title</span>
        <input value={title} disabled={saving} onChange={(event) => setTitle(event.target.value)} />
      </label>
      <label className="workspace-inspector__field">
        <span>{isBookLike ? "Author" : "Creator"}</span>
        <input value={creator} disabled={saving} onChange={(event) => setCreator(event.target.value)} />
      </label>
      <label className="workspace-inspector__field">
        <span>Year</span>
        <input value={year} disabled={saving} onChange={(event) => setYear(event.target.value)} />
      </label>
      {isBookLike && (
        <>
          <label className="workspace-inspector__field">
            <span>Series</span>
            <input value={series} disabled={saving} onChange={(event) => setSeries(event.target.value)} />
          </label>
          <label className="workspace-inspector__field">
            <span>Series index</span>
            <input value={seriesIndex} disabled={saving} onChange={(event) => setSeriesIndex(event.target.value)} />
          </label>
        </>
      )}
      <div className="workspace-inspector__actions">
        <button
          className="btn btn--green"
          disabled={saving || !title.trim()}
          onClick={() => onSave({
            override_title: title.trim(),
            override_primary_creator: creator.trim(),
            override_year: year.trim(),
            ...(isBookLike
              ? { override_series: series.trim(), override_series_index: seriesIndex.trim() }
              : {}),
          })}
        >
          <i className={`ti ti-${saving ? "loader-2 spinner" : "check"}`} /> Save identity
        </button>
        <button className="btn btn--compact" disabled={saving} onClick={onCancel}>
          Cancel
        </button>
      </div>
    </section>
  );
}

function MediaClassOverrideForm({
  vm,
  saving,
  onCancel,
  onSave,
}: {
  vm: CandidateViewModel;
  saving: boolean;
  onCancel: () => void;
  onSave: (targetMediaClass: string) => void;
}) {
  const mediaTypeToClass: Record<string, string> = {
    music: "music_audio",
    audiobook: "audiobook_audio",
    ebook: "ebook",
    comic: "comic",
    movie: "movie",
    tv: "tv_episode",
    artwork: "artwork",
    unknown: "unknown",
  };
  const [selected, setSelected] = useState(mediaTypeToClass[vm.mediaType] ?? "unknown");

  return (
    <section className="workspace-inspector__section workspace-inspector__class-override">
      <h3>Change media type</h3>
      <p className="workspace-inspector__class-override-hint">
        AA classified this as <strong>{vm.mediaType}</strong>. If that is wrong, select the correct type below and save. This does not move any files.
      </p>
      <label className="workspace-inspector__field">
        <span>Media type</span>
        <select
          value={selected}
          disabled={saving}
          onChange={(event) => setSelected(event.target.value)}
        >
          {MEDIA_CLASS_OPTIONS.map(({ value, label }) => (
            <option key={value} value={value}>{label}</option>
          ))}
        </select>
      </label>
      <div className="workspace-inspector__actions">
        <button
          className="btn btn--green"
          disabled={saving}
          onClick={() => onSave(selected)}
        >
          <i className={`ti ti-${saving ? "loader-2 spinner" : "check"}`} /> Save media type
        </button>
        <button className="btn btn--compact" disabled={saving} onClick={onCancel}>
          Cancel
        </button>
      </div>
    </section>
  );
}

export default function WorkspaceInspector({
  vm,
  ingestion,
  batchId,
  workspaceRefreshKey,
  savingActionId,
  actionError,
  onAction,
  onClear,
  onSplitCandidate,
  showTech,
  onCloseTech,
  onOpenFullEditor,
}: Props) {
  const [editingIdentity, setEditingIdentity] = useState(false);
  const [pendingIdentitySave, setPendingIdentitySave] = useState(false);
  const [identitySavedFlash, setIdentitySavedFlash] = useState(false);
  const [editingMediaClass, setEditingMediaClass] = useState(false);
  const [pendingMediaClassSave, setPendingMediaClassSave] = useState(false);
  const [mediaClassSavedFlash, setMediaClassSavedFlash] = useState(false);
  const [pendingExclude, setPendingExclude] = useState(false);
  const [excludeSavedFlash, setExcludeSavedFlash] = useState(false);
  const [pendingSplit, setPendingSplit] = useState(false);
  const [splitResult, setSplitResult] = useState<SplitCandidateResult | null>(null);
  const [splitError, setSplitError] = useState<string | null>(null);
  const [previewRefreshKey, setPreviewRefreshKey] = useState(0);

  useEffect(() => {
    setEditingIdentity(false);
    setPendingIdentitySave(false);
    setIdentitySavedFlash(false);
    setPendingExclude(false);
    setExcludeSavedFlash(false);
    setPendingSplit(false);
    setSplitResult(null);
    setSplitError(null);
  }, [vm?.id]);

  useEffect(() => {
    setEditingMediaClass(false);
    setPendingMediaClassSave(false);
    setMediaClassSavedFlash(false);
  }, [vm?.id]);

  useEffect(() => {
    if (!pendingIdentitySave) return;
    if (savingActionId === vm?.id) return;
    setPendingIdentitySave(false);
    if (actionError) return;
    setEditingIdentity(false);
    setIdentitySavedFlash(true);
    setPreviewRefreshKey((key) => key + 1);
  }, [savingActionId, actionError, pendingIdentitySave, vm?.id]);

  useEffect(() => {
    if (!pendingMediaClassSave) return;
    if (savingActionId === vm?.id) return;
    setPendingMediaClassSave(false);
    if (actionError) return;
    setEditingMediaClass(false);
    setMediaClassSavedFlash(true);
    setPreviewRefreshKey((key) => key + 1);
  }, [savingActionId, actionError, pendingMediaClassSave, vm?.id]);

  useEffect(() => {
    if (!pendingExclude) return;
    if (savingActionId === vm?.id) return;
    setPendingExclude(false);
    if (actionError) return;
    setExcludeSavedFlash(true);
    setPreviewRefreshKey((key) => key + 1);
  }, [savingActionId, actionError, pendingExclude, vm?.id]);

  useEffect(() => {
    if (!identitySavedFlash) return;
    const timer = window.setTimeout(() => setIdentitySavedFlash(false), 2400);
    return () => window.clearTimeout(timer);
  }, [identitySavedFlash]);

  useEffect(() => {
    if (!mediaClassSavedFlash) return;
    const timer = window.setTimeout(() => setMediaClassSavedFlash(false), 2400);
    return () => window.clearTimeout(timer);
  }, [mediaClassSavedFlash]);

  useEffect(() => {
    if (!excludeSavedFlash) return;
    const timer = window.setTimeout(() => setExcludeSavedFlash(false), 2400);
    return () => window.clearTimeout(timer);
  }, [excludeSavedFlash]);

  if (!vm) {
    return <aside className="workspace-inspector workspace-inspector--empty">Select a candidate to review.</aside>;
  }

  const candidate = vm.rawCandidate as EvidenceCandidate;
  const saving = savingActionId === vm.id;
  const approveDisabled = vm.hasChunkIdentityRisk || saving;

  return (
    <aside className="workspace-inspector" aria-label="Candidate inspector">
      <div className="workspace-inspector__header">
        <div>
          <span>{vm.mediaType}</span>
          <h2>{vm.title}</h2>
          <p>{vm.creator} | {vm.year}</p>
        </div>
        <span className={`workspace-inspector__state workspace-inspector__state--${vm.displayState}`}>{vm.displayState}</span>
      </div>

      {vm.hasChunkIdentityRisk && (
        <div className="workspace-inspector__warning">
          <i className="ti ti-alert-triangle" /> A source folder name appears to be used as this candidate identity. Review identity before approval.
        </div>
      )}
      {actionError && <div className="workspace-inspector__warning workspace-inspector__warning--error">{actionError}</div>}

      <div className="workspace-inspector__identity-edit-toggle">
        <button
          className="btn-sm"
          disabled={pendingIdentitySave}
          onClick={() => setEditingIdentity((current) => !current)}
        >
          <i className={`ti ti-${editingIdentity ? "x" : "pencil"}`} /> {editingIdentity ? "Cancel edit" : "Edit identity"}
        </button>
        {identitySavedFlash && (
          <span className="workspace-inspector__identity-saved">
            <i className="ti ti-check" /> Identity updated
          </span>
        )}
      </div>

      {editingIdentity && (
        <IdentityEditForm
          vm={vm}
          saving={saving}
          onCancel={() => setEditingIdentity(false)}
          onSave={(fields) => {
            setPendingIdentitySave(true);
            void onAction(vm.id, "override_identity", { ...fields, reason: "workspace_identity_edit" });
          }}
        />
      )}

      <div className="workspace-inspector__identity-edit-toggle workspace-inspector__class-override-toggle">
        <button
          className="btn-sm"
          disabled={pendingMediaClassSave}
          onClick={() => setEditingMediaClass((current) => !current)}
        >
          <i className={`ti ti-${editingMediaClass ? "x" : "tag"}`} /> {editingMediaClass ? "Cancel type change" : "Change media type"}
        </button>
        {mediaClassSavedFlash && (
          <span className="workspace-inspector__identity-saved">
            <i className="ti ti-check" /> Media type updated
          </span>
        )}
      </div>

      {editingMediaClass && (
        <MediaClassOverrideForm
          vm={vm}
          saving={saving}
          onCancel={() => setEditingMediaClass(false)}
          onSave={(targetMediaClass) => {
            setPendingMediaClassSave(true);
            void onAction(vm.id, "override_media_class", {
              target_media_class: targetMediaClass,
              reason: "workspace_media_class_override",
            });
          }}
        />
      )}

      {onSplitCandidate && (
        <section className="workspace-inspector__section workspace-inspector__split-section">
          <h3>Extract as own batch</h3>
          <p>
            This creates a separate album batch for this release and removes its files from the parent discography batch. Files are not moved on disk.
          </p>
          <button
            className="btn btn--compact"
            disabled={saving || pendingSplit}
            onClick={() => {
              setPendingSplit(true);
              setSplitError(null);
              setSplitResult(null);
              void onSplitCandidate(vm.id)
                .then((result) => {
                  setSplitResult(result);
                  setPreviewRefreshKey((key) => key + 1);
                })
                .catch((splitFailure: unknown) => {
                  setSplitError(splitFailure instanceof Error ? splitFailure.message : "Could not extract candidate");
                })
                .finally(() => setPendingSplit(false));
            }}
          >
            <i className={`ti ti-${pendingSplit ? "loader-2 spinner" : "git-branch"}`} /> Extract as own batch
          </button>
          {splitResult && (
            <div className="workspace-inspector__split-result">
              <i className="ti ti-check" />
              <span>
                Created batch {splitResult.child_batch_id} with {splitResult.moved_file_count} file{splitResult.moved_file_count === 1 ? "" : "s"}.
              </span>
            </div>
          )}
          {splitError && <small className="workspace-inspector__preview-error">{splitError}</small>}
        </section>
      )}
      <section className="workspace-inspector__section workspace-inspector__decision-actions-section">
        <h3>Decision</h3>
        <p>Choose what should happen to this candidate in the current review. These actions do not delete files.</p>
        <div className="workspace-inspector__actions">
          <button
            className="btn btn--green"
            disabled={approveDisabled}
            onClick={() => void onAction(vm.id, "approve_candidate", { reason: "workspace_approved" })}
          >
            <i className={`ti ti-${saving ? "loader-2 spinner" : "check"}`} /> {vm.hasChunkIdentityRisk ? "Review identity first" : "Approve candidate"}
          </button>
          <button
            className="btn btn--compact"
            disabled={saving}
            onClick={() => void onAction(vm.id, "mark_review_later", { reason: "workspace_review_later" })}
          >
            <i className="ti ti-clock" /> Review later
          </button>
          <button
            className="btn btn--compact workspace-inspector__exclude-btn"
            disabled={saving || pendingExclude}
            onClick={() => {
              setPendingExclude(true);
              void onAction(vm.id, "exclude_from_move_plan", { reason: "workspace_excluded" });
            }}
          >
            <i className={`ti ti-${pendingExclude ? "loader-2 spinner" : "eye-off"}`} /> Exclude
          </button>
          <button
            className="btn btn--compact"
            disabled={saving}
            onClick={() => void onAction(vm.id, "block_candidate", { reason: "workspace_blocked" })}
          >
            <i className="ti ti-ban" /> Block
          </button>
        </div>
        {excludeSavedFlash && (
          <div className="workspace-inspector__exclude-flash">
            <i className="ti ti-check" /> Excluded from move plan - files are untouched
          </div>
        )}
      </section>

      {vm.activeActions.length > 0 && (
        <section className="workspace-inspector__section workspace-inspector__decisions-section">
          <h3>Decisions</h3>
          <div className="workspace-inspector__actions-list">
            {vm.activeActions.map((action) => (
              <div key={action.id}>
                <span>{formatActionLabel(action)}</span>
                <button className="btn-sm" disabled={saving} onClick={() => void onClear(action.id, vm.id)}>
                  <i className="ti ti-eraser" /> Clear
                </button>
              </div>
            ))}
          </div>
        </section>
      )}

      <EvidenceRows candidate={candidate} />
      <DestinationPreview batchId={batchId} candidateId={vm.id} refreshKey={previewRefreshKey + workspaceRefreshKey} />
      {isCollectionCandidate(vm)
        ? <CollectionMembersPanel vm={vm} saving={saving} onAction={onAction} />
        : <SimpleFileList members={candidate.members} />
      }

      {showTech && (
        <section className="workspace-inspector__tech">
          <div>
            <strong>Technical Snapshot</strong>
            <button className="btn-sm" onClick={onCloseTech}><i className="ti ti-x" /></button>
          </div>
          <pre>{JSON.stringify({ batchId, candidate, summary: ingestion.summary }, null, 2)}</pre>
        </section>
      )}
      {onOpenFullEditor && (
        <section className="workspace-inspector__section workspace-inspector__full-editor-section">
          <div className="workspace-inspector__full-editor-hint">
            <i className="ti ti-external-link" />
            <span>Need full editing power? Open the legacy editor for detailed corrections.</span>
          </div>
          <button className="btn btn--compact" onClick={onOpenFullEditor}>
            <i className="ti ti-pencil" /> Open full editor
          </button>
        </section>
      )}
    </aside>
  );
}
