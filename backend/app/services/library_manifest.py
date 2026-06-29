import json
from pathlib import Path
from typing import Any

from app.core.time import now_utc, serialize_utc
from app.services.metadata_contract import (
    metadata_manifest_header,
    summarize_metadata_sources,
)


MANIFEST_VERSION = 1


def _manifest_type_from_filename(filename: str) -> str:
    mapping = {
        "music-album.json": "music_album",
        "music-release.json": "music_release",
        "book.json": "book",
        "audiobook.json": "audiobook",
        "movie.json": "movie",
        "tv-show.json": "tv_show",
        "discography.json": "music_discography",
    }
    return mapping.get(filename, Path(filename).stem.replace("-", "_"))


def _relative_library_path(path: Path) -> str:
    normalized = str(path).replace("\\", "/")
    markers = [
        "Audiobooks/Library/",
        "Books/",
        "Movies/Library/",
        "Music/Discographies/",
        "Music/Library/",
        "TV/Library/",
    ]
    lower = normalized.lower()
    for marker in markers:
        index = lower.find(marker.lower())
        if index >= 0:
            return normalized[index:].rstrip("/")
    return normalized


def write_library_manifest(
    destination: Path,
    filename: str,
    payload: dict[str, Any],
) -> Path:
    metadata_dir = destination / "metadata"
    metadata_dir.mkdir(parents=True, exist_ok=True)
    path = metadata_dir / filename
    header = metadata_manifest_header(
        manifest_type=_manifest_type_from_filename(filename),
        manifest_version=MANIFEST_VERSION,
        media_type=payload.get("media_kind"),
        sources_summary=summarize_metadata_sources(payload),
    )
    document = {
        "schema_version": 1,
        "generated_at": serialize_utc(now_utc()),
        "library_path": _relative_library_path(destination),
        **header,
        **payload,
    }
    path.write_text(
        json.dumps(document, indent=2, ensure_ascii=False, default=str),
        encoding="utf-8",
    )
    return path


def append_library_index_entry(
    index_dir: Path,
    entry: dict[str, Any],
) -> Path:
    index_dir.mkdir(parents=True, exist_ok=True)
    path = index_dir / "library-index.json"
    existing: list[dict[str, Any]] = []
    if path.exists():
        try:
            loaded = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(loaded, list):
                existing = [item for item in loaded if isinstance(item, dict)]
        except (OSError, ValueError):
            existing = []

    key = entry.get("library_path") or entry.get("destination_path")
    if key:
        existing = [
            item
            for item in existing
            if item.get("library_path") != key
            and item.get("destination_path") != key
        ]

    existing.append({
        "indexed_at": serialize_utc(now_utc()),
        **entry,
    })
    path.write_text(
        json.dumps(existing, indent=2, ensure_ascii=False, default=str),
        encoding="utf-8",
    )
    return path
