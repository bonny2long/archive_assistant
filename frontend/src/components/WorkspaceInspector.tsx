import { useEffect, useState } from "react";
import { api } from "../api/client";
import type {
  BatchUniversalIngestion,
  CandidateMember,
  CandidateMovePreview,
  MediaIdentityCandidate,
  UniversalReviewActionType,
  UniversalReviewActionUpdate,
} from "../types/archive";
import type { CandidateViewModel } from "./ReviewWorkspace";

type Props = {
  vm: CandidateViewModel | null;
  ingestion: BatchUniversalIngestion;
  batchId: number;
  savingActionId: number | null;
  actionError: string | null;
  onAction: (
    candidateId: number,
    actionType: UniversalReviewActionType,
    overrides?: Partial<UniversalReviewActionUpdate>,
  ) => Promise<void>;
  onClear: (actionId: number, candidateId: number) => Promise<void>;
  showTech: boolean;
  onCloseTech: () => void;
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

function formatActionLabel(actionType: string): string {
  return actionType.replace(/_/g, " ");
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

function MemberList({ members }: { members: CandidateMember[] }) {
  return (
    <section className="workspace-inspector__section">
      <h3>Files</h3>
      <div className="workspace-inspector__files">
        {members.slice(0, 12).map((member) => (
          <div key={member.id}>
            <strong>{memberLabel(member)}</strong>
            <small>{member.relative_path}</small>
          </div>
        ))}
        {members.length > 12 && <small>{members.length - 12} more file(s)</small>}
      </div>
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
  savingActionId,
  actionError,
  onAction,
  onClear,
  showTech,
  onCloseTech,
}: Props) {
  const [editingIdentity, setEditingIdentity] = useState(false);
  const [pendingIdentitySave, setPendingIdentitySave] = useState(false);
  const [identitySavedFlash, setIdentitySavedFlash] = useState(false);
  const [editingMediaClass, setEditingMediaClass] = useState(false);
  const [pendingMediaClassSave, setPendingMediaClassSave] = useState(false);
  const [mediaClassSavedFlash, setMediaClassSavedFlash] = useState(false);
  const [previewRefreshKey, setPreviewRefreshKey] = useState(0);

  useEffect(() => {
    setEditingIdentity(false);
    setPendingIdentitySave(false);
    setIdentitySavedFlash(false);
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
    if (!identitySavedFlash) return;
    const timer = window.setTimeout(() => setIdentitySavedFlash(false), 2400);
    return () => window.clearTimeout(timer);
  }, [identitySavedFlash]);

  useEffect(() => {
    if (!mediaClassSavedFlash) return;
    const timer = window.setTimeout(() => setMediaClassSavedFlash(false), 2400);
    return () => window.clearTimeout(timer);
  }, [mediaClassSavedFlash]);

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
          <i className="ti ti-alert-triangle" /> Chunked source folders need manual identity review before approval.
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

      <div className="workspace-inspector__actions">
        <button
          className="btn btn--green"
          disabled={approveDisabled}
          onClick={() => void onAction(vm.id, "approve_candidate", { reason: "workspace_approved" })}
        >
          <i className={`ti ti-${saving ? "loader-2 spinner" : "check"}`} /> Approve candidate
        </button>
        <button
          className="btn btn--compact"
          disabled={saving}
          onClick={() => void onAction(vm.id, "mark_review_later", { reason: "workspace_review_later" })}
        >
          <i className="ti ti-clock" /> Review later
        </button>
        <button
          className="btn btn--compact"
          disabled={saving}
          onClick={() => void onAction(vm.id, "block_candidate", { reason: "workspace_blocked" })}
        >
          <i className="ti ti-ban" /> Block
        </button>
      </div>

      {vm.activeActions.length > 0 && (
        <section className="workspace-inspector__section">
          <h3>Active Actions</h3>
          <div className="workspace-inspector__actions-list">
            {vm.activeActions.map((action) => (
              <div key={action.id}>
                <span>{formatActionLabel(action.action_type)}</span>
                <button className="btn-sm" disabled={saving} onClick={() => void onClear(action.id, vm.id)}>
                  <i className="ti ti-eraser" /> Clear
                </button>
              </div>
            ))}
          </div>
        </section>
      )}

      <EvidenceRows candidate={candidate} />
      <DestinationPreview batchId={batchId} candidateId={vm.id} refreshKey={previewRefreshKey} />
      <MemberList members={candidate.members} />

      {showTech && (
        <section className="workspace-inspector__tech">
          <div>
            <strong>Technical Snapshot</strong>
            <button className="btn-sm" onClick={onCloseTech}><i className="ti ti-x" /></button>
          </div>
          <pre>{JSON.stringify({ batchId, candidate, summary: ingestion.summary }, null, 2)}</pre>
        </section>
      )}
    </aside>
  );
}
