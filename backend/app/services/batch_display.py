from pathlib import Path

from app.models.archive import IngestBatch


MUSIC_TYPES = {"music_album", "music_discography"}
MOVIE_TYPES = {"video_movie"}
TV_TYPES = {"video_tv_show", "video_tv_episode"}
BOOK_TYPES = {"book"}
AUDIOBOOK_TYPES = {"audiobook"}
QUARANTINE_TYPES = {"unknown_type", "unsupported_file"}


def _plural(count: int, singular: str, plural: str | None = None) -> str:
    return f"{count} {singular if count == 1 else plural or singular + 's'}"


def _parent_review_media_label(detected_type: str) -> str:
    if detected_type == "music_discography":
        return "Discography Source"
    if detected_type in {"book", "audiobook", "video_movie", "video_tv_show", "video_tv_episode"}:
        return "Collection Source"
    return "Review Container"


def _parent_review_primary_name(batch: IngestBatch, metadata: dict) -> str:
    source_name = Path(batch.source_path or "").name
    return str(
        metadata.get("collection_title")
        or metadata.get("show_title")
        or metadata.get("artist")
        or metadata.get("albumartist")
        or metadata.get("author")
        or metadata.get("name")
        or source_name
        or "Review container"
    )


def _parent_review_secondary_name(parent_summary: dict) -> str:
    approved = int(parent_summary.get("approved_candidate_count") or 0)
    materialized = int(parent_summary.get("materialized_child_count") or 0)
    remaining = int(parent_summary.get("remaining_candidate_count") or 0)
    excluded = int(parent_summary.get("excluded_candidate_count") or 0)
    blocked = int(parent_summary.get("blocked_candidate_count") or 0)
    review_later = int(parent_summary.get("review_later_candidate_count") or 0)
    if parent_summary.get("parent_review_state") == "split_complete":
        child_count = materialized or approved
        return f"{_plural(child_count, 'child batch', 'child batches')} created, split complete"
    if parent_summary.get("parent_review_state") == "parent_partially_materialized":
        parts = [_plural(materialized, "child batch", "child batches") + " created"]
        if remaining:
            parts.append(f"{remaining} unresolved")
        if review_later:
            parts.append(_plural(review_later, "review later candidate"))
        if blocked:
            parts.append(_plural(blocked, "blocked candidate"))
        if excluded:
            parts.append(_plural(excluded, "excluded candidate"))
        return ", ".join(parts)
    parts = [
        _plural(approved, "approved candidate"),
        f"{remaining} remaining",
    ]
    if excluded:
        parts.append(_plural(excluded, "excluded candidate"))
    return ", ".join(parts)


def build_batch_display_fields(batch: IngestBatch, parent_summary: dict | None = None) -> dict:
    metadata = batch.metadata_json or {}
    detected_type = batch.detected_type
    if parent_summary and parent_summary.get("is_parent_review_container"):
        candidate_group_count = int(parent_summary.get("candidate_group_count") or 0)
        return {
            "media_category": "review",
            "media_label": _parent_review_media_label(detected_type),
            "primary_name": _parent_review_primary_name(batch, metadata),
            "secondary_name": _parent_review_secondary_name(parent_summary),
            "item_label": "candidate groups",
            "item_count": candidate_group_count,
            "edit_kind": None,
        }
    if detected_type == "music_discography":
        release_count = int(
            metadata.get("release_count")
            or metadata.get("album_count")
            or 0
        )
        return {
            "media_category": "music",
            "media_label": "Discography",
            "primary_name": (
                metadata.get("artist")
                or metadata.get("albumartist")
                or "Unknown Artist"
            ),
            "secondary_name": (
                f"{release_count} release discography"
                if release_count
                else "Discography"
            ),
            "item_label": "tracks",
            "item_count": int(metadata.get("track_count") or 0),
            "edit_kind": "music_discography",
        }

    if detected_type == "music_album":
        return {
            "media_category": "music",
            "media_label": "Music Album",
            "primary_name": (
                metadata.get("artist")
                or metadata.get("albumartist")
                or "Unknown Artist"
            ),
            "secondary_name": metadata.get("album") or "Unknown Album",
            "item_label": "tracks",
            "item_count": int(metadata.get("track_count") or 0),
            "edit_kind": "music_album",
        }

    if detected_type in MOVIE_TYPES:
        year = str(metadata.get("year") or "")[:4]
        return {
            "media_category": "movies",
            "media_label": "Movie",
            "primary_name": metadata.get("title") or "Unknown Movie",
            "secondary_name": f"{year} movie" if year else "Movie",
            "item_label": "videos",
            "item_count": int(metadata.get("video_file_count") or 0),
            "edit_kind": "movie",
        }

    if detected_type in TV_TYPES:
        season_count = int(metadata.get("season_count") or 0)
        episode_count = int(metadata.get("episode_count") or 0)
        special_count = int(metadata.get("special_episode_count") or 0)
        video_count = int(metadata.get("video_file_count") or 0)
        parts: list[str] = []
        if season_count:
            parts.append(f"{season_count} {'season' if season_count == 1 else 'seasons'}")
        if episode_count:
            parts.append(f"{episode_count} {'episode' if episode_count == 1 else 'episodes'}")
        if special_count:
            parts.append(f"{special_count} {'special' if special_count == 1 else 'specials'}")
        if video_count and video_count != episode_count:
            parts.append(f"{video_count} videos")
        if metadata.get("metadata_quality") == "weak":
            parts.append("needs episode review")
        return {
            "media_category": "tv",
            "media_label": "TV Show",
            "primary_name": metadata.get("show_title") or "Unknown TV Show",
            "secondary_name": " Ãƒâ€šÃ‚Â· ".join(parts),
            "item_label": "videos",
            "item_count": video_count or episode_count,
            "edit_kind": "tv_show",
        }

    if detected_type in BOOK_TYPES:
        items = metadata.get("book_items") or []
        if metadata.get("review_type") == "book_collection" or items:
            count = len([item for item in items if item.get("include", True)])
            return {
                "media_category": "books",
                "media_label": "Book Collection",
                "primary_name": metadata.get("collection_title") or "Book Collection",
                "secondary_name": f"{count} books" if count else "Book collection",
                "item_label": "book files",
                "item_count": int(metadata.get("book_file_count") or count or 0),
                "edit_kind": "book_collection",
            }
        year = str(metadata.get("year") or "")[:4]
        author = metadata.get("author") or "Unknown Author"
        return {
            "media_category": "books",
            "media_label": "Book",
            "primary_name": metadata.get("title") or "Unknown Title",
            "secondary_name": f"{author} Ãƒâ€šÃ‚Â· {year}" if year else author,
            "item_label": "book files",
            "item_count": int(metadata.get("book_file_count") or 0),
            "edit_kind": "book",
        }

    if detected_type in AUDIOBOOK_TYPES:
        author = metadata.get("author") or "Unknown Author"
        title = metadata.get("title") or "Unknown Title"
        year = str(metadata.get("year") or "")[:4]
        narrator = str(metadata.get("narrator") or "").strip()
        details = [title]
        if narrator:
            details.append(f"Narrated by {narrator}")
        if year:
            details.append(year)
        return {
            "media_category": "audiobooks",
            "media_label": "Audiobook",
            "primary_name": author,
            "secondary_name": " Ãƒâ€šÃ‚Â· ".join(details),
            "item_label": "audio files",
            "item_count": int(metadata.get("audiobook_file_count") or 0),
            "edit_kind": "audiobook",
        }

    if detected_type in QUARANTINE_TYPES:
        file_count = int(metadata.get("file_count") or 0)
        return {
            "media_category": "quarantine",
            "media_label": "Quarantine Review",
            "primary_name": metadata.get("name") or "Unknown item",
            "secondary_name": (
                f"{file_count} file(s)"
                if file_count
                else metadata.get("reason") or detected_type
            ),
            "item_label": "files",
            "item_count": file_count,
            "edit_kind": None,
        }

    return {
        "media_category": None,
        "media_label": detected_type.replace("_", " ").title(),
        "primary_name": metadata.get("name") or "Unknown item",
        "secondary_name": metadata.get("reason") or detected_type,
        "item_label": "items",
        "item_count": int(metadata.get("file_count") or 0),
        "edit_kind": None,
    }
