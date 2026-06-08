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
