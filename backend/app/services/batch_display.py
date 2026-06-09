from app.models.archive import IngestBatch


MUSIC_TYPES = {"music_album", "music_discography"}
MOVIE_TYPES = {"video_movie"}
TV_TYPES = {"video_tv_show", "video_tv_episode"}
BOOK_TYPES = {"book_epub", "book_pdf"}
AUDIOBOOK_TYPES = {"audiobook"}
QUARANTINE_TYPES = {"unknown_type", "unsupported_file"}


def build_batch_display_fields(batch: IngestBatch) -> dict:
    metadata = batch.metadata_json or {}
    detected_type = batch.detected_type

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
        season_label = "season" if season_count == 1 else "seasons"
        episode_label = "episode" if episode_count == 1 else "episodes"
        return {
            "media_category": "tv",
            "media_label": "TV Show",
            "primary_name": metadata.get("show_title") or "Unknown TV Show",
            "secondary_name": (
                f"{season_count} {season_label} · "
                f"{episode_count} {episode_label}"
            ),
            "item_label": "episodes",
            "item_count": episode_count,
            "edit_kind": "tv_show",
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
