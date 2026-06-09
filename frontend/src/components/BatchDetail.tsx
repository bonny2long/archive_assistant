import { useState } from "react";
import type { BatchMoveSummary, BatchReview, IngestBatch } from "../types/archive";
import { formatArchiveTime } from "../utils/archiveTime";
import { getBatchDisplayTitle, getReleaseCount } from "../utils/batchDisplay";

type Props = {
  batch: IngestBatch;
  moveSummary?: BatchMoveSummary;
  review?: BatchReview;
};

function metadataValue(batch: IngestBatch, key: string): string {
  const value = batch.metadata_json?.[key];
  return value === null || value === undefined || value === "" ? "-" : String(value);
}

function readableLibraryPath(value?: string | null): string {
  if (!value) return "-";
  const normalized = value.replace(/\\/g, "/");
  const lower = normalized.toLowerCase();
  for (const marker of [
    "tv/library/",
    "movies/library/",
    "music/discographies/",
    "music/library/",
  ]) {
    const index = lower.indexOf(marker);
    if (index >= 0) return normalized.slice(index);
  }
  return normalized;
}

function readableSourcePath(value: string): string {
  const normalized = value.replace(/\\/g, "/");
  const dataMarker = "/data/";
  const dataIndex = normalized.toLowerCase().indexOf(dataMarker);
  return dataIndex >= 0
    ? normalized.slice(dataIndex + dataMarker.length)
    : normalized.split("/").slice(-2).join("/");
}

function formatBytes(value: unknown): string {
  const bytes = Number(value ?? 0);
  if (!Number.isFinite(bytes) || bytes <= 0) return "0 B";
  const units = ["B", "KB", "MB", "GB", "TB"];
  const unit = Math.min(
    Math.floor(Math.log(bytes) / Math.log(1024)),
    units.length - 1,
  );
  return `${(bytes / (1024 ** unit)).toFixed(unit === 0 ? 0 : 1)} ${units[unit]}`;
}

const WARNING_LABELS: Record<string, string> = {
  artist_missing: "Artist missing",
  album_missing: "Album missing",
  year_missing: "Year missing",
  year_invalid: "Year invalid",
  genre_missing: "Genre missing",
  raw_folder_name_detected: "Raw folder name detected",
  partial_duplicate_tracks_detected: "Partial duplicate tracks detected",
  compilation_suspected: "Compilation suspected",
  compilation_detected: "Compilation detected",
  compilation_prefix_removed: "Compilation prefix removed",
  mixed_embedded_metadata_detected: "Mixed embedded metadata detected",
  track_album_mismatch_detected: "Some track album tags differ from the release folder",
  track_artist_mismatch_detected: "Some track artist tags differ from the release folder",
  release_folder_grouping_used: "Release folder grouping used",
  possible_duplicate_destination: "Possible duplicate destination",
  possible_artist_alias: "Possible artist alias",
  manual_duplicate_batch_merge_performed: "Manual duplicate batch merge performed",
  possible_artist_alias_resolved: "Artist alias resolved",
  possible_archived_duplicate_candidate: "Matching release already archived",
  destination_file_conflict: "Destination filename conflict",
  album_tag_mismatch: "Album tag mismatch",
  artist_tag_mismatch: "Artist tag mismatch",
  discography_grouping_used: "Discography grouping used",
  child_album_metadata_missing: "Child album metadata needs review",
  album_missing_year: "Album missing year",
  album_missing_title: "Album missing title",
  mixed_formats: "Mixed formats",
  discography_destination_exists: "Discography folder already exists",
  one_track_release: "One-track release",
  possible_single_or_ep: "Possible single/EP",
  suspicious_year: "Suspicious year",
  folder_artist_mismatch: "Folder artist mismatch",
  album_title_from_folder_cleanup: "Album title cleaned",
  release_tag_removed: "Release tag removed",
  movie_year_missing: "Movie year missing",
  movie_destination_exists: "Movie destination already exists",
  tv_show_title_from_folder: "TV show title taken from folder",
  tv_show_title_missing: "TV show title missing",
  tv_episode_parse_failed: "Some TV episodes could not be parsed",
  tv_destination_exists: "TV show destination already exists",
};

function metadataWarnings(batch: IngestBatch): string[] {
  const warnings = batch.metadata_json?.metadata_warnings;
  return Array.isArray(warnings)
    ? warnings.filter((warning): warning is string => typeof warning === "string")
    : [];
}

function metadataAlertMessages(batch: IngestBatch): string[] {
  const alerts = batch.metadata_json?.metadata_alerts;
  if (!Array.isArray(alerts)) return [];
  return alerts
    .map((alert) => {
      if (
        alert
        && typeof alert === "object"
        && "message" in alert
        && typeof alert.message === "string"
      ) {
        return alert.message;
      }
      return null;
    })
    .filter((message): message is string => Boolean(message));
}

function warningLabel(warning: string): string {
  return WARNING_LABELS[warning]
    ?? warning.replace(/_/g, " ").replace(/^\w/, (value: string) => value.toUpperCase());
}

function DebugDetails({ batch, moveSummary, review }: Props) {
  const [showJson, setShowJson] = useState(false);
  const [copyLabel, setCopyLabel] = useState("Copy debug JSON");

  const copyDebugJson = async () => {
    try {
      await navigator.clipboard.writeText(JSON.stringify(batch, null, 2));
      setCopyLabel("Debug JSON copied");
      window.setTimeout(() => setCopyLabel("Copy debug JSON"), 1800);
    } catch {
      setShowJson(true);
      setCopyLabel("Copy failed. JSON opened instead.");
      window.setTimeout(() => setCopyLabel("Copy debug JSON"), 2600);
    }
  };

  return (
    <div className="batch-debug">
      <div className="batch-debug__actions">
        <button className="btn btn--compact" onClick={() => setShowJson((value) => !value)}>
          <i className={`ti ti-${showJson ? "eye-off" : "code"}`} />
          {showJson ? "Hide debug JSON" : "Show debug JSON"}
        </button>
        <button className="btn btn--compact" onClick={() => void copyDebugJson()}>
          <i className="ti ti-copy" />
          {copyLabel}
        </button>
      </div>
      {showJson && (
        <div className="batch-debug__content">
          <div>
            <div className="batch-detail__label">Source path</div>
            <div className="batch-detail__value batch-detail__path">{batch.source_path}</div>
          </div>
          <pre className="batch-detail__debug">
            {JSON.stringify({ batch, review, move_summary: moveSummary }, null, 2)}
          </pre>
        </div>
      )}
    </div>
  );
}

function QuarantineReviewDetail({ batch, moveSummary }: Props) {
  return (
    <div className="batch-detail">
      <div className="batch-detail__grid batch-detail__grid--stacked">
        <div><div className="batch-detail__label">Name</div><div className="batch-detail__value">{metadataValue(batch, "name")}</div></div>
        <div><div className="batch-detail__label">Detected type</div><div className="batch-detail__value">{batch.detected_type}</div></div>
        <div><div className="batch-detail__label">Reason</div><div className="batch-detail__value">{metadataValue(batch, "reason")}</div></div>
        <div><div className="batch-detail__label">File count</div><div className="batch-detail__value">{metadataValue(batch, "file_count")}</div></div>
        <div><div className="batch-detail__label">Folder count</div><div className="batch-detail__value">{metadataValue(batch, "folder_count")}</div></div>
        <div><div className="batch-detail__label">Size</div><div className="batch-detail__value">{formatBytes(batch.metadata_json?.size_bytes)}</div></div>
        <div><div className="batch-detail__label">Recommended action</div><div className="batch-detail__value">{metadataValue(batch, "recommended_action")}</div></div>
        {Boolean(batch.metadata_json?.music_parent) && (
          <div><div className="batch-detail__label">Music collection</div><div className="batch-detail__value batch-detail__path">{metadataValue(batch, "music_parent")}</div></div>
        )}
        {Boolean(batch.metadata_json?.relative_path) && (
          <div><div className="batch-detail__label">Location inside collection</div><div className="batch-detail__value batch-detail__path">{metadataValue(batch, "relative_path")}</div></div>
        )}
        <div>
          <div className="batch-detail__label">Source path</div>
          <div className="batch-detail__value batch-detail__path">
            {readableSourcePath(batch.source_path)}
          </div>
        </div>
      </div>
      <DebugDetails batch={batch} moveSummary={moveSummary} />
    </div>
  );
}

function MovieBatchDetail({ batch, moveSummary }: Props) {
  const warnings = metadataWarnings(batch);
  const alerts = metadataAlertMessages(batch);
  const moved = batch.status === "moved";
  return (
    <div className={`batch-detail ${moved ? "batch-detail--moved" : "batch-detail--review"}`}>
      <div className="library-status">
        <div className="library-status__icon"><i className="ti ti-movie" /></div>
        <div>
          <div className="library-status__eyebrow">Movie detected</div>
          <h2>{getBatchDisplayTitle(batch)}</h2>
          <p>{metadataValue(batch, "format")} · {metadataValue(batch, "video_file_count")} video file(s)</p>
        </div>
        <div className="library-status__facts">
          <span>{Math.round(batch.confidence * 100)}% confidence</span>
          <span>{batch.status.replace(/_/g, " ")}</span>
        </div>
      </div>

      <div className="library-detail__grid movie-detail__cards">
        <section className="library-card">
          <h3>Movie</h3>
          <dl className="library-fields">
            <div><dt>Title</dt><dd>{metadataValue(batch, "title")}</dd></div>
            <div><dt>Year</dt><dd>{metadataValue(batch, "year")}</dd></div>
            {Boolean(batch.metadata_json?.edition) && (
              <div><dt>Edition / Version</dt><dd>{metadataValue(batch, "edition")}</dd></div>
            )}
            <div><dt>Format</dt><dd>{metadataValue(batch, "format")}</dd></div>
            <div><dt>Video files</dt><dd>{metadataValue(batch, "video_file_count")}</dd></div>
            <div><dt>Artwork</dt><dd>{metadataValue(batch, "artwork_count")}</dd></div>
            <div><dt>Subtitles</dt><dd>{metadataValue(batch, "subtitle_count")}</dd></div>
            <div><dt>Ignored sidecars</dt><dd>{metadataValue(batch, "ignored_sidecar_count")}</dd></div>
            {Array.isArray(batch.metadata_json?.release_tags_removed)
              && batch.metadata_json.release_tags_removed.length > 0 && (
              <div>
                <dt>Release tags removed</dt>
                <dd>{batch.metadata_json.release_tags_removed.join(", ")}</dd>
              </div>
            )}
          </dl>
        </section>
        <section className="library-card">
          <h3>Source</h3>
          <dl className="library-fields library-fields--single">
            <div>
              <dt>Path</dt>
              <dd className="library-fields__path">{readableSourcePath(batch.source_path)}</dd>
            </div>
            <div><dt>Status</dt><dd>{batch.status.replace(/_/g, " ")}</dd></div>
          </dl>
        </section>
      </div>

      <section className="library-destination">
        <span>{moved ? "Final destination" : "Destination preview"}</span>
        <strong>{readableLibraryPath(batch.suggested_destination)}</strong>
      </section>

      {warnings.length > 0 && (
        <section className="metadata-warnings">
          <div className="metadata-warnings__list">
            {warnings.map((warning) => (
              <span key={warning}><i className="ti ti-alert-triangle" />{warningLabel(warning)}</span>
            ))}
          </div>
        </section>
      )}
      {alerts.length > 0 && (
        <section className="metadata-alerts" aria-label="Movie metadata alerts">
          {alerts.map((message) => (
            <div key={message}><i className="ti ti-info-circle" />{message}</div>
          ))}
        </section>
      )}

      {moved && moveSummary && (
        <div className="move-log__empty">
          {moveSummary.completed} files completed, {moveSummary.failed} failed.
        </div>
      )}
      <DebugDetails batch={batch} moveSummary={moveSummary} />
    </div>
  );
}

type TvEpisodeDetail = {
  season_number?: number | null;
  episode_number?: number | null;
  episode_code?: string | null;
  episode_title?: string | null;
  source_file?: string;
};

type TvSeasonDetail = {
  season_number?: number;
  episode_count?: number;
  episodes?: TvEpisodeDetail[];
};

function TvBatchDetail({ batch, moveSummary }: Props) {
  const metadata = batch.metadata_json ?? {};
  const seasons = Array.isArray(metadata.seasons)
    ? metadata.seasons.filter(
      (season): season is TvSeasonDetail => Boolean(season) && typeof season === "object",
    )
    : [];
  const episodes = seasons.flatMap((season) => season.episodes ?? []);
  const warnings = metadataWarnings(batch);
  const alerts = metadataAlertMessages(batch);
  const moved = batch.status === "moved";

  return (
    <div className={`batch-detail ${moved ? "batch-detail--moved" : "batch-detail--review"}`}>
      <div className="library-status">
        <div className="library-status__icon"><i className="ti ti-device-tv" /></div>
        <div>
          <div className="library-status__eyebrow">TV show detected</div>
          <h2>{metadataValue(batch, "show_title")}</h2>
          <p>
            {metadataValue(batch, "season_count")} season(s) ·{" "}
            {metadataValue(batch, "episode_count")} episode(s)
          </p>
        </div>
        <div className="library-status__facts">
          <span>{Math.round(batch.confidence * 100)}% confidence</span>
          <span>{batch.status.replace(/_/g, " ")}</span>
        </div>
      </div>

      <div className="library-detail__grid movie-detail__cards">
        <section className="library-card">
          <h3>TV Show</h3>
          <dl className="library-fields">
            <div><dt>Show</dt><dd>{metadataValue(batch, "show_title")}</dd></div>
            <div><dt>Seasons</dt><dd>{metadataValue(batch, "season_count")}</dd></div>
            <div><dt>Episodes</dt><dd>{metadataValue(batch, "episode_count")}</dd></div>
            <div><dt>Video files</dt><dd>{metadataValue(batch, "video_file_count")}</dd></div>
            <div><dt>Subtitles</dt><dd>{metadataValue(batch, "subtitle_count")}</dd></div>
            <div><dt>Artwork</dt><dd>{metadataValue(batch, "artwork_count")}</dd></div>
            <div><dt>Ignored sidecars</dt><dd>{metadataValue(batch, "ignored_sidecar_count")}</dd></div>
          </dl>
        </section>
        <section className="library-card">
          <h3>Source</h3>
          <dl className="library-fields library-fields--single">
            <div>
              <dt>Path</dt>
              <dd className="library-fields__path">{readableSourcePath(batch.source_path)}</dd>
            </div>
            <div><dt>Status</dt><dd>{batch.status.replace(/_/g, " ")}</dd></div>
          </dl>
        </section>
      </div>

      <section className="library-destination">
        <span>{moved ? "Final destination" : "Destination preview"}</span>
        <strong>{readableLibraryPath(batch.suggested_destination)}</strong>
      </section>

      {warnings.length > 0 && (
        <section className="metadata-warnings">
          <div className="metadata-warnings__list">
            {warnings.map((warning) => (
              <span key={warning}><i className="ti ti-alert-triangle" />{warningLabel(warning)}</span>
            ))}
          </div>
        </section>
      )}
      {alerts.length > 0 && (
        <section className="metadata-alerts" aria-label="TV metadata alerts">
          {alerts.map((message) => (
            <div key={message}><i className="ti ti-info-circle" />{message}</div>
          ))}
        </section>
      )}

      {episodes.length > 0 && (
        <section className="track-preview">
          <div className="track-preview__header">
            <h3>Episode preview</h3>
            <span>{episodes.length} episode(s)</span>
          </div>
          <div className="track-preview__table">
            <table>
              <thead>
                <tr>
                  <th>Season</th>
                  <th>Episode</th>
                  <th>Source file</th>
                  <th>Destination preview</th>
                </tr>
              </thead>
              <tbody>
                {episodes.map((episode, index) => {
                  const seasonNumber = Number(episode.season_number ?? 0);
                  const season = seasonNumber
                    ? String(seasonNumber).padStart(2, "0")
                    : "-";
                  const code = episode.episode_code ?? "-";
                  const source = episode.source_file ?? "Unknown file";
                  const preview = seasonNumber && episode.episode_code
                    ? `Season ${season}/${episode.episode_code} - ${source}`
                    : "Metadata review required";
                  return (
                    <tr key={`${code}-${source}-${index}`}>
                      <td>{season}</td>
                      <td>{code}</td>
                      <td>{source}</td>
                      <td>{preview}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </section>
      )}

      {moved && moveSummary && (
        <div className="move-log__empty">
          {moveSummary.completed} files completed, {moveSummary.failed} failed.
        </div>
      )}
      <DebugDetails batch={batch} moveSummary={moveSummary} />
    </div>
  );
}

function ReviewBatchDetail({ batch, moveSummary, review }: Props) {
  const warnings = review?.warnings ?? metadataWarnings(batch);
  const alerts = metadataAlertMessages(batch);
  const destination = review?.destination_preview ?? batch.suggested_destination;

  return (
    <div className="batch-detail batch-detail--review">
      <div className="library-status">
        <div className="library-status__icon"><i className="ti ti-clipboard-check" /></div>
        <div>
          <div className="library-status__eyebrow">Library status</div>
          <h2>Ready for review</h2>
          <p>{review?.artist ?? metadataValue(batch, "artist")} · {review?.album ?? metadataValue(batch, "album")}</p>
        </div>
        <div className="library-status__facts">
          <span>{Math.round(batch.confidence * 100)}% confidence</span>
          <span>{batch.metadata_confirmed ? "Metadata confirmed" : "Review before approval"}</span>
        </div>
      </div>

      <div className="library-detail__grid">
        <section className="library-card">
          <h3>Album</h3>
          <dl className="library-fields">
            <div><dt>Artist</dt><dd>{review?.artist ?? metadataValue(batch, "artist")}</dd></div>
            <div><dt>Album</dt><dd>{review?.album ?? metadataValue(batch, "album")}</dd></div>
            <div><dt>Year</dt><dd>{review?.year ?? metadataValue(batch, "year")}</dd></div>
            <div><dt>Genre</dt><dd>{review?.genre ?? metadataValue(batch, "genre")}</dd></div>
            <div><dt>Format</dt><dd>{review?.format ?? metadataValue(batch, "format")}</dd></div>
            <div><dt>Tracks</dt><dd>{review?.track_count ?? batch.files.length}</dd></div>
            <div><dt>Artwork</dt><dd>{metadataValue(batch, "artwork_count")}</dd></div>
          </dl>
        </section>
        <section className="library-card">
          <h3>Source</h3>
          <dl className="library-fields library-fields--single">
            <div><dt>Folder</dt><dd>{review?.source_path ?? batch.source_path}</dd></div>
            <div><dt>Discs</dt><dd>{review?.disc_count ?? metadataValue(batch, "disc_count")}</dd></div>
            <div><dt>Status</dt><dd>{review?.status ?? batch.status}</dd></div>
          </dl>
        </section>
      </div>

      {warnings.length > 0 && (
        <section className="metadata-warnings" aria-label="Metadata warnings">
          <div className="batch-detail__label">Warnings</div>
          <div className="metadata-warnings__list">
            {warnings.map((warning) => (
              <span key={warning}><i className="ti ti-alert-triangle" />{warningLabel(warning)}</span>
            ))}
          </div>
        </section>
      )}
      {alerts.length > 0 && (
        <section className="metadata-alerts" aria-label="Metadata alerts">
          {alerts.map((message) => (
            <div key={message}><i className="ti ti-info-circle" />{message}</div>
          ))}
        </section>
      )}

      <section className="library-destination">
        <span>Destination preview</span>
        <strong>{readableLibraryPath(destination)}</strong>
      </section>

      {review?.tracks.length ? (
        <section className="track-preview">
          <div className="track-preview__header">
            <h3>Track preview</h3>
            <span>{review.tracks.length} track(s)</span>
          </div>
          <div className="track-preview__table">
            <table>
              <thead>
                <tr>
                  <th>#</th>
                  <th>Disc</th>
                  <th>Track</th>
                  <th>Title / source</th>
                  <th>Destination filename</th>
                  <th>Warn</th>
                </tr>
              </thead>
              <tbody>
                {review.tracks.map((track) => (
                  <tr key={`${track.position}-${track.source_filename}`}>
                    <td>{track.position}</td>
                    <td>{track.disc}</td>
                    <td>{track.track ?? "-"}</td>
                    <td>
                      <strong>{track.title}</strong>
                      <small>{track.source_filename}</small>
                    </td>
                    <td>{track.destination_filename}</td>
                    <td>
                      {track.warnings.length ? (
                        <span className="track-preview__warning" title={track.warnings.map(warningLabel).join(", ")}>
                          <i className="ti ti-alert-triangle" />
                        </span>
                      ) : "-"}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      ) : null}

      <DebugDetails batch={batch} moveSummary={moveSummary} review={review} />
    </div>
  );
}

type DiscographyAlbum = {
  year?: string | null;
  album?: string | null;
  track_count?: number;
  format?: string;
  status?: string;
  warnings?: string[];
};

type DiscographyParentCleanup = {
  removed_tokens?: string[];
  year_range?: string | null;
  format_hint?: string | null;
};

function DiscographyBatchDetail({ batch, moveSummary }: Props) {
  const metadata = batch.metadata_json ?? {};
  const albums = Array.isArray(metadata.albums)
    ? metadata.albums.filter(
      (album): album is DiscographyAlbum => Boolean(album) && typeof album === "object",
    )
    : [];
  const cleanup = metadata.parent_cleanup && typeof metadata.parent_cleanup === "object"
    ? metadata.parent_cleanup as DiscographyParentCleanup
    : null;
  const removedTokens = cleanup?.removed_tokens?.filter(Boolean) ?? [];
  const artistSource = typeof metadata.artist_source === "string"
    ? metadata.artist_source
    : "";
  const warnings = metadataWarnings(batch);
  const moved = batch.status === "moved";
  const releaseCount = getReleaseCount(batch);

  return (
    <div className={`batch-detail ${moved ? "batch-detail--moved" : "batch-detail--review"}`}>
      <div className="library-status">
        <div className="library-status__icon"><i className="ti ti-folders" /></div>
        <div>
          <div className="library-status__eyebrow">Discography detected</div>
          <h2>{getBatchDisplayTitle(batch)}</h2>
          <p>{releaseCount} releases · {String(metadata.track_count ?? batch.files.length)} tracks</p>
        </div>
        <div className="library-status__facts">
          <span>{Array.isArray(metadata.format_summary) ? metadata.format_summary.join(", ") : "-"}</span>
          <span>{batch.status.replace(/_/g, " ")}</span>
        </div>
      </div>

      <section className="library-destination">
        <span>{moved ? "Final destination" : "Destination preview"}</span>
        <strong>{readableLibraryPath(batch.suggested_destination)}</strong>
      </section>

      {(removedTokens.length > 0 || Boolean(cleanup?.year_range) || Boolean(artistSource)) && (
        <section className="library-card discography-cleanup">
          <h3>Source folder cleanup</h3>
          <dl className="library-fields library-fields--single">
            {removedTokens.length > 0 && (
              <div><dt>Removed</dt><dd>{removedTokens.join(", ")}</dd></div>
            )}
            {cleanup?.year_range && (
              <div><dt>Year range</dt><dd>{cleanup.year_range}</dd></div>
            )}
            {cleanup?.format_hint && (
              <div><dt>Format hint</dt><dd>{cleanup.format_hint}</dd></div>
            )}
            {artistSource && (
              <div><dt>Artist selected from</dt><dd>{artistSource}</dd></div>
            )}
          </dl>
        </section>
      )}

      {warnings.length > 0 && (
        <section className="metadata-warnings">
          <div className="batch-detail__label">Warnings</div>
          <div className="metadata-warnings__list">
            {warnings.map((warning) => (
              <span key={warning}><i className="ti ti-alert-triangle" />{warningLabel(warning)}</span>
            ))}
          </div>
        </section>
      )}

      <section className="discography-albums">
        <div className="track-preview__header">
          <h3>Releases found</h3>
          <span>{releaseCount} releases</span>
        </div>
        <div className="track-preview__table">
          <table>
            <thead>
              <tr>
                <th>Year</th>
                <th>Album</th>
                <th>Tracks</th>
                <th>Format</th>
                <th>Status</th>
                <th>Warnings</th>
              </tr>
            </thead>
            <tbody>
              {albums.map((album, index) => (
                <tr key={`${album.year ?? "unknown"}-${album.album ?? index}`}>
                  <td>{album.year ?? "-"}</td>
                  <td>{album.album ?? "Unknown Album"}</td>
                  <td>{album.track_count ?? 0}</td>
                  <td>{album.format ?? "-"}</td>
                  <td>{(album.status ?? "ready").replace(/_/g, " ")}</td>
                  <td>
                    {album.warnings?.length ? (
                      <div className="metadata-warnings__list metadata-warnings__list--compact">
                        {album.warnings.map((warning) => (
                          <span key={warning}>{warningLabel(warning)}</span>
                        ))}
                      </div>
                    ) : "-"}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      {moved && moveSummary && (
        <div className="move-log__empty">
          {moveSummary.completed} tracks completed, {moveSummary.failed} failed.
        </div>
      )}
      <DebugDetails batch={batch} moveSummary={moveSummary} />
    </div>
  );
}

function MovedBatchDetail({ batch, moveSummary }: Props) {
  const completedDates = moveSummary?.moves
    .filter((move) => move.completed_at)
    .map((move) => move.completed_at as string)
    .sort() ?? [];
  const latestCompleted = completedDates[completedDates.length - 1];
  const warnings = moveSummary?.moves.filter(
    (move) => move.status !== "completed" || move.error_message,
  ) ?? [];
  const metadataWarningValues = metadataWarnings(batch);
  const metadataAlerts = metadataAlertMessages(batch);

  return (
    <div className="batch-detail batch-detail--moved">
      <div className="library-status">
        <div className="library-status__icon"><i className="ti ti-circle-check" /></div>
        <div>
          <div className="library-status__eyebrow">Library status</div>
          <h2>Moved successfully</h2>
          <p>{metadataValue(batch, "artist")} · {metadataValue(batch, "album")}</p>
        </div>
        <div className="library-status__facts">
          <span>{Math.round(batch.confidence * 100)}% confidence</span>
          <span>{batch.metadata_confirmed ? "Metadata confirmed" : "Detected metadata"}</span>
        </div>
      </div>

      <div className="library-detail__grid">
        <section className="library-card">
          <h3>Album</h3>
          <dl className="library-fields">
            <div><dt>Artist</dt><dd>{metadataValue(batch, "artist")}</dd></div>
            <div><dt>Album</dt><dd>{metadataValue(batch, "album")}</dd></div>
            <div><dt>Year</dt><dd>{metadataValue(batch, "year")}</dd></div>
            <div><dt>Genre</dt><dd>{metadataValue(batch, "genre")}</dd></div>
            <div><dt>Format</dt><dd>{metadataValue(batch, "format")}</dd></div>
            <div><dt>Tracks</dt><dd>{moveSummary?.total ?? batch.files.length}</dd></div>
          </dl>
        </section>

        <section className="library-card">
          <h3>Timeline</h3>
          <dl className="library-fields">
            <div><dt>Created</dt><dd>{formatArchiveTime(batch.created_at)}</dd></div>
            <div><dt>Approved</dt><dd>{formatArchiveTime(batch.approved_at)}</dd></div>
            <div><dt>Moved</dt><dd>{formatArchiveTime(latestCompleted)}</dd></div>
          </dl>
        </section>
      </div>

      <section className="library-destination">
        <span>Final destination</span>
        <strong>{readableLibraryPath(batch.suggested_destination)}</strong>
      </section>

      {metadataWarningValues.length > 0 && (
        <section className="metadata-warnings" aria-label="Metadata warnings">
          <div className="metadata-warnings__list">
            {metadataWarningValues.map((warning) => (
              <span key={warning}><i className="ti ti-alert-triangle" />{warningLabel(warning)}</span>
            ))}
          </div>
        </section>
      )}
      {metadataAlerts.length > 0 && (
        <section className="metadata-alerts" aria-label="Metadata alerts">
          {metadataAlerts.map((message) => (
            <div key={message}><i className="ti ti-info-circle" />{message}</div>
          ))}
        </section>
      )}

      <section className="move-log">
        <div className="move-log__header">
          <div>
            <h3>Move log</h3>
            <p>{moveSummary?.completed ?? 0} completed, {moveSummary?.failed ?? 0} failed</p>
          </div>
          <span className={`move-log__summary ${warnings.length ? "move-log__summary--warning" : ""}`}>
            {warnings.length ? `${warnings.length} warning(s)` : "All files completed"}
          </span>
        </div>
        {moveSummary?.moves.length ? (
          <div className="move-file-list">
            {moveSummary.moves.map((move) => (
              <div className="move-file" key={move.id}>
                <i className={`ti ti-${move.status === "completed" ? "check" : "alert-triangle"}`} />
                <span title={move.destination_path}>{move.file_name ?? "Unknown file"}</span>
                <span className={`move-file__status move-file__status--${move.status}`}>
                  {move.status}
                </span>
                {move.error_message && <small>{move.error_message}</small>}
              </div>
            ))}
          </div>
        ) : (
          <div className="move-log__empty">No move actions were recorded for this batch.</div>
        )}
      </section>

      <DebugDetails batch={batch} moveSummary={moveSummary} />
    </div>
  );
}

export default function BatchDetail({ batch, moveSummary, review }: Props) {
  if (batch.status === "needs_quarantine_review" || batch.status === "quarantined") {
    return <QuarantineReviewDetail batch={batch} moveSummary={moveSummary} />;
  }
  if (batch.detected_type === "music_discography") {
    return <DiscographyBatchDetail batch={batch} moveSummary={moveSummary} />;
  }
  if (batch.detected_type === "video_movie") {
    return <MovieBatchDetail batch={batch} moveSummary={moveSummary} />;
  }
  if (batch.detected_type === "video_tv_show") {
    return <TvBatchDetail batch={batch} moveSummary={moveSummary} />;
  }
  if (batch.status === "moved") {
    return <MovedBatchDetail batch={batch} moveSummary={moveSummary} />;
  }

  if (batch.status === "pending_review" || batch.status === "needs_metadata_review" || batch.status === "approved") {
    return <ReviewBatchDetail batch={batch} moveSummary={moveSummary} review={review} />;
  }

  const warnings = metadataWarnings(batch);
  const alerts = metadataAlertMessages(batch);

  return (
    <div className="batch-detail">
      <div className="batch-detail__grid batch-detail__grid--stacked">
        <div>
          <div className="batch-detail__label">Artist</div>
          <div className="batch-detail__value">{metadataValue(batch, "artist")}</div>
        </div>
        <div>
          <div className="batch-detail__label">Album</div>
          <div className="batch-detail__value">{metadataValue(batch, "album")}</div>
        </div>
        <div>
          <div className="batch-detail__label">Source path</div>
          <div className="batch-detail__value batch-detail__path">
            {readableSourcePath(batch.source_path)}
          </div>
        </div>
        <div>
          <div className="batch-detail__label">Suggested destination</div>
          <div className="batch-detail__value batch-detail__path">
            {batch.suggested_destination
              ? readableSourcePath(batch.suggested_destination)
              : "-"}
          </div>
        </div>
        <div>
          <div className="batch-detail__label">Detected type</div>
          <div className="batch-detail__value">{batch.detected_type}</div>
        </div>
        <div>
          <div className="batch-detail__label">Source kind</div>
          <div className="batch-detail__value">{batch.source_kind}</div>
        </div>
        <div>
          <div className="batch-detail__label">Created at</div>
          <div className="batch-detail__value">{formatArchiveTime(batch.created_at)}</div>
        </div>
        <div>
          <div className="batch-detail__label">Approved at</div>
          <div className="batch-detail__value">{formatArchiveTime(batch.approved_at)}</div>
        </div>
      </div>
      {warnings.length > 0 && (
        <section className="metadata-warnings" aria-label="Metadata warnings">
          <div className="batch-detail__label">Metadata warnings</div>
          <div className="metadata-warnings__list">
            {warnings.map((warning) => (
              <span key={warning}><i className="ti ti-alert-triangle" />{warningLabel(warning)}</span>
            ))}
          </div>
        </section>
      )}
      {alerts.length > 0 && (
        <section className="metadata-alerts" aria-label="Metadata alerts">
          {alerts.map((message) => (
            <div key={message}><i className="ti ti-info-circle" />{message}</div>
          ))}
        </section>
      )}
      <DebugDetails batch={batch} moveSummary={moveSummary} />
    </div>
  );
}
