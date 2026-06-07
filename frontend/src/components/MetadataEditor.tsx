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

function sanitizePathPart(value: string): string {
  return value.replace(/[<>:"/\\|?*]/g, "_").trim();
}

function destinationRoot(destination?: string | null): string {
  if (!destination) return "Music/Library/MP3";
  const match = destination.match(/^(.*?[\\/]Music[\\/]Library[\\/](?:MP3|FLAC))/i);
  return match?.[1] ?? "Music/Library/MP3";
}

export default function MetadataEditor({ batch, saving, onSave, onClose }: Props) {
  const [artist, setArtist] = useState(() => metadataValue(batch, "artist"));
  const [album, setAlbum] = useState(() => metadataValue(batch, "album"));
  const [year, setYear] = useState(() => metadataValue(batch, "year"));
  const [genre, setGenre] = useState(() => metadataValue(batch, "genre"));

  const preview = useMemo(() => {
    const root = destinationRoot(batch.suggested_destination);
    const folder = year.trim() ? `${year.trim()} - ${sanitizePathPart(album)}` : sanitizePathPart(album);
    return `${root}\\${sanitizePathPart(artist)}\\${folder}`;
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
        <label>
          <span>Artist</span>
          <input value={artist} onChange={(event) => setArtist(event.target.value)} autoFocus />
        </label>
        <label>
          <span>Album</span>
          <input value={album} onChange={(event) => setAlbum(event.target.value)} />
        </label>
        <div className="metadata-editor__row">
          <label>
            <span>Year</span>
            <input value={year} maxLength={4} onChange={(event) => setYear(event.target.value)} />
          </label>
          <label>
            <span>Genre</span>
            <input value={genre} onChange={(event) => setGenre(event.target.value)} />
          </label>
        </div>
        <div className="metadata-editor__preview">
          <span>Destination preview</span>
          <code>{preview}</code>
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
