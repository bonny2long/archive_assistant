from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

from app.core.config import settings
from app.core.time import serialize_utc


MANIFEST_VERSION = "v1"
ARCHIVE_ASSISTANT_VERSION = "v2.066"


def _relative(path: Path) -> str:
    try:
        return path.resolve().relative_to(settings.data_root.resolve()).as_posix()
    except ValueError:
        return path.as_posix()


def _source_relative(path: Path, source_root: Path) -> str:
    try:
        return path.relative_to(source_root).as_posix()
    except ValueError:
        try:
            return path.relative_to(source_root.parent).as_posix()
        except ValueError:
            return path.name


def _slug(value: str) -> str:
    normalized = re.sub(r"[^a-z0-9]+", "-", value.casefold()).strip("-")
    return normalized[:80] or "batch"


def _manifest_paths(
    *,
    batch_id: int,
    detected_type: str,
    review_type: str,
    metadata: dict,
    destination_roots: list[Path],
    created_at: datetime,
) -> tuple[Path, Path]:
    collection = (
        detected_type == "book"
        and review_type == "book_collection"
    )
    if collection:
        title = str(
            metadata.get("collection_title")
            or metadata.get("title")
            or f"batch-{batch_id}"
        )
        stem = (
            f"{created_at.date().isoformat()}_{batch_id}_"
            f"{_slug(title)}_move_manifest"
        )
        directory = settings.books_metadata_dir / "move_manifests"
        return directory / f"{stem}.json", directory / f"{stem}.md"
    if detected_type == "music_discography":
        artist = str(metadata.get("artist") or f"batch-{batch_id}")
        stem = (
            f"{created_at.date().isoformat()}_{batch_id}_"
            f"{_slug(artist)}-discography_move_manifest"
        )
        directory = settings.music_metadata_dir / "move_manifests"
        return directory / f"{stem}.json", directory / f"{stem}.md"
    if detected_type == "video_movie" and review_type == "movie_collection":
        title = str(
            metadata.get("collection_title")
            or metadata.get("title")
            or f"batch-{batch_id}"
        )
        stem = (
            f"{created_at.date().isoformat()}_{batch_id}_"
            f"{_slug(title)}_move_manifest"
        )
        directory = settings.movies_metadata_dir / "move_manifests"
        return directory / f"{stem}.json", directory / f"{stem}.md"

    destination = (
        destination_roots[0]
        if destination_roots and metadata.get("metadata_locked_for_move")
        else None
    )
    if destination is None:
        if detected_type == "audiobook":
            directory = settings.audiobooks_metadata_dir / "move_manifests"
        elif detected_type == "book":
            directory = settings.books_metadata_dir / "move_manifests"
        else:
            directory = settings.data_root / "_REPORTS" / "move_manifests"
        stem = f"{created_at.date().isoformat()}_{batch_id}_move_manifest"
        return directory / f"{stem}.json", directory / f"{stem}.md"

    directory = destination / "metadata"
    return directory / "move_manifest.json", directory / "move_manifest.md"


def _confirmed_metadata(detected_type: str, metadata: dict) -> dict:
    if detected_type == "video_movie":
        if (
            metadata.get("review_type") == "movie_collection"
            or metadata.get("movie_items")
        ):
            return {
                "collection_title": metadata.get("collection_title"),
                "items": [
                    {
                        key: item.get(key)
                        for key in (
                            "source_file", "title", "year", "edition",
                            "format", "resolution", "source",
                            "destination_preview",
                        )
                    }
                    for item in metadata.get("movie_items") or []
                    if isinstance(item, dict) and item.get("include", True)
                ],
            }
        return {
            key: metadata.get(key)
            for key in (
                "title", "year", "edition", "resolution", "source", "format",
            )
        }
    if detected_type == "music_album":
        return {
            "album_artist": (
                metadata.get("album_artist")
                or metadata.get("albumartist")
                or metadata.get("artist")
            ),
            "album_title": metadata.get("album"),
            "year": metadata.get("year") or metadata.get("date"),
            "genre": metadata.get("genre"),
            "format": metadata.get("format"),
        }
    if detected_type == "music_discography":
        return {
            "discography_artist": metadata.get("artist"),
            "albums": [
                {
                    key: album.get(key)
                    for key in (
                        "source_folder", "album", "year", "release_type",
                        "format", "disc_count", "track_count",
                        "artwork_count", "include",
                    )
                }
                for album in metadata.get("albums") or []
                if isinstance(album, dict) and album.get("include", True)
            ],
        }
    if detected_type == "audiobook":
        keys = (
            "author", "title", "year", "narrator", "series",
            "series_index", "format",
        )
        return {key: metadata.get(key) for key in keys}
    if detected_type == "book":
        items = []
        for item in metadata.get("book_items") or []:
            if not isinstance(item, dict) or not item.get("include", True):
                continue
            items.append({
                key: item.get(key)
                for key in (
                    "source_file", "title", "author", "year", "format",
                    "series", "series_index", "destination_preview",
                )
            })
        if items:
            return {
                "collection_title": metadata.get("collection_title"),
                "keep_collection_together": bool(
                    metadata.get("keep_collection_together")
                ),
                "collection_destination_root": metadata.get(
                    "collection_destination_root"
                ),
                "items": items,
            }
        keys = ("title", "author", "year", "format")
        return {key: metadata.get(key) for key in keys}
    return {
        key: metadata.get(key)
        for key in (
            "artist", "album", "title", "show_title", "year",
            "genre", "format",
        )
        if metadata.get(key) is not None
    }


def _accepted_unknowns(detected_type: str, metadata: dict) -> dict:
    if detected_type == "video_movie":
        if (
            metadata.get("review_type") == "movie_collection"
            or metadata.get("movie_items")
        ):
            return {
                "items": [
                    {
                        "source_file": item.get("source_file"),
                        "accepted_unknown_title": bool(
                            item.get("accepted_unknown_title")
                        ),
                        "accepted_unknown_year": bool(
                            item.get("accepted_unknown_year")
                        ),
                        "lookup_later": bool(item.get("lookup_later")),
                    }
                    for item in metadata.get("movie_items") or []
                    if isinstance(item, dict) and any((
                        item.get("accepted_unknown_title"),
                        item.get("accepted_unknown_year"),
                        item.get("lookup_later"),
                    ))
                ],
            }
        return {
            "title": bool(metadata.get("accepted_unknown_title")),
            "year": bool(metadata.get("accepted_unknown_year")),
            "items": [],
        }
    if detected_type == "music_album":
        return {
            "album_artist": bool(
                metadata.get("accepted_unknown_album_artist")
            ),
            "album_title": bool(
                metadata.get("accepted_unknown_album_title")
            ),
            "year": bool(metadata.get("accepted_unknown_year")),
            "items": [],
        }
    if detected_type == "music_discography":
        return {
            "discography_artist": bool(
                metadata.get("accepted_unknown_discography_artist")
            ),
            "items": [
                {
                    "source_folder": album.get("source_folder"),
                    "accepted_unknown_album_artist": bool(
                        album.get("accepted_unknown_album_artist")
                    ),
                    "accepted_unknown_album_title": bool(
                        album.get("accepted_unknown_album_title")
                    ),
                    "accepted_unknown_year": bool(
                        album.get("accepted_unknown_year")
                    ),
                    "lookup_later": bool(album.get("lookup_later")),
                }
                for album in metadata.get("albums") or []
                if isinstance(album, dict) and any((
                    album.get("accepted_unknown_album_artist"),
                    album.get("accepted_unknown_album_title"),
                    album.get("accepted_unknown_year"),
                    album.get("lookup_later"),
                ))
            ],
        }
    if detected_type == "audiobook":
        return {
            "author": bool(metadata.get("accepted_unknown_author")),
            "year": bool(metadata.get("accepted_unknown_year")),
            "narrator": bool(metadata.get("accepted_unknown_narrator")),
            "items": [],
        }
    items = []
    for item in metadata.get("book_items") or []:
        if not isinstance(item, dict):
            continue
        if not (
            item.get("accepted_unknown_author")
            or item.get("accepted_unknown_year")
            or item.get("lookup_later")
        ):
            continue
        items.append({
            "source_file": item.get("source_file"),
            "accepted_unknown_author": bool(
                item.get("accepted_unknown_author")
            ),
            "accepted_unknown_year": bool(
                item.get("accepted_unknown_year")
            ),
            "lookup_later": bool(item.get("lookup_later")),
        })
    return {"items": items}


def _lookup_later(detected_type: str, metadata: dict) -> list[dict]:
    values = []
    if detected_type == "video_movie" and metadata.get("lookup_later"):
        values.append({
            "scope": "batch",
            "title": metadata.get("title"),
        })
    if detected_type == "video_movie":
        for item in metadata.get("movie_items") or []:
            if isinstance(item, dict) and item.get("lookup_later"):
                values.append({
                    "scope": "movie",
                    "source_file": item.get("source_file"),
                    "title": item.get("title"),
                })
    if detected_type in {"music_album", "music_discography"} and metadata.get(
        "lookup_later"
    ):
        values.append({
            "scope": "batch",
            "title": metadata.get("album") or metadata.get("artist"),
        })
    if detected_type == "music_discography":
        for album in metadata.get("albums") or []:
            if isinstance(album, dict) and album.get("lookup_later"):
                values.append({
                    "scope": "album",
                    "source_folder": album.get("source_folder"),
                    "title": album.get("album"),
                })
    if detected_type == "audiobook" and metadata.get("lookup_later"):
        values.append({
            "scope": "batch",
            "title": metadata.get("title"),
        })
    for item in metadata.get("book_items") or []:
        if isinstance(item, dict) and item.get("lookup_later"):
            values.append({
                "scope": "item",
                "source_file": item.get("source_file"),
                "title": item.get("title"),
            })
    return values


def _ignored_sidecars(metadata: dict) -> list[dict]:
    values = []
    seen = set()
    candidates: Iterable[object] = (
        metadata.get("ignored_sidecar_files")
        or metadata.get("sidecars_ignored")
        or []
    )
    for value in candidates:
        path = str(
            value.get("file") if isinstance(value, dict) else value
        )
        if not path or path in seen:
            continue
        seen.add(path)
        values.append({
            "source_relative": path.replace("\\", "/"),
            "reason": "ignored_sidecar",
        })
    return values


def _summary(detected_type: str, metadata: dict, manifest: dict) -> dict:
    if detected_type == "video_movie":
        if (
            metadata.get("review_type") == "movie_collection"
            or metadata.get("movie_items")
        ):
            included = [
                item for item in metadata.get("movie_items") or []
                if isinstance(item, dict) and item.get("include", True)
            ]
            years = sorted({
                str(item.get("year"))
                for item in included
                if str(item.get("year") or "").isdigit()
            })
            return {
                "collection_title": metadata.get("collection_title"),
                "movie_count": len(included),
                "year_range": (
                    years[0] if len(years) == 1
                    else f"{years[0]}-{years[-1]}" if years else None
                ),
                "poster_count": len(manifest["artwork_moved"]),
                "subtitle_count": len(manifest["subtitles_moved"]),
                "extra_count": metadata.get("extra_count", 0),
                "ignored_sidecar_count": len(manifest["sidecars_ignored"]),
                "files_moved_count": (
                    len(manifest["files_moved"])
                    + len(manifest["artwork_moved"])
                    + len(manifest["subtitles_moved"])
                ),
                "failed_move_count": len(manifest["failed_moves"]),
            }
        return {
            "title": metadata.get("title"),
            "year": metadata.get("year"),
            "format": metadata.get("format"),
            "video_file_count": metadata.get("video_file_count", 0),
            "poster_count": len(manifest["artwork_moved"]),
            "subtitle_count": len(manifest["subtitles_moved"]),
            "extra_count": metadata.get("extra_count", 0),
            "ignored_sidecar_count": len(manifest["sidecars_ignored"]),
            "files_moved_count": (
                len(manifest["files_moved"])
                + len(manifest["artwork_moved"])
                + len(manifest["subtitles_moved"])
            ),
            "failed_move_count": len(manifest["failed_moves"]),
        }
    if detected_type == "music_album":
        return {
            "album_artist": (
                metadata.get("album_artist")
                or metadata.get("albumartist")
                or metadata.get("artist")
            ),
            "album_title": metadata.get("album"),
            "year": metadata.get("year") or metadata.get("date"),
            "format": metadata.get("format"),
            "disc_count": metadata.get("disc_count", 1),
            "track_count": metadata.get("track_count", 0),
            "artwork_count": len(manifest["artwork_moved"]),
            "ignored_sidecar_count": len(manifest["sidecars_ignored"]),
            "failed_move_count": len(manifest["failed_moves"]),
        }
    if detected_type == "music_discography":
        return {
            "discography_artist": metadata.get("artist"),
            "album_count": metadata.get("album_count", 0),
            "track_count": metadata.get("track_count", 0),
            "artwork_count": len(manifest["artwork_moved"]),
            "ignored_sidecar_count": len(manifest["sidecars_ignored"]),
            "failed_move_count": len(manifest["failed_moves"]),
        }
    if detected_type == "audiobook":
        title = metadata.get("title")
        author = metadata.get("author")
        item_count = metadata.get("audiobook_file_count")
    elif detected_type == "book":
        title = metadata.get("collection_title") or metadata.get("title")
        author = metadata.get("author")
        item_count = len(
            [
                item for item in metadata.get("book_items") or []
                if isinstance(item, dict) and item.get("include", True)
            ]
        ) or metadata.get("book_file_count")
    else:
        title = (
            metadata.get("album")
            or metadata.get("title")
            or metadata.get("show_title")
        )
        author = metadata.get("artist")
        item_count = len(manifest["files_moved"])
    return {
        "title": title,
        "author": author,
        "year": metadata.get("year"),
        "format": metadata.get("format"),
        "item_count": item_count or len(manifest["files_moved"]),
        "artwork_count": len(manifest["artwork_moved"]),
        "ignored_sidecar_count": len(manifest["sidecars_ignored"]),
        "failed_move_count": len(manifest["failed_moves"]),
    }


def _markdown(manifest: dict) -> str:
    summary = manifest["summary"]
    accepted = manifest["accepted_unknowns"]
    heading = (
        summary.get("title")
        or summary.get("collection_title")
        or summary.get("album_title")
        or summary.get("discography_artist")
        or f"Batch {manifest['batch_id']}"
    )
    lines = [
        f"# Move Manifest - {heading}",
        "",
        f"Archive Assistant version: {manifest['archive_assistant_version']}  ",
        f"Moved at: {manifest['created_at']}  ",
        f"Batch ID: {manifest['batch_id']}  ",
        f"Type: {manifest['review_type']}  ",
        f"Status: {manifest['status_after_move']}  ",
        "",
        "## Summary",
        "",
        f"- Title: {summary.get('title') or summary.get('collection_title') or summary.get('album_title') or summary.get('discography_artist') or 'Unknown'}",
        f"- Author/Artist: {summary.get('author') or summary.get('album_artist') or summary.get('discography_artist') or 'Unknown'}",
        f"- Year: {summary.get('year') or 'Unknown Year'}",
        f"- Format: {summary.get('format') or 'Unknown'}",
        f"- Files moved: {len(manifest['files_moved'])}",
        f"- Artwork moved: {len(manifest['artwork_moved'])}",
        f"- Ignored sidecars: {len(manifest['sidecars_ignored'])}",
        f"- Failed moves: {len(manifest['failed_moves'])}",
        "",
        "## Accepted Unknowns",
        "",
    ]
    if "author" in accepted:
        lines.extend([
            f"- Author: {'accepted as unknown' if accepted['author'] else 'not accepted'}",
            f"- Year: {'accepted as unknown' if accepted['year'] else 'not accepted'}",
            f"- Narrator: {'accepted as unknown' if accepted['narrator'] else 'not accepted'}",
        ])
    elif "album_artist" in accepted:
        lines.extend([
            f"- Album artist: {'accepted as unknown' if accepted['album_artist'] else 'not accepted'}",
            f"- Album title: {'accepted as unknown' if accepted['album_title'] else 'not accepted'}",
            f"- Year: {'accepted as unknown' if accepted['year'] else 'not accepted'}",
        ])
    elif "discography_artist" in accepted:
        lines.append(
            "- Discography artist: "
            f"{'accepted as unknown' if accepted['discography_artist'] else 'not accepted'}"
        )
        for item in accepted.get("items", []):
            lines.append(
                f"- {item.get('source_folder') or 'Unknown release'}: "
                f"{json.dumps(item, sort_keys=True)}"
            )
    elif "title" in accepted:
        lines.extend([
            f"- Movie title: {'accepted as unknown' if accepted['title'] else 'not accepted'}",
            f"- Movie year: {'accepted as unknown' if accepted['year'] else 'not accepted'}",
        ])
    elif accepted.get("items"):
        for item in accepted["items"]:
            flags = []
            if item.get("accepted_unknown_author"):
                flags.append("unknown author accepted")
            if item.get("accepted_unknown_title"):
                flags.append("unknown title accepted")
            if item.get("accepted_unknown_year"):
                flags.append("unknown year accepted")
            if item.get("lookup_later"):
                flags.append("lookup later")
            lines.append(
                f"- {item.get('source_file') or 'Unknown item'}: "
                f"{', '.join(flags)}"
            )
    else:
        lines.append("- None")

    lines.extend(["", "## Destination", ""])
    lines.extend(
        f"- {path}" for path in manifest["destination_roots"]
    )
    lines.extend(["", "## Files Moved", ""])
    moved = manifest["files_moved"]
    for item in moved[:200]:
        lines.append(
            f"- {item['source_relative']} -> {item['destination_relative']}"
        )
    if len(moved) > 200:
        lines.append(
            f"- {len(moved) - 200} additional files are listed in JSON."
        )

    lines.extend(["", "## Artwork", ""])
    lines.extend(
        f"- {item['destination_relative']}"
        for item in manifest["artwork_moved"]
    )
    if not manifest["artwork_moved"]:
        lines.append("- None")

    lines.extend(["", "## Subtitles", ""])
    lines.extend(
        f"- {item['destination_relative']}"
        for item in manifest.get("subtitles_moved", [])
    )
    if not manifest.get("subtitles_moved"):
        lines.append("- None")

    lines.extend(["", "## Notes", ""])
    for note in manifest["notes"]:
        lines.append(f"- {note}")
    return "\n".join(lines) + "\n"


def write_move_manifest(
    *,
    batch,
    move_actions: list,
    failed_messages: list[str],
) -> tuple[dict | None, list[str]]:
    metadata = dict(batch.metadata_json or {})
    created_at = datetime.now(timezone.utc)
    source_root = Path(batch.source_path)
    file_by_path = {
        str(Path(item.file_path)): item for item in batch.files
    }
    completed = []
    failed = []
    destinations: list[Path] = []
    seen_completed = set()
    review_type = str(
        metadata.get("review_type") or batch.detected_type
    )

    for action in move_actions:
        source = Path(action.source_path)
        destination = Path(action.destination_path)
        if action.status == "completed":
            key = (str(source), str(destination))
            if key in seen_completed:
                continue
            seen_completed.add(key)
            ingest_file = file_by_path.get(str(source))
            role = (
                ingest_file.detected_role
                if ingest_file is not None
                else "media_file"
            )
            entry = {
                "source_relative": _source_relative(source, source_root),
                "destination_relative": _relative(destination),
                "role": role,
                "size_bytes": (
                    ingest_file.size_bytes if ingest_file is not None else None
                ),
            }
            if ingest_file is not None and ingest_file.extension:
                entry["format"] = ingest_file.extension.lstrip(".").upper()
            completed.append(entry)
            destinations.append(destination.parent)
        elif action.status == "failed":
            failed.append({
                "source_relative": _source_relative(source, source_root),
                "intended_destination_relative": _relative(destination),
                "error": action.error_message or "move_failed",
            })

    for message in failed_messages:
        if any(item["error"] == message for item in failed):
            continue
        failed.append({
            "source_relative": None,
            "intended_destination_relative": None,
            "error": message,
        })

    destination_roots = []
    if (
        (
            batch.detected_type == "book"
            and review_type == "book_collection"
        )
        or (
            batch.detected_type == "video_movie"
            and review_type == "movie_collection"
        )
        and destinations
    ):
        destination_roots.extend(destinations)
    elif batch.suggested_destination:
        destination_roots.append(Path(batch.suggested_destination))
    elif destinations:
        destination_roots.extend(destinations)
    destination_roots = sorted(
        {path.resolve() for path in destination_roots},
        key=lambda path: str(path).casefold(),
    )
    json_path, markdown_path = _manifest_paths(
        batch_id=batch.id,
        detected_type=batch.detected_type,
        review_type=review_type,
        metadata=metadata,
        destination_roots=destination_roots,
        created_at=created_at,
    )

    artwork_roles = {
        "artwork", "audiobook_artwork", "book_artwork",
        "movie_artwork", "tv_artwork",
    }
    artwork_moved = []
    subtitles_moved = []
    files_moved = []
    for entry in completed:
        if entry["role"] in artwork_roles:
            artwork_moved.append({
                **entry,
                "matched_to": metadata.get("title")
                or metadata.get("collection_title")
                or metadata.get("album")
                or metadata.get("artist"),
                "match_method": (
                    "audiobook_sidecar_artwork"
                    if batch.detected_type == "audiobook"
                    else "music_sidecar_artwork"
                    if batch.detected_type in {
                        "music_album", "music_discography"
                    }
                    else "generic_movie_poster_name"
                    if (
                        batch.detected_type == "video_movie"
                        and Path(
                            str(entry.get("source_relative") or "")
                        ).stem.casefold()
                        in {"poster", "cover", "folder", "movie", "front"}
                    )
                    else "normalized_basename"
                ),
                "confidence": 0.9,
            })
        elif entry["role"] == "subtitle":
            subtitles_moved.append(entry)
        else:
            files_moved.append(entry)

    excluded = []
    for item in metadata.get("book_items") or []:
        if isinstance(item, dict) and not item.get("include", True):
            excluded.append({
                "source_relative": item.get("source_file"),
                "reason": "excluded_from_batch",
            })
    for item in metadata.get("movie_items") or []:
        if isinstance(item, dict) and not item.get("include", True):
            excluded.append({
                "source_relative": item.get("source_file"),
                "reason": "excluded_from_batch",
            })

    manifest = {
        "manifest_version": MANIFEST_VERSION,
        "archive_assistant_version": ARCHIVE_ASSISTANT_VERSION,
        "created_at": serialize_utc(created_at),
        "batch_id": batch.id,
        "source_kind": batch.source_kind,
        "source_path": _relative(source_root),
        "detected_type": batch.detected_type,
        "review_type": review_type,
        "status_after_move": batch.status,
        "metadata_confirmed": bool(batch.metadata_confirmed),
        "review_confirmed": bool(metadata.get("review_confirmed")),
        "metadata_locked_for_move": bool(
            metadata.get("metadata_locked_for_move")
        ),
        "confidence": batch.confidence,
        "summary": {},
        "confirmed_metadata": _confirmed_metadata(
            batch.detected_type, metadata
        ),
        "accepted_unknowns": _accepted_unknowns(
            batch.detected_type, metadata
        ),
        "lookup_later": _lookup_later(batch.detected_type, metadata),
        "release_cleanup": (
            {
                "collection": metadata.get("release_cleanup"),
                "items": [
                    {
                        "source_file": item.get("source_file"),
                        **dict(item.get("release_cleanup") or {}),
                    }
                    for item in metadata.get("movie_items") or []
                    if isinstance(item, dict)
                ],
            }
            if batch.detected_type == "video_movie"
            and review_type == "movie_collection"
            else metadata.get("release_cleanup")
        ),
        "tracks": [
            {
                "track_number": (
                    (item.metadata_json or {}).get("tracknumber")
                ),
                "disc_number": (
                    (item.metadata_json or {}).get("discnumber")
                ),
                "title": (item.metadata_json or {}).get("title"),
                "track_artist": (item.metadata_json or {}).get("artist"),
                "file_name": item.file_name,
                "format": item.extension.lstrip(".").upper(),
            }
            for item in batch.files
            if batch.detected_type in {
                "music_album", "music_discography"
            }
            and item.detected_role not in {"artwork"}
        ],
        "files_moved": files_moved,
        "artwork_moved": artwork_moved,
        "subtitles_moved": subtitles_moved,
        "sidecars_ignored": _ignored_sidecars(metadata),
        "files_skipped": excluded,
        "failed_moves": failed,
        "destination_roots": [
            _relative(path) for path in destination_roots
        ],
        "notes": [
            "Metadata was manually reviewed before move.",
            "No embedded tags were modified.",
            "Existing destination files were not overwritten.",
        ],
    }
    manifest["summary"] = _summary(
        batch.detected_type, metadata, manifest
    )

    warnings = []
    try:
        json_path.parent.mkdir(parents=True, exist_ok=True)
        json_path.write_text(
            json.dumps(manifest, indent=2, default=str),
            encoding="utf-8",
        )
    except OSError as exc:
        return None, [f"JSON move manifest failed: {exc}"]

    try:
        markdown_path.write_text(_markdown(manifest), encoding="utf-8")
    except OSError as exc:
        warnings.append(f"Markdown move manifest failed: {exc}")

    pointer = {
        "json_path": _relative(json_path),
        "markdown_path": (
            _relative(markdown_path) if markdown_path.exists() else None
        ),
        "created_at": manifest["created_at"],
        "manifest_version": MANIFEST_VERSION,
        "archive_assistant_version": ARCHIVE_ASSISTANT_VERSION,
        "files_moved": len(files_moved),
        "artwork_moved": len(artwork_moved),
        "failed_moves": len(failed),
    }
    return pointer, warnings
