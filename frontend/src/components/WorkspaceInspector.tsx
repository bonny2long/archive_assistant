import { useEffect, useState } from "react";
import type {
  BatchUniversalIngestion,
  CandidateMember,
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

const BOOK_LIKE_TYPES = new Set(["audiobook", "ebook", "comic"]);

function formatActionLabel(actionType: string): string {
  return actionType.replace(/_/g, " ");
}

function memberLabel(member: CandidateMember): string {
  const parts = [member.title, member.artist_or_author, member.album_or_series].filter(Boolean);
  return parts.length ? parts.join(" | ") : member.filename;
}

function pathSegment(value: string): string {
  return value.trim().replace(/[\\/:*?"<>|]+/g, "-") || "Unknown";
}

function DestinationPreview({ vm }: { vm: CandidateViewModel }) {
  const root = vm.mediaType === "music" ? "Music" : vm.mediaType === "audiobook" ? "Audiobooks" : "Media";
  const creator = pathSegment(vm.creator === "Unknown creator" ? "Unknown" : vm.creator);
  const title = pathSegment(vm.title);
  const year = vm.year === "Unknown year" ? "" : ` (${pathSegment(vm.year)})`;
  return (
    <section className="workspace-inspector__section">
      <h3>Destination Preview</h3>
      <code>{root}\{creator}\{title}{year}</code>
      <small>Frontend preview only. Backend move planning remains authoritative.</small>
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

  useEffect(() => {
    setEditingIdentity(false);
    setPendingIdentitySave(false);
    setIdentitySavedFlash(false);
  }, [vm?.id]);

  useEffect(() => {
    if (!pendingIdentitySave) return;
    if (savingActionId === vm?.id) return;
    setPendingIdentitySave(false);
    if (actionError) return;
    setEditingIdentity(false);
    setIdentitySavedFlash(true);
  }, [savingActionId, actionError, pendingIdentitySave, vm?.id]);

  useEffect(() => {
    if (!identitySavedFlash) return;
    const timer = window.setTimeout(() => setIdentitySavedFlash(false), 2400);
    return () => window.clearTimeout(timer);
  }, [identitySavedFlash]);

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
      <DestinationPreview vm={vm} />
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
