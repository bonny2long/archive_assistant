from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Iterable

from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.time import now_utc
from app.models.archive import IngestBatch, IngestFile

AUDIO_EXTENSIONS = {
    ".mp3", ".flac", ".m4a", ".aac", ".wav", ".ogg", ".opus", ".wma", ".aiff", ".alac"
}
AUDIO_ROLE_VALUES = {"audio", "audio_track", "music_audio", "music_track", "discography_track"}
STRICT_MUSIC_FORMATS = {"FLAC", "MP3"}
_SAFE_PART_PATTERN = re.compile(r'[<>:"/\\|?*]+')
MIXED_FORMAT_WARNING = "mixed_audio_formats_destination_review_required"
UNKNOWN_FORMAT_WARNING = "audio_format_destination_review_required"


def safe_path_part(value: object, fallback: str = "Unknown") -> str:
    text = str(value or "").strip() or fallback
    text = _SAFE_PART_PATTERN.sub(" ", text)
    text = re.sub(r"\s+", " ", text).strip(" .")
    return text or fallback


def file_extension(ingest_file: IngestFile) -> str:
    ext = getattr(ingest_file, "extension", None)
    if ext:
        return str(ext).lower().strip()
    return Path(getattr(ingest_file, "file_name", "") or "").suffix.lower().strip()


def is_audio_file(ingest_file: IngestFile) -> bool:
    role = str(getattr(ingest_file, "detected_role", "") or "").lower()
    return file_extension(ingest_file) in AUDIO_EXTENSIONS or role in AUDIO_ROLE_VALUES


def infer_audio_format_from_files(files: Iterable[IngestFile]) -> str:
    formats = {
        file_extension(ingest_file).lstrip(".").upper()
        for ingest_file in files
        if is_audio_file(ingest_file) and file_extension(ingest_file)
    }
    strict_formats = formats & STRICT_MUSIC_FORMATS
    if strict_formats == {"FLAC"} and formats <= {"FLAC"}:
        return "FLAC"
    if strict_formats == {"MP3"} and formats <= {"MP3"}:
        return "MP3"
    if len(strict_formats) > 1 or len(formats) > 1:
        return "MIXED"
    return next(iter(formats), "UNKNOWN")


def build_music_library_destination(
    *,
    data_root: str | Path | None = None,
    artist: str,
    album: str,
    year: str | int | None,
    audio_format: str,
) -> str:
    format_bucket = str(audio_format or "").upper().strip()
    if format_bucket == "FLAC":
        root = settings.music_flac_dir
    elif format_bucket == "MP3":
        root = settings.music_mp3_dir
    else:
        raise ValueError(f"Unsupported music destination format: {audio_format}")
    if data_root is not None:
        root = Path(data_root) / "Music" / "Library" / format_bucket
    artist_part = safe_path_part(artist, "Unknown Artist")
    album_part = safe_path_part(album, "Unknown Album")
    year_text = safe_path_part(year or "", "").strip()
    album_folder = f"{year_text} - {album_part}" if year_text else album_part
    return str(Path(root) / artist_part / album_folder)


def sync_batch_destination_fields(batch: IngestBatch, destination: str) -> None:
    destination_text = str(destination)
    batch.suggested_destination = destination_text
    suggested = dict(batch.suggested_metadata or {})
    suggested["suggested_destination"] = destination_text
    batch.suggested_metadata = suggested
    metadata = dict(batch.metadata_json or {})
    metadata["suggested_destination"] = destination_text
    batch.metadata_json = metadata


def _destination_fields(batch: IngestBatch) -> dict[str, str]:
    metadata = batch.metadata_json or {}
    suggested = batch.suggested_metadata or {}
    return {
        "batch.suggested_destination": str(batch.suggested_destination or ""),
        "metadata_json.suggested_destination": str(metadata.get("suggested_destination") or ""),
        "suggested_metadata.suggested_destination": str(suggested.get("suggested_destination") or ""),
    }


def validate_music_format_destination(batch: IngestBatch) -> list[str]:
    metadata = batch.metadata_json or {}
    format_bucket = str(metadata.get("format") or "").upper().strip()
    if format_bucket not in STRICT_MUSIC_FORMATS:
        return []
    values = _destination_fields(batch)
    errors: list[str] = []
    missing = [key for key, value in values.items() if not value]
    if missing:
        errors.append(f"Missing destination sync field(s): {', '.join(missing)}.")
        return errors
    normalized = {key: value.replace("\\", "/") for key, value in values.items()}
    if len(set(normalized.values())) != 1:
        errors.append("Music destination fields are not synchronized.")
    expected = f"Music/Library/{format_bucket}"
    wrong = "Music/Library/MP3" if format_bucket == "FLAC" else "Music/Library/FLAC"
    for key, value in normalized.items():
        if expected not in value or wrong in value:
            errors.append(f"{key} does not match {format_bucket} destination authority.")
    return errors


def metadata_identity(metadata: dict[str, Any], batch: IngestBatch | None = None) -> tuple[str, str, str | None]:
    artist = str(metadata.get("artist") or metadata.get("albumartist") or metadata.get("album_artist") or "Unknown Artist")
    album = str(metadata.get("album") or metadata.get("title") or (Path(batch.source_path).name if batch and batch.source_path else "Unknown Album"))
    year_value = metadata.get("year") or metadata.get("date")
    year = str(year_value)[:4] if year_value else None
    return artist, album, year


def _mark_format_review_required(batch: IngestBatch, metadata: dict[str, Any], warning: str, message: str) -> None:
    warnings = list(metadata.get("metadata_warnings") or [])
    if warning not in warnings:
        warnings.append(warning)
    blocking = list(metadata.get("blocking_review_items") or [])
    if not any(isinstance(item, dict) and item.get("type") == warning for item in blocking):
        blocking.append({"type": warning, "message": message})
    metadata["metadata_warnings"] = warnings
    metadata["blocking_review_items"] = blocking
    batch.metadata_confirmed = False
    batch.status = "needs_metadata_review"


def rebuild_music_batch_destination_from_attached_files(batch: IngestBatch, db: Session | None = None) -> dict[str, Any]:
    files = list(batch.files or [])
    if db is not None and not files and batch.id is not None:
        files = db.query(IngestFile).filter(IngestFile.batch_id == batch.id).all()
    metadata = dict(batch.metadata_json or {})
    audio_format = infer_audio_format_from_files(files)
    metadata["file_count"] = len(files)
    audio_files = [ingest_file for ingest_file in files if is_audio_file(ingest_file)]
    if audio_files:
        metadata["track_count"] = len(audio_files)
    if audio_format in STRICT_MUSIC_FORMATS:
        metadata["format"] = audio_format
        warnings = [item for item in list(metadata.get("metadata_warnings") or []) if item not in {MIXED_FORMAT_WARNING, UNKNOWN_FORMAT_WARNING}]
        blocking = [
            item for item in list(metadata.get("blocking_review_items") or [])
            if not (isinstance(item, dict) and item.get("type") in {MIXED_FORMAT_WARNING, UNKNOWN_FORMAT_WARNING})
        ]
        metadata["metadata_warnings"] = warnings
        metadata["blocking_review_items"] = blocking
        batch.metadata_json = metadata
        suggested = dict(batch.suggested_metadata or {})
        artist, album, year = metadata_identity(metadata, batch)
        destination = build_music_library_destination(artist=artist, album=album, year=year, audio_format=audio_format)
        suggested.update({
            "artist": artist,
            "album": album,
            "year": year,
            "format": audio_format,
            "primary_genre": metadata.get("primary_genre") or metadata.get("genre"),
        })
        batch.suggested_metadata = suggested
        sync_batch_destination_fields(batch, destination)
        metadata = dict(batch.metadata_json or {})
        metadata["format"] = audio_format
        batch.metadata_json = metadata
    elif audio_format == "MIXED":
        metadata["format"] = "MIXED"
        batch.metadata_json = metadata
        _mark_format_review_required(batch, metadata, MIXED_FORMAT_WARNING, "Mixed audio formats require destination review before move.")
    else:
        metadata["format"] = audio_format
        batch.metadata_json = metadata
        _mark_format_review_required(batch, metadata, UNKNOWN_FORMAT_WARNING, "Audio format could not be verified from attached files.")
    errors = validate_music_format_destination(batch)
    if errors:
        metadata = dict(batch.metadata_json or {})
        _mark_format_review_required(batch, metadata, "music_destination_sync_mismatch", "Destination does not match file format. Rebuild required before move.")
        batch.metadata_json = metadata
    batch.updated_at = now_utc()
    return {
        "audio_format": audio_format,
        "destination": batch.suggested_destination,
        "errors": errors,
        "file_count": len(files),
        "audio_file_count": len(audio_files),
    }
