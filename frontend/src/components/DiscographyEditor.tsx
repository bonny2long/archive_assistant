import { useMemo, useState } from "react";
import type {
  BatchSummary,
  DiscographyAlbumUpdate,
  DiscographyMetadataUpdate,
  DiscographyReleaseType,
} from "../types/archive";
import ReviewIssuesPanel from "./ReviewIssuesPanel";

type Props = {
  batch: BatchSummary;
  saving: boolean;
  onSave: (update: DiscographyMetadataUpdate) => Promise<void>;
  onConfirm: () => Promise<void>;
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
  const title = sanitizePathPart(album.album);
  if ((releaseType === "single" || releaseType === "ep") && album.year) {
    return `Music/Discographies/${sanitizePathPart(artist)}/${RELEASE_BUCKETS[releaseType]}/${album.year}/${title}`;
  }
  const folder = album.year ? `${album.year} - ${title}` : title;
  return `Music/Discographies/${sanitizePathPart(artist)}/${RELEASE_BUCKETS[releaseType]}/${folder}`;
}

export default function DiscographyEditor({
  batch,
  saving,
  onSave,
  onConfirm,
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
  const trackCount = useMemo(
    () => batch.albums.reduce((total, album) => total + album.track_count, 0),
    [batch.albums],
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

        <div className="discography-editor__body">
          <ReviewIssuesPanel
            batch={batch}
            saving={saving}
            confirmLabel="Confirm release list"
            onConfirm={onConfirm}
          />
          <div className="discography-editor__collection">
            <label>
              <span>Artist</span>
              <input value={artist} autoFocus onChange={(event) => setArtist(event.target.value)} />
            </label>
            <div className="metadata-editor__preview">
              <span>Destination preview</span>
              <code>{collectionDestination}</code>
            </div>
          </div>

          <div className="discography-editor__release-summary">
            <strong>Releases</strong>
            <span>{albums.length} releases · {trackCount} tracks</span>
          </div>

          <div className="discography-editor__releases">
            <div className="album-edit-row album-edit-header" aria-hidden="true">
              <span>Include</span>
              <span>Year</span>
              <span>Album title</span>
              <span>Release type</span>
              <span>Destination preview</span>
              <span>Warnings</span>
            </div>
            {albums.map((album) => {
              const source = albumsBySource.get(album.source_folder);
              const destination = albumDestination(artist, album);
              return (
                <div className="album-edit-row" key={album.source_folder}>
                  <div className="album-edit-row__include">
                      <input
                        aria-label={`Include ${album.album}`}
                        type="checkbox"
                        checked={album.include && album.release_type !== "exclude"}
                        onChange={(event) => updateAlbum(album.source_folder, {
                          include: event.target.checked,
                          release_type: event.target.checked && album.release_type === "exclude"
                            ? "album"
                            : album.release_type,
                        })}
                      />
                  </div>
                  <div>
                      <input
                        className="discography-editor__year"
                        aria-label={`Year for ${album.album}`}
                        value={album.year ?? ""}
                        placeholder="YYYY"
                        onChange={(event) => updateAlbum(album.source_folder, {
                          year: event.target.value || null,
                        })}
                      />
                  </div>
                  <div className="album-edit-row__title">
                      <input
                        aria-label={`Title for ${album.source_folder}`}
                        value={album.album}
                        onChange={(event) => updateAlbum(album.source_folder, {
                          album: event.target.value,
                        })}
                      />
                  </div>
                  <div>
                      <select
                        aria-label={`Release type for ${album.album}`}
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
                  </div>
                  <code className="album-edit-row__destination" title={destination}>
                    {destination}
                  </code>
                  <div className="album-edit-row__warnings">
                    <small>{source?.track_count ?? 0} track(s)</small>
                    {source?.warnings?.length
                      ? source.warnings.map((warning) => <span key={warning}>{warning.replace(/_/g, " ")}</span>)
                      : <small>No warnings</small>}
                  </div>
                </div>
              );
            })}
          </div>
        </div>

        <div className="metadata-editor__actions discography-editor__footer">
          <span className="discography-editor__resize-hint">
            Drag the bottom-right corner to resize
          </span>
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
