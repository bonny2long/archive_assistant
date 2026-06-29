from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from app.services.metadata_contract import (
    METADATA_CONTRACT_VERSION,
    field_source,
    is_field_envelope,
    metadata_field,
)


AUDIO_EXTENSIONS = {
    ".mp3",
    ".flac",
    ".m4a",
    ".mp4",
    ".aac",
    ".ogg",
    ".opus",
    ".wav",
    ".aiff",
    ".aif",
}

TAG_ALIASES: dict[str, tuple[str, ...]] = {
    "title": ("title", "TIT2", "\xa9nam"),
    "artist": ("artist", "artists", "TPE1", "\xa9ART"),
    "album_artist": ("albumartist", "album artist", "TPE2", "aART"),
    "album": ("album", "TALB", "\xa9alb"),
    "date": ("date", "year", "originaldate", "TDRC", "TYER", "\xa9day"),
    "original_date": ("originaldate", "originalyear", "TDOR"),
    "genre": ("genre", "TCON", "\xa9gen"),
    "track_number": ("tracknumber", "track", "TRCK", "trkn"),
    "disc_number": ("discnumber", "disc", "TPOS", "disk"),
    "composer": ("composer", "TCOM", "\xa9wrt"),
    "album_sort": ("albumsort", "TSOA", "soal"),
    "artist_sort": ("artistsort", "TSOP", "soar"),
    "musicbrainz_artist_id": ("musicbrainz_artistid", "musicbrainz artist id"),
    "musicbrainz_release_id": ("musicbrainz_albumid", "musicbrainz release id"),
    "musicbrainz_recording_id": ("musicbrainz_trackid", "musicbrainz recording id"),
    "acoustid": ("acoustid_id", "acoustid fingerprint", "acoustid"),
    "bpm": ("bpm", "TBPM", "tmpo"),
    "compilation": ("compilation", "TCMP", "cpil"),
    "narrator": ("narrator", "performer", "TMCL", "composer"),
    "series": ("series", "show", "tvshow"),
    "series_index": ("series-part", "series_index", "discsubtitle"),
}

FIELD_CONFIDENCE = {
    "genre": 0.72,
    "date": 0.82,
    "original_date": 0.82,
    "track_number": 0.88,
    "disc_number": 0.88,
    "bpm": 0.82,
    "compilation": 0.82,
}


@dataclass
class EmbeddedMetadataResult:
    path: str
    media_type: str
    fields: dict[str, Any] = field(default_factory=dict)
    technical: dict[str, Any] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    read_ok: bool = False


def _first_text(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, (list, tuple)):
        for item in value:
            text = _first_text(item)
            if text:
                return text
        return None
    if isinstance(value, bytes):
        try:
            value = value.decode("utf-8", errors="replace")
        except Exception:
            return None
    if hasattr(value, "text"):
        return _first_text(getattr(value, "text"))
    text = str(value).strip()
    return text or None


def _tag_value(tags: Any, aliases: tuple[str, ...]) -> str | None:
    if tags is None:
        return None
    for alias in aliases:
        value = None
        try:
            value = tags.get(alias)
        except AttributeError:
            value = None
        if value is None:
            continue
        text = _first_text(value)
        if text:
            return text
    return None


def _split_number(value: str | None) -> tuple[str | None, str | None]:
    if not value:
        return None, None
    left, _, right = str(value).partition("/")
    return left.strip() or None, right.strip() or None


def _technical(media: Any, path: Path) -> dict[str, Any]:
    info = getattr(media, "info", None)
    technical: dict[str, Any] = {
        "file_extension": path.suffix.lower(),
    }
    if info is None:
        return technical
    length = getattr(info, "length", None)
    if length is not None:
        technical["duration_seconds"] = round(float(length), 3)
    bitrate = getattr(info, "bitrate", None)
    if bitrate is not None:
        technical["bitrate"] = int(bitrate)
    sample_rate = getattr(info, "sample_rate", None)
    if sample_rate is not None:
        technical["sample_rate"] = int(sample_rate)
    mime = getattr(info, "mime", None)
    if mime:
        technical["codec"] = _first_text(mime)
    technical.setdefault("container", path.suffix.lower().lstrip("."))
    return technical


def read_embedded_metadata(
    path: str | Path,
    media_type: str | None = None,
) -> EmbeddedMetadataResult:
    """Read embedded metadata from a local media file without mutating it."""
    file_path = Path(path)
    resolved_media_type = (
        media_type
        or ("audio" if file_path.suffix.lower() in AUDIO_EXTENSIONS else "unknown")
    )
    result = EmbeddedMetadataResult(
        path=str(file_path),
        media_type=resolved_media_type,
        technical={"file_extension": file_path.suffix.lower()},
    )
    if file_path.suffix.lower() not in AUDIO_EXTENSIONS:
        result.warnings.append("unsupported_embedded_metadata_type")
        return result
    try:
        from mutagen import File as MutagenFile
    except ImportError:
        result.warnings.append("mutagen_unavailable")
        return result
    try:
        media = MutagenFile(str(file_path), easy=True)
    except Exception as exc:
        result.warnings.append(f"embedded_metadata_read_error:{type(exc).__name__}")
        return result
    if media is None:
        result.warnings.append("embedded_metadata_unreadable")
        return result

    tags = getattr(media, "tags", None)
    for field_name, aliases in TAG_ALIASES.items():
        value = _tag_value(tags, aliases)
        if value:
            result.fields[field_name] = value

    track, total_tracks = _split_number(result.fields.get("track_number"))
    disc, total_discs = _split_number(result.fields.get("disc_number"))
    if track:
        result.fields["track_number"] = track
    if total_tracks:
        result.fields["total_tracks"] = total_tracks
    if disc:
        result.fields["disc_number"] = disc
    if total_discs:
        result.fields["total_discs"] = total_discs

    result.technical.update(_technical(media, file_path))
    result.read_ok = bool(result.fields or len(result.technical) > 1)
    if not result.fields:
        result.warnings.append("embedded_metadata_tags_empty")
    return result


def embedded_field_envelopes(
    result: EmbeddedMetadataResult,
) -> dict[str, dict[str, Any]]:
    envelopes: dict[str, dict[str, Any]] = {}
    for field_name, value in result.fields.items():
        confidence = FIELD_CONFIDENCE.get(field_name, 0.88)
        envelopes[field_name] = metadata_field(
            value,
            source="embedded_tag",
            confidence=confidence,
            reason=f"Read from embedded {field_name} tag.",
            approval_state="pending",
            approved=False,
        )
    for field_name, value in result.technical.items():
        envelopes[field_name] = metadata_field(
            value,
            source="embedded_tag",
            confidence=0.95,
            reason=f"Read from media parser technical field {field_name}.",
            approval_state="pending",
            approved=False,
        )
    return envelopes


def apply_embedded_metadata_evidence(
    metadata: dict[str, Any],
    result: EmbeddedMetadataResult,
    *,
    field_map: dict[str, str] | None = None,
) -> dict[str, Any]:
    contract = dict(metadata.get("metadata_contract") or {})
    contract["version"] = METADATA_CONTRACT_VERSION
    fields = dict(contract.get("fields") or {})
    evidence = embedded_field_envelopes(result)
    field_map = field_map or {}
    conflicts = list(metadata.get("metadata_conflicts") or [])

    for embedded_name, envelope in evidence.items():
        metadata_name = field_map.get(embedded_name, embedded_name)
        existing = fields.get(metadata_name)
        if is_field_envelope(existing) and existing.get("approved"):
            existing_value = existing.get("value")
            if str(existing_value or "") != str(envelope.get("value") or ""):
                conflicts.append({
                    "type": "metadata_conflict",
                    "field": metadata_name,
                    "approved_value": existing_value,
                    "embedded_value": envelope.get("value"),
                    "preferred_value": existing_value,
                    "reason": "Manually approved metadata wins over embedded tag evidence.",
                })
            fields.setdefault(f"embedded_{metadata_name}", envelope)
            continue
        fields[metadata_name] = envelope

    contract["fields"] = fields
    metadata["metadata_contract"] = contract
    metadata["embedded_metadata"] = {
        "read_ok": result.read_ok,
        "path": result.path,
        "media_type": result.media_type,
        "fields": result.fields,
        "technical": result.technical,
        "warnings": result.warnings,
    }
    metadata["embedded_metadata_fields"] = result.fields
    metadata["embedded_technical"] = result.technical
    metadata["extraction_warnings"] = list(dict.fromkeys([
        *list(metadata.get("extraction_warnings") or []),
        *result.warnings,
    ]))
    if conflicts:
        metadata["metadata_conflicts"] = conflicts
    metadata["field_sources"] = {
        **dict(metadata.get("field_sources") or {}),
        **{
            field_map.get(field_name, field_name): field_source(envelope)
            for field_name, envelope in evidence.items()
        },
    }
    metadata["field_confidence"] = {
        **dict(metadata.get("field_confidence") or {}),
        **{
            field_map.get(field_name, field_name): envelope.get("confidence")
            for field_name, envelope in evidence.items()
        },
    }
    return metadata
