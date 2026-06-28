import { useMemo, useState } from "react";
import type {
  BatchSummary,
  DiscographyAlbumUpdate,
  DiscographyMetadataUpdate,
  DiscographyReleaseType,
} from "../types/archive";
import ReviewIssuesPanel from "./ReviewIssuesPanel";
import MetadataAssistStaleWarning from "./MetadataAssistStaleWarning";
import MetadataSuggestionChips from "./MetadataSuggestionChips";

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

const GENRE_CHIPS = [
  "Hip-Hop",
  "R&B",
  "Alternative R&B",
  "Alternative",
  "Indie Rock",
  "Pop",
  "Soul",
  "Jazz",
  "Electronic",
  "Rock",
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
      genre: album.genre ?? null,
      release_type: releaseType,
      include: album.include !== false && releaseType !== "exclude",
      accepted_unknown_album_artist: album.accepted_unknown_album_artist ?? false,
      accepted_unknown_album_title: album.accepted_unknown_album_title ?? false,
      accepted_unknown_year: album.accepted_unknown_year ?? false,
      lookup_later: album.lookup_later ?? false,
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
  const [primaryGenre, setPrimaryGenre] = useState(
    () => batch.primary_genre ?? batch.suggested_metadata?.genre ?? "",
  );
  const [acceptedUnknownArtist, setAcceptedUnknownArtist] = useState(
    Boolean(batch.accepted_unknown_discography_artist),
  );
  const [lookupLater, setLookupLater] = useState(Boolean(batch.lookup_later));
  const [filter, setFilter] = useState<"repair" | "included" | "excluded" | "all">("repair");
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
  const visibleAlbums = albums.filter((album) => {
    if (filter === "included") return album.include;
    if (filter === "excluded") return !album.include;
    if (filter === "repair") {
      return album.include && (!album.album.trim() || !album.year || album.lookup_later);
    }
    return true;
  });
  const valid = (artist.trim().length > 0 || acceptedUnknownArtist)
    && albums.every((album) => (
      (!album.include || album.album.trim().length > 0 || album.accepted_unknown_album_title)
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
        className="discography-editor"
        onMouseDown={(event) => event.stopPropagation()}
        onSubmit={(event) => {
          event.preventDefault();
          if (valid) void onSave({
            artist: artist.trim() || "Unknown Artist",
            primary_genre: primaryGenre.trim() || null,
            albums,
            accepted_unknown_discography_artist: acceptedUnknownArtist,
            lookup_later: lookupLater,
          });
        }}
      >
        <div className="discography-editor__header">
          <div className="discography-editor__header-title">
            <span className="discography-editor__header-eyebrow">Music · Discography</span>
            <h2>Correct discography</h2>
            <p>Edit collection metadata, release genres, and the move plan without changing audio tags.</p>
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
          <MetadataAssistStaleWarning batch={batch} />
          <div className="discography-editor__collection discography-editor__card">
            <label>
              <span>Discography artist</span>
              <input value={artist} autoFocus onChange={(event) => setArtist(event.target.value)} />
              <MetadataSuggestionChips
                label="Discography artist"
                field="album_artist"
                candidates={batch.metadata_candidates?.album_artist ?? []}
                currentValue={artist}
                onApply={setArtist}
              />
            </label>
            <label>
              <span>Default genre</span>
              <input
                value={primaryGenre}
                placeholder="Used for manifests and downstream apps"
                onChange={(event) => setPrimaryGenre(event.target.value)}
              />
              <small className="discography-editor__genre-help">
                Used for manifests and downstream apps. Audio tags are not changed.
              </small>
              <div className="discography-editor__genre-chips">
                {GENRE_CHIPS.map((genre) => (
                  <button type="button" className="btn-sm" key={genre} onClick={() => setPrimaryGenre(genre)}>
                    {genre}
                  </button>
                ))}
              </div>
            </label>
            <div className="metadata-editor__preview discography-editor__destination-preview">
              <span>Destination preview</span>
              <code>{collectionDestination}</code>
            </div>
          </div>

          <section className="acceptance-controls discography-editor__decisions">
            <div>
              <strong>Discography decisions</strong>
              <p>Accepted unknowns and lookup-later choices remain in the move manifest.</p>
            </div>
            <div className="acceptance-controls__buttons">
              <button type="button" className={`btn-sm${acceptedUnknownArtist ? " btn-sm--active" : ""}`} onClick={() => setAcceptedUnknownArtist((value) => !value)}>
                {acceptedUnknownArtist ? "Unknown Artist Accepted" : "Accept Unknown Discography Artist"}
              </button>
              <button type="button" className={`btn-sm${lookupLater ? " btn-sm--active" : ""}`} onClick={() => setLookupLater((value) => !value)}>
                {lookupLater ? "Lookup Later Marked" : "Lookup Later"}
              </button>
            </div>
          </section>

          <div className="discography-editor__release-summary">
            <span className="discography-editor__release-label">Releases</span>
            <span className="discography-editor__release-count">{albums.length} releases · {trackCount} tracks</span>
          </div>

          <div className="discography-editor__controls">
            <div className="discography-editor__filter-tabs">
              {(["repair", "included", "excluded", "all"] as const).map((value) => (
                <button type="button" className={`btn-sm${filter === value ? " btn-sm--active" : ""}`} key={value} onClick={() => setFilter(value)}>
                  {value === "repair" ? "Needs repair" : value[0].toUpperCase() + value.slice(1)}
                </button>
              ))}
            </div>
            <div className="discography-editor__bulk-actions">
              <button type="button" className="btn-sm" onClick={() => {
                const visible = new Set(visibleAlbums.map((album) => album.source_folder));
                setAlbums((current) => current.map((album) => visible.has(album.source_folder)
                  ? { ...album, accepted_unknown_album_artist: true }
                  : album));
              }}>Accept unknown artists for visible</button>
              <button type="button" className="btn-sm" onClick={() => {
                const visible = new Set(visibleAlbums.map((album) => album.source_folder));
                setAlbums((current) => current.map((album) => visible.has(album.source_folder)
                  ? { ...album, lookup_later: true }
                  : album));
              }}>Mark visible lookup later</button>
              <button type="button" className="btn-sm" onClick={() => {
                const visible = new Set(visibleAlbums.map((album) => album.source_folder));
                setAlbums((current) => current.map((album) => visible.has(album.source_folder)
                  ? { ...album, include: false, release_type: "exclude" }
                  : album));
              }}>Exclude visible</button>
              <button type="button" className="btn-sm" disabled={!primaryGenre.trim()} onClick={() => {
                const visible = new Set(visibleAlbums.map((album) => album.source_folder));
                const genre = primaryGenre.trim();
                setAlbums((current) => current.map((album) => visible.has(album.source_folder)
                  ? { ...album, genre }
                  : album));
              }}>Apply default genre to visible</button>
              <button type="button" className="btn-sm" onClick={() => {
                const visible = new Set(visibleAlbums.map((album) => album.source_folder));
                setAlbums((current) => current.map((album) => visible.has(album.source_folder)
                  ? { ...album, genre: null }
                  : album));
              }}>Clear visible genre overrides</button>
            </div>
          </div>

          <div className="discography-editor__releases">
            <div className="album-edit-row album-edit-header" aria-hidden="true">
              <span>Include</span>
              <span>Year</span>
              <span>Album title</span>
              <span>Release type</span>
              <span>Genre</span>
              <span>Destination preview</span>
              <span>Warnings</span>
            </div>
            {visibleAlbums.map((album) => {
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
                    <MetadataSuggestionChips
                      label={`Year for ${album.album}`}
                      field="year"
                      candidates={source?.metadata_candidates?.year ?? []}
                      currentValue={album.year ?? ""}
                      onApply={(value) => updateAlbum(album.source_folder, { year: value })}
                      maxVisible={1}
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
                    <MetadataSuggestionChips
                      label={`Title for ${album.source_folder}`}
                      field="album_title"
                      candidates={source?.metadata_candidates?.album_title ?? []}
                      currentValue={album.album}
                      onApply={(value) => updateAlbum(album.source_folder, { album: value })}
                      maxVisible={1}
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
                  <div className="album-edit-row__genre">
                    <input
                      aria-label={`Genre for ${album.album}`}
                      value={album.genre ?? ""}
                      placeholder={primaryGenre.trim() ? `Inherit ${primaryGenre.trim()}` : source?.genre ? `Detected ${source.genre}` : "Genre"}
                      onChange={(event) => updateAlbum(album.source_folder, {
                        genre: event.target.value || null,
                      })}
                    />
                    <small className={album.genre?.trim() ? "album-genre-pill album-genre-pill--override" : primaryGenre.trim() ? "album-genre-pill album-genre-pill--inherited" : "album-genre-pill album-genre-pill--empty"}>
                      {album.genre?.trim()
                        ? `Genre: ${album.genre.trim()}`
                        : primaryGenre.trim()
                          ? `Inherits: ${primaryGenre.trim()}`
                          : source?.genre_source
                            ? `Source: ${source.genre_source}`
                            : "No genre set"}
                    </small>
                  </div>
                  <code className="album-edit-row__destination" title={destination}>
                    {destination}
                  </code>
                  <div className="album-edit-row__warnings">
                    <small>
                      {source?.track_count ?? 0} track(s) · {source?.disc_count ?? 1} disc(s) · {source?.format ?? "Unknown"}
                    </small>
                    <small>Artwork: {source?.artwork_count ?? 0}</small>
                    {source?.warnings?.length
                      ? source.warnings.map((warning) => <span key={warning}>{warning.replace(/_/g, " ")}</span>)
                      : <small>No warnings</small>}
                    <div className="album-edit-row__decisions">
                      <button type="button" className={`btn-sm${album.accepted_unknown_album_title ? " btn-sm--active" : ""}`} onClick={() => updateAlbum(album.source_folder, { accepted_unknown_album_title: !album.accepted_unknown_album_title })}>
                        Unknown title
                      </button>
                      <button type="button" className={`btn-sm${album.accepted_unknown_year ? " btn-sm--active" : ""}`} onClick={() => updateAlbum(album.source_folder, { accepted_unknown_year: !album.accepted_unknown_year })}>
                        Unknown year
                      </button>
                      <button type="button" className={`btn-sm${album.lookup_later ? " btn-sm--active" : ""}`} onClick={() => updateAlbum(album.source_folder, { lookup_later: !album.lookup_later })}>
                        Lookup later
                      </button>
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
        </div>

        <div className="discography-editor__footer">
          <span className="discography-editor__resize-hint">
            <i className="ti ti-arrows-diagonal" />
            Drag corner to resize
          </span>
          <div className="discography-editor__footer-actions">
            <button type="button" className="btn" disabled={saving} onClick={onClose}>Cancel</button>
            <button type="submit" className="btn btn--green" disabled={saving || !valid}>
              <i className={`ti ti-${saving ? "loader-2 spinner" : "device-floppy"}`} />
              Save discography corrections
            </button>
          </div>
        </div>
      </form>
    </div>
  );
}
