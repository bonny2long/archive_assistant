import { useMemo, useState } from "react";
import type { BatchMetadataUpdate, BatchSummary } from "../types/archive";

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
    possible_duplicate_destination: "Possible duplicate destination",
    possible_artist_alias: "Possible artist alias",
  };
  return labels[value]
    ?? value.replace(/_/g, " ").replace(/^\w/, (letter: string) => letter.toUpperCase());
}

export default function MetadataEditor({ batch, saving, onSave, onClose }: Props) {
  const [artist, setArtist] = useState(() => metadataValue(batch, "artist"));
  const [album, setAlbum] = useState(() => metadataValue(batch, "album"));
  const [year, setYear] = useState(() => metadataValue(batch, "year"));
  const [genre, setGenre] = useState(() => metadataValue(batch, "genre"));

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

  const valid = artist.trim() !== ""
    && album.trim() !== ""
    && /^(19|20)\d{2}$/.test(year.trim());

  return (
    <div className="modal-backdrop" role="presentation" onMouseDown={onClose}>
      <form
        className="metadata-editor"
        onMouseDown={(event) => event.stopPropagation()}
        onSubmit={(event) => {
          event.preventDefault();
          if (!valid) return;
          void onSave({
            artist: artist.trim(),
            album: album.trim(),
            year: year.trim(),
            primary_genre: genre.trim() || null,
            format: batch.format ?? "MP3",
          });
        }}
      >
        <div className="metadata-editor__header">
          <div>
            <h2>Correct metadata</h2>
            <p>Batch {batch.id}. Saving confirms these values for review.</p>
          </div>
          <button type="button" className="btn-sm" title="Close" onClick={onClose}>
            <i className="ti ti-x" />
          </button>
        </div>
        {batch.metadata_warnings.length > 0 && (
          <div className="metadata-editor__warnings">
            {batch.metadata_warnings.map((warning) => (
              <span key={warning}><i className="ti ti-alert-triangle" />{readableWarning(warning)}</span>
            ))}
          </div>
        )}
        <label>
          <span>Artist</span>
          <input value={artist} onChange={(event) => setArtist(event.target.value)} autoFocus />
          {suggestionSource(batch, "artist") && <small>{suggestionSource(batch, "artist")}</small>}
        </label>
        <label>
          <span>Album</span>
          <input value={album} onChange={(event) => setAlbum(event.target.value)} />
          {suggestionSource(batch, "album") && <small>{suggestionSource(batch, "album")}</small>}
        </label>
        <div className="metadata-editor__row">
          <label>
            <span>Year</span>
            <input value={year} maxLength={4} onChange={(event) => setYear(event.target.value)} />
            {suggestionSource(batch, "year") && <small>{suggestionSource(batch, "year")}</small>}
          </label>
          <label>
            <span>Genre</span>
            <input value={genre} onChange={(event) => setGenre(event.target.value)} />
            {suggestionSource(batch, "genre") && <small>{suggestionSource(batch, "genre")}</small>}
          </label>
        </div>
        <div className="metadata-editor__preview">
          <span>Destination preview</span>
          <div><small>Artist folder</small><strong>{preview.artistFolder || "-"}</strong></div>
          <div><small>Album folder</small><strong>{preview.albumFolder || "-"}</strong></div>
          <div><small>Full path</small><code>{preview.fullPath}</code></div>
        </div>
        {!valid && <p className="metadata-editor__error">Artist, album, and a four-digit year are required.</p>}
        <div className="metadata-editor__actions">
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
