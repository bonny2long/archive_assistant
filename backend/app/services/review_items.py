"""
review_items.py

Builds normalized review_items lists for each media type.
These supplement (never replace) media-specific metadata.
Used by batch_display and the new movie collection review flow.
"""
from pathlib import Path


def build_review_items_for_music_album(metadata: dict) -> list[dict]:
    """Single-item list describing the album being reviewed."""
    artist = str(metadata.get("artist") or metadata.get("albumartist") or "").strip()
    album = str(metadata.get("album") or "").strip()
    year = str(metadata.get("year") or metadata.get("date") or "")[:4]
    fmt = str(metadata.get("format") or "").strip()
    track_count = int(metadata.get("track_count") or 0)
    disc_count = int(metadata.get("disc_count") or 1)
    artwork_count = int(metadata.get("artwork_count") or 0)
    dest = str(metadata.get("suggested_destination") or "").strip()

    return [
        {
            "item_kind": "album",
            "source_key": "album",
            "include": True,
            "title": album or None,
            "artist": artist or None,
            "year": year or None,
            "format": fmt or None,
            "track_count": track_count,
            "disc_count": disc_count,
            "artwork_count": artwork_count,
            "destination_preview": dest or None,
        }
    ]


def build_review_items_for_discography(metadata: dict) -> list[dict]:
    """One item per release in the discography."""
    artist = str(metadata.get("artist") or "").strip()
    items = []
    for album in metadata.get("albums", []):
        if not isinstance(album, dict):
            continue
        source_folder = str(album.get("source_folder") or "").strip()
        release_year = str(album.get("year") or "").strip()
        title = str(album.get("album") or "").strip()
        release_type = str(album.get("release_type") or "album").strip()
        include = bool(album.get("include", True))
        track_count = int(album.get("track_count") or 0)
        artwork_count = int(album.get("artwork_count") or 0)
        dest = str(album.get("destination_preview") or "").strip()

        items.append(
            {
                "item_kind": "release",
                "source_key": source_folder,
                "include": include,
                "artist": artist or None,
                "title": title or None,
                "year": release_year or None,
                "release_type": release_type,
                "track_count": track_count,
                "artwork_count": artwork_count,
                "destination_preview": dest or None,
            }
        )
    return items


def build_review_items_for_single_movie(metadata: dict) -> list[dict]:
    """Single-item list for a single movie batch."""
    title = str(metadata.get("title") or "").strip()
    year = str(metadata.get("year") or "")[:4]
    edition = str(metadata.get("edition") or "").strip()
    fmt = str(metadata.get("format") or "").strip()
    primary_file = str(metadata.get("primary_video_file") or "").strip()
    dest = str(metadata.get("suggested_destination") or "").strip()

    return [
        {
            "item_kind": "movie",
            "source_key": primary_file or "video",
            "include": True,
            "title": title or None,
            "year": year or None,
            "edition": edition or None,
            "format": fmt or None,
            "destination_preview": dest or None,
        }
    ]


def build_review_items_for_movie_collection(
    metadata: dict,
    files: list,
) -> list[dict]:
    """
    One item per video file in a multi-video movie batch.

    If movie_items already exist in metadata (set by a prior review save),
    use those as the canonical source of truth and just fill in any
    new files that are not yet represented.

    Files argument: list of IngestFile ORM objects.
    """
    from app.services.video_metadata import (
        VIDEO_EXTENSIONS,
        parse_movie_name,
        safe_movie_path_part,
    )

    existing_items: dict[str, dict] = {}
    for item in metadata.get("movie_items", []):
        if isinstance(item, dict) and item.get("source_file"):
            key = str(item["source_file"]).casefold()
            existing_items[key] = item

    video_files = [
        f for f in files
        if Path(f.file_name).suffix.lower() in VIDEO_EXTENSIONS
    ]

    items = []
    for vf in video_files:
        key = str(vf.file_name).casefold()
        if key in existing_items:
            item = dict(existing_items[key])
        else:
            parsed = parse_movie_name(vf.file_name)
            title = str(parsed.get("title") or "").strip()
            year = str(parsed.get("year") or "")[:4]
            edition = str(parsed.get("edition") or "").strip()
            fmt = str(parsed.get("format") or "").strip().upper()

            dest_part = (
                f"{year or 'Unknown Year'} - {title or 'Unknown Title'}"
                if not edition
                else f"{year or 'Unknown Year'} - {title or 'Unknown Title'} [{edition}]"
            )
            dest = f"Movies/Library/{safe_movie_path_part(dest_part)}"

            item = {
                "item_kind": "movie",
                "source_key": vf.file_name,
                "source_file": vf.file_name,
                "include": True,
                "title": title or None,
                "year": year or None,
                "edition": edition or None,
                "format": fmt or None,
                "destination_preview": dest,
            }
        items.append(item)
    return items


def build_review_items_for_batch(batch) -> list[dict]:
    """
    Entry point: build normalized review_items for any batch.
    Returns an empty list for unsupported types rather than raising.
    """
    detected_type = str(batch.detected_type or "")
    metadata = dict(batch.metadata_json or {})

    if detected_type == "music_album":
        return build_review_items_for_music_album(metadata)
    if detected_type == "music_discography":
        return build_review_items_for_discography(metadata)
    if detected_type == "video_movie":
        review_type = str(metadata.get("review_type") or "")
        if review_type == "movie_collection" or metadata.get("movie_items"):
            return build_review_items_for_movie_collection(metadata, batch.files)
        return build_review_items_for_single_movie(metadata)
    return []
