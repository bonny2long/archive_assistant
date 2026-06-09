import type { BatchSummary, IngestBatch } from "../types/archive";

type DisplayBatch = BatchSummary | IngestBatch;

function metadataValue(batch: DisplayBatch, key: string): unknown {
  return "metadata_json" in batch ? batch.metadata_json?.[key] : undefined;
}

export function getReleaseCount(batch: DisplayBatch): number {
  const metadataCount = Number(
    metadataValue(batch, "release_count")
    ?? metadataValue(batch, "album_count")
    ?? 0,
  );
  if (metadataCount > 0) return metadataCount;
  if ("release_count" in batch && batch.release_count > 0) return batch.release_count;
  if ("album_count" in batch && batch.album_count > 0) return batch.album_count;
  if ("albums" in batch && batch.albums.length > 0) return batch.albums.length;
  return 0;
}

export function getBatchDisplayTitle(batch: DisplayBatch): string {
  if (batch.detected_type === "video_movie") {
    const title = (
      ("title" in batch ? batch.title : null)
      ?? metadataValue(batch, "title")
      ?? "Unknown Movie"
    );
    const year = (
      ("year" in batch ? batch.year : null)
      ?? metadataValue(batch, "year")
    );
    return year
      ? `Movie - ${String(title)} (${String(year)})`
      : `Movie - ${String(title)}`;
  }

  const metadataArtist = metadataValue(batch, "artist")
    ?? metadataValue(batch, "albumartist");
  const artist = (
    ("artist" in batch ? batch.artist : null)
    ?? batch.suggested_metadata?.artist
    ?? metadataArtist
    ?? "Unknown Artist"
  );

  if (batch.detected_type === "music_discography") {
    const releaseCount = getReleaseCount(batch);
    return releaseCount
      ? `${String(artist)} - ${releaseCount} release discography`
      : `${String(artist)} - Discography`;
  }

  const album = (
    ("album" in batch ? batch.album : null)
    ?? batch.suggested_metadata?.album
    ?? metadataValue(batch, "album")
    ?? "Unknown Album"
  );
  return `${String(artist)} - ${String(album)}`;
}

export function getBatchMediaLabel(batch: DisplayBatch): string {
  if ("media_label" in batch && batch.media_label) {
    return batch.media_label === "Music Album" ? "Music" : batch.media_label;
  }
  if (batch.detected_type === "music_album") return "Music";
  if (batch.detected_type === "music_discography") return "Discography";
  if (batch.detected_type === "video_movie") return "Movie";
  return "Quarantine Review";
}

export function getBatchPrimaryName(batch: DisplayBatch): string {
  if ("primary_name" in batch && batch.primary_name) return batch.primary_name;
  if (batch.detected_type === "video_movie") {
    return String(
      ("title" in batch ? batch.title : null)
      ?? metadataValue(batch, "title")
      ?? "Unknown Movie",
    );
  }
  if (batch.detected_type === "unknown_type" || batch.detected_type === "unsupported_file") {
    return String(
      ("name" in batch ? batch.name : null)
      ?? metadataValue(batch, "name")
      ?? "Unknown item",
    );
  }
  return String(
    ("artist" in batch ? batch.artist : null)
    ?? batch.suggested_metadata?.artist
    ?? metadataValue(batch, "artist")
    ?? metadataValue(batch, "albumartist")
    ?? "Unknown Artist",
  );
}

export function getBatchSecondaryName(batch: DisplayBatch): string {
  if ("secondary_name" in batch && batch.secondary_name) return batch.secondary_name;
  if (batch.detected_type === "music_discography") {
    const releaseCount = getReleaseCount(batch);
    return releaseCount ? `${releaseCount} release discography` : "Discography";
  }
  if (batch.detected_type === "video_movie") {
    const year = ("year" in batch ? batch.year : null) ?? metadataValue(batch, "year");
    return year ? `${String(year)} movie` : "Movie";
  }
  if (batch.detected_type === "unknown_type" || batch.detected_type === "unsupported_file") {
    const fileCount = "file_count" in batch ? batch.file_count : metadataValue(batch, "file_count");
    return fileCount
      ? `${String(fileCount)} file(s)`
      : String(metadataValue(batch, "reason") ?? batch.detected_type);
  }
  return String(
    ("album" in batch ? batch.album : null)
    ?? batch.suggested_metadata?.album
    ?? metadataValue(batch, "album")
    ?? "Unknown Album",
  );
}

export function getBatchItemText(batch: DisplayBatch): string {
  if ("item_count" in batch && batch.item_label) {
    const label = batch.item_count === 1
      ? batch.item_label.replace(/s$/, "")
      : batch.item_label;
    return `${batch.item_count} ${label}`;
  }
  if (batch.detected_type === "video_movie") {
    const count = "video_file_count" in batch
      ? batch.video_file_count
      : Number(metadataValue(batch, "video_file_count") ?? 0);
    return `${count} ${count === 1 ? "video" : "videos"}`;
  }
  if (batch.detected_type === "unknown_type" || batch.detected_type === "unsupported_file") {
    const count = "file_count" in batch
      ? batch.file_count
      : Number(metadataValue(batch, "file_count") ?? 0);
    return `${count} ${count === 1 ? "file" : "files"}`;
  }
  const count = "track_count" in batch
    ? batch.track_count
    : Number(metadataValue(batch, "track_count") ?? 0);
  return `${count} ${count === 1 ? "track" : "tracks"}`;
}

export function getBatchEditKind(batch: BatchSummary): string | null {
  if (batch.edit_kind !== undefined) return batch.edit_kind;
  if (batch.detected_type === "video_movie") return "movie";
  if (batch.detected_type === "music_discography") return "music_discography";
  if (batch.detected_type === "music_album") return "music_album";
  return null;
}
