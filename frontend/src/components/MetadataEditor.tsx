import { useMemo, useState } from "react";
import type {
  BatchMetadataUpdate,
  BatchSummary,
  FieldEnvelope,
  MetadataCandidate,
  MusicTrackProfileSummary,
} from "../types/archive";
import MetadataAssistStaleWarning from "./MetadataAssistStaleWarning";
import MetadataSuggestionChips from "./MetadataSuggestionChips";

type Props = {
  batch: BatchSummary;
  saving: boolean;
  onSave: (update: BatchMetadataUpdate) => Promise<void>;
  onClose: () => void;
};

type IssueLevel = "blocking" | "review" | "info";

const SETUP_WARNINGS = new Set(["embedded_metadata_reader_unavailable", "mutagen_unavailable"]);
const REVIEW_WARNINGS = new Set([
  "year_missing",
  "year_invalid",
  "genre_missing",
  "raw_folder_name_detected",
  "profile_inheritance_stale",
  "track_album_mismatch_detected",
  "track_artist_mismatch_detected",
]);
const DIVIDER = " | ";

const OPTIONAL_FIELD_LABELS: Record<string, string> = {
  subgenres: "subgenres",
  moods: "moods",
  energy: "energy",
  era: "era",
  region: "region",
  scene: "scene",
  related_artists: "related artists",
};

function metadataValue(batch: BatchSummary, key: "artist" | "album" | "year" | "genre"): string {
  const suggested = batch.suggested_metadata?.[key];
  if (suggested) return suggested;
  if (key === "genre") return batch.primary_genre ?? "";
  return batch[key] ?? "";
}

function suggestionSource(
  batch: BatchSummary,
  key: "artist" | "album" | "year" | "genre",
): string | null {
  const source = batch.suggested_metadata?.sources?.[key];
  return source ? `Suggested from ${source}` : null;
}

function sanitizePathPart(value: string): string {
  return value.replace(/[<>:"/\\|?*]/g, "_").trim();
}

function destinationRoot(destination?: string | null): string {
  if (!destination) return "data/Music/Library/MP3";
  const normalized = destination.replace(/\\/g, "/");
  const dataIndex = normalized.toLowerCase().indexOf("data/music/library/");
  if (dataIndex >= 0) return normalized.slice(dataIndex).split("/").slice(0, 4).join("/");
  const libraryIndex = normalized.toLowerCase().indexOf("music/library/");
  if (libraryIndex >= 0) return normalized.slice(libraryIndex).split("/").slice(0, 3).join("/");
  return "data/Music/Library/MP3";
}

function readableWarning(value: string): string {
  const labels: Record<string, string> = {
    mixed_embedded_metadata_detected: "Mixed embedded metadata detected",
    track_album_mismatch_detected: "Track album tags differ from this release",
    track_artist_mismatch_detected: "Track artist tags differ from this release",
    compilation_detected: "Compilation detected",
    compilation_prefix_removed: "Compilation prefix removed",
    possible_duplicate_destination: "Possible duplicate destination",
    possible_artist_alias: "Possible artist alias",
    manual_duplicate_batch_merge_performed: "Manual duplicate batch merge performed",
    possible_artist_alias_resolved: "Artist alias resolved",
    possible_archived_duplicate_candidate: "Matching release already archived",
    destination_file_conflict: "Destination filename conflict",
    profile_inheritance_stale: "Profile inheritance needs refresh",
    embedded_metadata_reader_unavailable: "Embedded metadata reader unavailable",
    mutagen_unavailable: "Mutagen unavailable",
    raw_folder_name_detected: "Raw folder name detected",
    genre_missing: "Genre missing",
    year_missing: "Year missing",
    year_invalid: "Year invalid",
    artist_missing: "Artist missing",
    album_missing: "Album missing",
  };
  return labels[value]
    ?? value.replace(/_/g, " ").replace(/^\w/, (letter: string) => letter.toUpperCase());
}

function isPlaceholderValue(value: unknown): boolean {
  if (value === null || value === undefined) return true;
  if (Array.isArray(value)) return value.length === 0;
  if (typeof value === "object") return Object.keys(value).length === 0;
  const normalized = String(value).trim().toLowerCase();
  return [
    "",
    "missing",
    "n/a",
    "none",
    "null",
    "unkn",
    "unknown",
    "unknown album",
    "unknown artist",
    "unknown year",
    "unknown ye",
  ].includes(normalized);
}

function isUnknown(value: string): boolean {
  return isPlaceholderValue(value);
}

function normalizeTrackTitleForDisplay(value: unknown, trackNumber?: unknown): string {
  let current = String(value ?? "").trim();
  const expected = Number.parseInt(String(trackNumber ?? "").match(/\d+/)?.[0] ?? "", 10);
  for (let index = 0; index < 4; index += 1) {
    const combined = current.match(/^\s*0*\d{1,3}\s*-\s*0*(\d{1,3})\s*(?:[-._]\s*)+(.+?)\s*$/);
    const single = combined ?? current.match(/^\s*0*(\d{1,3})\s*(?:[-._]\s*)+(.+?)\s*$/);
    if (!single) break;
    const parsed = Number.parseInt(single[1], 10);
    if (Number.isFinite(expected) && parsed !== expected) break;
    const next = single[2].replace(/_/g, " ").replace(/\s+/g, " ").replace(/^[ ._-]+|[ ._-]+$/g, "");
    if (!next || next === current) break;
    current = next;
  }
  return current;
}
function buildLiveMusicIssues(params: {
  artist: string;
  album: string;
  year: string;
  genre: string;
  originalWarnings: string[];
  acceptedUnknownArtist: boolean;
  acceptedUnknownAlbum: boolean;
  acceptedUnknownYear: boolean;
}) {
  const blockers: string[] = [];
  const warnings: string[] = [];

  if (isUnknown(params.artist) && !params.acceptedUnknownArtist) blockers.push("artist_missing");
  if (isUnknown(params.album) && !params.acceptedUnknownAlbum) blockers.push("album_missing");
  if (!/^(19|20)\d{2}$/.test(params.year.trim())) warnings.push("year_missing");
  if (isUnknown(params.genre)) warnings.push("genre_missing");

  const liveFieldWarnings = new Set([
    "artist_missing",
    "album_missing",
    "year_missing",
    "year_invalid",
    "genre_missing",
  ]);
  for (const warning of params.originalWarnings) {
    if (!liveFieldWarnings.has(warning)) warnings.push(warning);
  }

  return {
    blockers: Array.from(new Set(blockers)),
    warnings: Array.from(new Set(warnings)),
  };
}

function envelopeValue(field?: FieldEnvelope | null): string {
  const value = field?.value;
  if (Array.isArray(value)) return value.join(", ");
  if (isPlaceholderValue(value)) return "Missing";
  return String(value);
}

function sourceLabel(source?: string | null): string {
  const labels: Record<string, string> = {
    manual: "Manual",
    artist_profile: "Artist profile",
    release_profile: "Release profile",
    embedded_tag: "Embedded tag",
    folder_inference: "Folder",
    filename_inference: "Filename",
    track_override: "Track override",
    unknown: "Unknown",
  };
  return labels[source ?? "unknown"] ?? sourceLabel("unknown");
}

function FieldBadge({ field }: { field?: FieldEnvelope | null }) {
  const placeholder = isPlaceholderValue(field?.value);
  const approved = Boolean(field?.approved) && !placeholder;
  const inherited = field?.approval_state === "inherited" && !placeholder;
  const source = sourceLabel(field?.source);
  const status = placeholder ? "Missing" : inherited ? "Inherited" : approved ? "Approved" : "Needs review";
  const tone = placeholder ? "missing" : inherited ? "inherited" : approved ? "approved" : "pending";
  return (
    <span className={`metadata-badge metadata-badge--${tone}`}>
      {status}{DIVIDER}{source}
    </span>
  );
}

function ProfileField({ label, field }: { label: string; field?: FieldEnvelope | null }) {
  return (
    <div className="profile-field">
      <span>{label}</span>
      <strong>{envelopeValue(field)}</strong>
      {field ? <FieldBadge field={field} /> : <span className="metadata-badge metadata-badge--missing">Missing</span>}
    </div>
  );
}

function classifyWarning(warning: string): IssueLevel {
  if (SETUP_WARNINGS.has(warning)) return "info";
  if (REVIEW_WARNINGS.has(warning)) return "review";
  return "info";
}

function groupWarnings(blockers: string[], warnings: string[]) {
  const review: string[] = [];
  const info: string[] = [];
  for (const warning of warnings) {
    if (classifyWarning(warning) === "review") review.push(warning);
    else info.push(warning);
  }
  return {
    blockers: Array.from(new Set(blockers)),
    review: Array.from(new Set(review)),
    info: Array.from(new Set(info)),
  };
}

function CandidatePanel({ candidates }: { candidates: Record<string, MetadataCandidate[]> }) {
  const rows = Object.entries(candidates)
    .flatMap(([field, values]) => values.map((candidate) => ({ field, candidate })))
    .filter(({ candidate }) => !candidate.ignored)
    .slice(0, 12);
  if (rows.length === 0) {
    return <p className="metadata-card__empty">No local candidates are available for this release.</p>;
  }
  return (
    <div className="candidate-list">
      {rows.map(({ field, candidate }) => (
        <div className="candidate-row" key={`${field}-${candidate.source}-${candidate.value}`}>
          <strong>{candidate.value}</strong>
          <span>{field.replace(/_/g, " ")}</span>
          <small>{candidate.confidence_label}{DIVIDER}{candidate.source_label}</small>
        </div>
      ))}
    </div>
  );
}

function TrackInheritanceSection({ tracks }: { tracks: MusicTrackProfileSummary[] }) {
  const visible = tracks.slice(0, 24);
  if (tracks.length === 0) {
    return <p className="metadata-card__empty">Track inheritance profiles will appear after metadata is saved or rescanned.</p>;
  }
  return (
    <div className="track-inheritance-list">
      {visible.map((track, index) => {
        const profile = track.track_profile ?? {};
        return (
          <div className="track-inheritance-row" key={`${track.file_name ?? "track"}-${index}`}>
            <span>{index + 1}</span>
            <strong>{normalizeTrackTitleForDisplay(envelopeValue(profile.track_title) || track.file_name || "Untitled track", profile.track_number?.value ?? profile.tracknumber?.value ?? index + 1)}</strong>
            <small>{envelopeValue(profile.genre ?? profile.primary_genre)}</small>
            <FieldBadge field={profile.genre ?? profile.primary_genre} />
          </div>
        );
      })}
      {tracks.length > visible.length && (
        <p className="metadata-card__empty">{tracks.length - visible.length} additional tracks are summarized in the inheritance counts.</p>
      )}
    </div>
  );
}

export default function MusicAlbumReviewEditor({
  batch,
  saving,
  onSave,
  onClose,
}: Props) {
  const [artist, setArtist] = useState(() => metadataValue(batch, "artist"));
  const [album, setAlbum] = useState(() => metadataValue(batch, "album"));
  const [year, setYear] = useState(() => metadataValue(batch, "year"));
  const [genre, setGenre] = useState(() => metadataValue(batch, "genre"));
  const [note, setNote] = useState(
    () => String(batch.suggested_metadata?.note ?? ""),
  );
  const [acceptedUnknownArtist, setAcceptedUnknownArtist] = useState(
    Boolean(batch.accepted_unknown_album_artist),
  );
  const [acceptedUnknownAlbum, setAcceptedUnknownAlbum] = useState(
    Boolean(batch.accepted_unknown_album_title),
  );
  const [acceptedUnknownYear, setAcceptedUnknownYear] = useState(
    Boolean(batch.accepted_unknown_year),
  );
  const [lookupLater, setLookupLater] = useState(Boolean(batch.lookup_later));
  const candidates = batch.metadata_candidates ?? {};
  const summary = batch.music_review_summary;
  const artistProfile = summary?.artist_profile ?? {};
  const releaseProfile = summary?.release_profile ?? {};
  const trackProfiles = summary?.track_profiles ?? [];

  const preview = useMemo(() => {
    const root = destinationRoot(batch.suggested_destination);
    const artistFolder = sanitizePathPart(artist);
    const albumFolder = year.trim()
      ? `${year.trim()} - ${sanitizePathPart(album)}`
      : sanitizePathPart(album);
    return {
      artistFolder,
      albumFolder,
      fullPath: `${root}/${artistFolder}/${albumFolder}`,
    };
  }, [album, artist, batch.suggested_destination, year]);

  const liveIssues = useMemo(
    () => buildLiveMusicIssues({
      artist,
      album,
      year,
      genre,
      originalWarnings: batch.metadata_warnings ?? [],
      acceptedUnknownArtist,
      acceptedUnknownAlbum,
      acceptedUnknownYear,
    }),
    [
      artist,
      album,
      year,
      genre,
      batch.metadata_warnings,
      acceptedUnknownArtist,
      acceptedUnknownAlbum,
      acceptedUnknownYear,
    ],
  );

  const issueGroups = useMemo(
    () => groupWarnings(liveIssues.blockers, liveIssues.warnings),
    [liveIssues],
  );
  const missingOptional = (summary?.missing_optional_fields ?? []).map((field) => OPTIONAL_FIELD_LABELS[field] ?? field);
  const inheritedFields = summary?.inherited_fields ?? [];
  const inheritedTrackCount = summary?.inherited_to_track_count ?? 0;
  const setupWarnings = summary?.setup_warnings ?? [];

  const artistReady = !isUnknown(artist) || acceptedUnknownArtist;
  const albumReady = !isUnknown(album) || acceptedUnknownAlbum;
  const yearReady = /^(19|20)\d{2}$/.test(year.trim())
    || acceptedUnknownYear
    || year.trim() === "";
  const valid = artistReady && albumReady && yearReady;

  return (
    <div className="modal-backdrop" role="presentation" onMouseDown={onClose}>
      <form
        className="metadata-editor metadata-editor--wide metadata-cockpit"
        onMouseDown={(event) => event.stopPropagation()}
        onSubmit={(event) => {
          event.preventDefault();
          if (!valid) return;
          void onSave({
            artist: isUnknown(artist) ? "Unknown Artist" : artist.trim(),
            album: isUnknown(album) ? "Unknown Album" : album.trim(),
            year: /^(19|20)\d{2}$/.test(year.trim()) ? year.trim() : null,
            primary_genre: genre.trim() || null,
            format: batch.format ?? "MP3",
            note: note.trim() || null,
            accepted_unknown_album_artist: acceptedUnknownArtist,
            accepted_unknown_album_title: acceptedUnknownAlbum,
            accepted_unknown_year: acceptedUnknownYear,
            lookup_later: lookupLater,
          });
        }}
      >
        <div className="editor-shell__header metadata-cockpit__header">
          <div>
            <span className="metadata-cockpit__eyebrow">Music Album{DIVIDER}{batch.status.replace(/_/g, " ")}</span>
            <h2>{artist || "Unknown Artist"}{DIVIDER}{album || "Unknown Album"}</h2>
            <p>
              {batch.track_count} tracks{DIVIDER}{batch.disc_count} disc{batch.disc_count === 1 ? "" : "s"}{DIVIDER}{batch.format ?? "Unknown format"}{DIVIDER}Confidence {Math.round((batch.confidence ?? 0) * 100)}%
            </p>
          </div>
          <button type="button" className="btn-sm" title="Close" onClick={onClose}>
            <i className="ti ti-x" />
          </button>
        </div>

        <div className="editor-shell__body metadata-cockpit__body">
          <MetadataAssistStaleWarning batch={batch} />

          <section className="metadata-cockpit__hero">
            <div>
              <span>Move readiness</span>
              <strong>{valid && issueGroups.blockers.length === 0 ? "Ready after save" : "Needs review"}</strong>
              <small>{batch.metadata_quality.replace(/_/g, " ")} metadata{DIVIDER}{summary?.profile_consistency === "stale" ? "profile stale" : "profile consistent"}</small>
            </div>
            <div>
              <span>Destination</span>
              <code>{preview.fullPath}</code>
            </div>
          </section>

          <section className="metadata-card metadata-card--core">
            <div className="metadata-card__heading">
              <div>
                <h3>Core Metadata</h3>
                <p>Saved values automatically rehydrate inheritance.</p>
              </div>
              <span className="metadata-badge metadata-badge--approved">
                {summary?.approved_core_fields?.length ?? 0} approved fields
              </span>
            </div>
            <div className="editor-grid">
              <label>
                <span>Album artist</span>
                <input value={artist} onChange={(event) => setArtist(event.target.value)} autoFocus />
                {suggestionSource(batch, "artist") && <small>{suggestionSource(batch, "artist")}</small>}
                <MetadataSuggestionChips label="Album artist" field="album_artist" candidates={candidates.album_artist ?? []} currentValue={artist} onApply={setArtist} />
              </label>
              <label>
                <span>Album title</span>
                <input value={album} onChange={(event) => setAlbum(event.target.value)} />
                {suggestionSource(batch, "album") && <small>{suggestionSource(batch, "album")}</small>}
                <MetadataSuggestionChips label="Album title" field="album_title" candidates={candidates.album_title ?? []} currentValue={album} onApply={setAlbum} />
              </label>
              <label>
                <span>Year</span>
                <input value={year} maxLength={4} onChange={(event) => setYear(event.target.value)} />
                {suggestionSource(batch, "year") && <small>{suggestionSource(batch, "year")}</small>}
                <MetadataSuggestionChips label="Year" field="year" candidates={candidates.year ?? []} currentValue={year} onApply={setYear} />
              </label>
              <label>
                <span>Genre</span>
                <input value={genre} onChange={(event) => setGenre(event.target.value)} />
                {suggestionSource(batch, "genre") && <small>{suggestionSource(batch, "genre")}</small>}
                <MetadataSuggestionChips label="Genre" field="genre" candidates={candidates.genre ?? []} currentValue={genre} onApply={setGenre} />
              </label>
            </div>
          </section>

          <div className="metadata-card-grid">
            <section className="metadata-card">
              <div className="metadata-card__heading"><h3>Artist Profile</h3></div>
              <div className="profile-grid">
                <ProfileField label="Artist" field={artistProfile.artist} />
                <ProfileField label="Primary genre" field={artistProfile.primary_genre} />
                <ProfileField label="Subgenres" field={artistProfile.subgenres} />
                <ProfileField label="Moods" field={artistProfile.moods} />
                <ProfileField label="Era" field={artistProfile.era} />
                <ProfileField label="Region" field={artistProfile.region} />
              </div>
            </section>
            <section className="metadata-card">
              <div className="metadata-card__heading"><h3>Release Profile</h3></div>
              <div className="profile-grid">
                <ProfileField label="Release title" field={releaseProfile.release_title} />
                <ProfileField label="Year" field={releaseProfile.year} />
                <ProfileField label="Genre" field={releaseProfile.genre} />
                <ProfileField label="Primary genre" field={releaseProfile.primary_genre} />
                <ProfileField label="Release type" field={releaseProfile.release_type} />
                <ProfileField label="Format" field={releaseProfile.format} />
              </div>
            </section>
          </div>

          <section className="metadata-card metadata-card--summary">
            <div className="metadata-card__heading"><h3>Inheritance Summary</h3></div>
            <div className="inheritance-summary-grid">
              <div><strong>{inheritedTrackCount}</strong><span>tracks inherited approved release metadata</span></div>
              <div><strong>{inheritedFields.length || 0}</strong><span>inherited field groups</span></div>
              <div><strong>{missingOptional.length}</strong><span>optional radio fields still missing</span></div>
              <div><strong>{setupWarnings.length}</strong><span>setup notices</span></div>
            </div>
            <p className="metadata-card__note">
              {inheritedFields.length > 0
                ? `Inherited fields: ${inheritedFields.map((field) => field.replace(/_/g, " ")).join(", ")}.`
                : "Core inheritance will be rebuilt after the next save."}
            </p>
            {missingOptional.length > 0 && (
              <p className="metadata-card__note">Still missing optional radio fields: {missingOptional.join(", ")}.</p>
            )}
          </section>

          {(issueGroups.blockers.length > 0 || issueGroups.review.length > 0 || issueGroups.info.length > 0) && (
            <section className="metadata-card warning-card">
              <div className="metadata-card__heading"><h3>Review Signals</h3></div>
              {issueGroups.blockers.length > 0 && <IssueList title="Blocking" issues={issueGroups.blockers} tone="blocking" />}
              {issueGroups.review.length > 0 && <IssueList title="Needs review" issues={issueGroups.review} tone="review" />}
              {issueGroups.info.length > 0 && <IssueList title="Informational" issues={issueGroups.info} tone="info" />}
              {setupWarnings.includes("embedded_metadata_reader_unavailable") && (
                <p className="setup-warning-copy">
                  Embedded metadata reader unavailable. Install backend requirements or confirm Mutagen is installed if you want tag extraction during scans. Manual review can continue.
                </p>
              )}
            </section>
          )}

          <section className="metadata-card">
            <div className="metadata-card__heading"><h3>Track Inheritance</h3><span>{trackProfiles.length} track profiles</span></div>
            <TrackInheritanceSection tracks={trackProfiles} />
          </section>

          <section className="metadata-card">
            <div className="metadata-card__heading"><h3>Candidate Suggestions</h3></div>
            <CandidatePanel candidates={candidates} />
          </section>

          <section className="acceptance-controls">
            <div>
              <strong>Accepted unknown metadata</strong>
              <p>Explicit choices remain visible in the move manifest.</p>
            </div>
            <div className="acceptance-controls__buttons">
              <button type="button" className={`btn-sm${acceptedUnknownArtist ? " btn-sm--active" : ""}`} onClick={() => setAcceptedUnknownArtist((value) => !value)}>
                {acceptedUnknownArtist ? "Unknown Artist Accepted" : "Accept Unknown Artist"}
              </button>
              <button type="button" className={`btn-sm${acceptedUnknownAlbum ? " btn-sm--active" : ""}`} onClick={() => setAcceptedUnknownAlbum((value) => !value)}>
                {acceptedUnknownAlbum ? "Unknown Album Accepted" : "Accept Unknown Album Title"}
              </button>
              <button type="button" className={`btn-sm${acceptedUnknownYear ? " btn-sm--active" : ""}`} onClick={() => setAcceptedUnknownYear((value) => !value)}>
                {acceptedUnknownYear ? "Unknown Year Accepted" : "Accept Unknown Year"}
              </button>
              <button type="button" className={`btn-sm${lookupLater ? " btn-sm--active" : ""}`} onClick={() => setLookupLater((value) => !value)}>
                {lookupLater ? "Lookup Later Marked" : "Lookup Later"}
              </button>
            </div>
          </section>

          <div className="editor-grid editor-grid--full">
            <label>
              <span>Review note optional</span>
              <input value={note} onChange={(event) => setNote(event.target.value)} />
            </label>
          </div>

          <details className="metadata-card metadata-details-drawer">
            <summary>Advanced metadata details</summary>
            <pre>{JSON.stringify({ summary, warnings: batch.metadata_warnings }, null, 2)}</pre>
          </details>

          {!valid && <p className="metadata-editor__error">Album artist and title must be supplied or explicitly accepted as unknown. Invalid years must be corrected or accepted.</p>}
        </div>

        <div className="editor-shell__footer">
          <button type="button" className="btn" disabled={saving} onClick={onClose}>Cancel</button>
          <button type="submit" className="btn btn--green" disabled={saving || !valid}>
            <i className={`ti ti-${saving ? "loader-2 spinner" : "device-floppy"}`} />
            Save metadata review
          </button>
        </div>
      </form>
    </div>
  );
}

function IssueList({ title, issues, tone }: { title: string; issues: string[]; tone: IssueLevel }) {
  return (
    <div className={`issue-group issue-group--${tone}`}>
      <strong>{title}</strong>
      {issues.map((issue) => (
        <span key={issue}>{readableWarning(issue)}</span>
      ))}
    </div>
  );
}
