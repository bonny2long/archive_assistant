import { useMemo, useState } from "react";
import type { BatchMetadataUpdate, BatchSummary } from "../types/archive";
import MetadataAssistStaleWarning from "./MetadataAssistStaleWarning";
import MetadataSuggestionChips from "./MetadataSuggestionChips";

type Props = {
  batch: BatchSummary;
  saving: boolean;
  onSave: (update: BatchMetadataUpdate) => Promise<void>;
  onClose: () => void;
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
    track_album_mismatch_detected: "Some track album tags differ from the release folder",
    track_artist_mismatch_detected: "Some track artist tags differ from the release folder",
    compilation_detected: "Compilation detected",
    compilation_prefix_removed: "Compilation prefix removed",
    possible_duplicate_destination: "Possible duplicate destination",
    possible_artist_alias: "Possible artist alias",
    manual_duplicate_batch_merge_performed: "Manual duplicate batch merge performed",
    possible_artist_alias_resolved: "Artist alias resolved",
    possible_archived_duplicate_candidate: "Matching release already archived",
    destination_file_conflict: "Destination filename conflict",
  };
  return labels[value]
    ?? value.replace(/_/g, " ").replace(/^\w/, (letter: string) => letter.toUpperCase());
}

function isUnknown(value: string): boolean {
  const normalized = value.trim().toLowerCase();
  return normalized === ""
    || normalized === "unknown"
    || normalized === "unknown artist"
    || normalized === "unknown album"
    || normalized === "unkn";
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

  const artistReady = !isUnknown(artist) || acceptedUnknownArtist;
  const albumReady = !isUnknown(album) || acceptedUnknownAlbum;
  const yearReady = /^(19|20)\d{2}$/.test(year.trim())
    || acceptedUnknownYear
    || year.trim() === "";
  const valid = artistReady && albumReady && yearReady;

  return (
    <div className="modal-backdrop" role="presentation" onMouseDown={onClose}>
      <form
        className="metadata-editor metadata-editor--wide"
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
        {/* ── Header ── */}
        <div className="editor-shell__header">
          <div>
            <h2>Review music album</h2>
            <p>Batch {batch.id}. Save metadata corrections after review.</p>
          </div>
          <button type="button" className="btn-sm" title="Close" onClick={onClose}>
            <i className="ti ti-x" />
          </button>
        </div>

        {/* ── Body ── */}
        <div className="editor-shell__body">
          <MetadataAssistStaleWarning batch={batch} />
          {(liveIssues.blockers.length > 0 || liveIssues.warnings.length > 0) && (
            <section className="review-issues">
              <div className="review-issues__summary">
                <strong>{liveIssues.blockers.length > 0 ? "Review required" : "Review available"}</strong>
                <span>
                  {liveIssues.blockers.length} blocking item(s) · {liveIssues.warnings.length} warning(s)
                </span>
              </div>
              {liveIssues.blockers.length > 0 && (
                <div>
                  <h3>Blocking issues</h3>
                  {liveIssues.blockers.map((issue) => (
                    <p key={issue}>
                      <i className="ti ti-alert-triangle" />
                      {readableWarning(issue)}
                    </p>
                  ))}
                </div>
              )}
              {liveIssues.warnings.length > 0 && (
                <div>
                  <h3>Warnings</h3>
                  {liveIssues.warnings.map((issue) => (
                    <p key={issue}>
                      <i className="ti ti-info-circle" />
                      {readableWarning(issue)}
                    </p>
                  ))}
                </div>
              )}
            </section>
          )}

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

          <div className="editor-grid editor-grid--full">
            <label>
              <span>Review note optional</span>
              <input value={note} onChange={(event) => setNote(event.target.value)} />
            </label>
          </div>

          <div className="metadata-editor__preview">
            <span>Destination preview</span>
            <div><small>Artist folder</small><strong>{preview.artistFolder || "-"}</strong></div>
            <div><small>Album folder</small><strong>{preview.albumFolder || "-"}</strong></div>
            <div><small>Full path</small><code>{preview.fullPath}</code></div>
          </div>
          {!valid && <p className="metadata-editor__error">Album artist and title must be supplied or explicitly accepted as unknown. Invalid years must be corrected or accepted.</p>}
        </div>

        {/* ── Footer ── */}
        <div className="editor-shell__footer">
          <button type="button" className="btn" disabled={saving} onClick={onClose}>Cancel</button>
          <button type="submit" className="btn btn--green" disabled={saving || !valid}>
            <i className={`ti ti-${saving ? "loader-2 spinner" : "device-floppy"}`} />
            Save
          </button>
        </div>
      </form>
    </div>
  );
}
