import { useMemo, useState } from "react";
import type {
  BatchSummary,
  DiscographyAlbumUpdate,
  DiscographyMetadataUpdate,
  DiscographyReleaseType,
} from "../types/archive";

type Props = {
  batch: BatchSummary;
  saving: boolean;
  onSave: (update: DiscographyMetadataUpdate) => Promise<void>;
  onClose: () => void;
};

const RELEASE_TYPES: Array<{ value: DiscographyReleaseType; label: string }> = [
  { value: "album", label: "Album" },
  { value: "ep", label: "EP" },
  { value: "single", label: "Single" },
  { value: "compilation", label: "Compilation" },
  { value: "live", label: "Live" },
  { value: "other", label: "Other" },
  { value: "exclude", label: "Exclude" },
];

const RELEASE_BUCKETS: Record<Exclude<DiscographyReleaseType, "exclude">, string> = {
  album: "Albums",
  ep: "EPs",
  single: "Singles",
  compilation: "Compilations",
  live: "Live",
  other: "Other",
};

function sanitizePathPart(value: string): string {
  return value.replace(/[<>:"/\\|?*]/g, "_").trim();
}

function initialAlbums(batch: BatchSummary): DiscographyAlbumUpdate[] {
  return batch.albums.map((album) => {
    const releaseType = album.release_type
      ?? (album.track_count === 1 ? "single" : "album");
    return {
      source_folder: album.source_folder,
      album: album.album,
      year: album.year ?? null,
      release_type: releaseType,
      include: album.include !== false && releaseType !== "exclude",
    };
  });
}

function albumDestination(
  artist: string,
  album: DiscographyAlbumUpdate,
): string {
  if (!album.include || album.release_type === "exclude") {
    return `data/_QUARANTINE/music/discography-excluded/${sanitizePathPart(artist)}/${sanitizePathPart(album.source_folder)}`;
  }
  const releaseType = album.release_type as Exclude<DiscographyReleaseType, "exclude">;
  const folder = album.year
    ? `${album.year} - ${sanitizePathPart(album.album)}`
    : sanitizePathPart(album.album);
  return `Music/Discographies/${sanitizePathPart(artist)}/${RELEASE_BUCKETS[releaseType]}/${folder}`;
}

export default function DiscographyEditor({
  batch,
  saving,
  onSave,
  onClose,
}: Props) {
  const [artist, setArtist] = useState(
    () => batch.suggested_metadata?.artist ?? batch.artist ?? "",
  );
  const [albums, setAlbums] = useState(() => initialAlbums(batch));
  const collectionDestination = useMemo(
    () => `Music/Discographies/${sanitizePathPart(artist)}`,
    [artist],
  );
  const albumsBySource = useMemo(
    () => new Map(batch.albums.map((album) => [album.source_folder, album])),
    [batch.albums],
  );
  const valid = artist.trim().length > 0
    && albums.every((album) => (
      album.album.trim().length > 0
      && (!album.year || /^(19|20)\d{2}$/.test(album.year))
    ));

  const updateAlbum = (
    sourceFolder: string,
    update: Partial<DiscographyAlbumUpdate>,
  ) => {
    setAlbums((current) => current.map((album) => (
      album.source_folder === sourceFolder
        ? { ...album, ...update }
        : album
    )));
  };

  return (
    <div className="modal-backdrop" role="presentation" onMouseDown={onClose}>
      <form
        className="metadata-editor discography-editor"
        onMouseDown={(event) => event.stopPropagation()}
        onSubmit={(event) => {
          event.preventDefault();
          if (valid) void onSave({ artist: artist.trim(), albums });
        }}
      >
        <div className="metadata-editor__header">
          <div>
            <h2>Correct discography</h2>
            <p>Edit the collection and release move plan without changing audio tags.</p>
          </div>
          <button type="button" className="btn-sm" disabled={saving} onClick={onClose}>
            <i className="ti ti-x" />
          </button>
        </div>

        <label>
          <span>Artist</span>
          <input value={artist} autoFocus onChange={(event) => setArtist(event.target.value)} />
        </label>
        <div className="metadata-editor__preview">
          <span>Destination preview</span>
          <code>{collectionDestination}</code>
        </div>

        <div className="discography-editor__table">
          <table>
            <thead>
              <tr>
                <th>Include</th>
                <th>Year</th>
                <th>Album title</th>
                <th>Release type</th>
                <th>Tracks</th>
                <th>Warnings</th>
                <th>Destination preview</th>
              </tr>
            </thead>
            <tbody>
              {albums.map((album) => {
                const source = albumsBySource.get(album.source_folder);
                return (
                  <tr key={album.source_folder}>
                    <td>
                      <input
                        type="checkbox"
                        checked={album.include && album.release_type !== "exclude"}
                        onChange={(event) => updateAlbum(album.source_folder, {
                          include: event.target.checked,
                          release_type: event.target.checked && album.release_type === "exclude"
                            ? "album"
                            : album.release_type,
                        })}
                      />
                    </td>
                    <td>
                      <input
                        className="discography-editor__year"
                        value={album.year ?? ""}
                        placeholder="YYYY"
                        onChange={(event) => updateAlbum(album.source_folder, {
                          year: event.target.value || null,
                        })}
                      />
                    </td>
                    <td>
                      <input
                        value={album.album}
                        onChange={(event) => updateAlbum(album.source_folder, {
                          album: event.target.value,
                        })}
                      />
                    </td>
                    <td>
                      <select
                        value={album.release_type}
                        onChange={(event) => {
                          const releaseType = event.target.value as DiscographyReleaseType;
                          updateAlbum(album.source_folder, {
                            release_type: releaseType,
                            include: releaseType !== "exclude",
                          });
                        }}
                      >
                        {RELEASE_TYPES.map((option) => (
                          <option key={option.value} value={option.value}>{option.label}</option>
                        ))}
                      </select>
                    </td>
                    <td>{source?.track_count ?? 0}</td>
                    <td>{source?.warnings?.join(", ") || "-"}</td>
                    <td><code>{albumDestination(artist, album)}</code></td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>

        <div className="metadata-editor__actions">
          <button type="button" className="btn" disabled={saving} onClick={onClose}>Cancel</button>
          <button type="submit" className="btn btn--green" disabled={saving || !valid}>
            <i className={`ti ti-${saving ? "loader-2 spinner" : "device-floppy"}`} />
            Save discography corrections
          </button>
        </div>
      </form>
    </div>
  );
}
