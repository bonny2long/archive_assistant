from collections import Counter
from typing import Any

from app.services.video_metadata import parse_movie_name


def _all_same_movie(video_files: list) -> bool:
    titles: set[str] = set()
    for filename in video_files:
        if not isinstance(filename, str):
            return False
        parsed = parse_movie_name(filename)
        title = str(parsed.get("title") or "").strip().casefold()
        if title and title not in ("unknown movie",):
            titles.add(title)
    return len(titles) == 1


REVIEW_TYPES = {
    "music_album": "music_album",
    "music_discography": "music_discography",
    "video_movie": "movie",
    "video_tv_show": "tv_show",
    "unknown_type": "quarantine",
    "unsupported_file": "quarantine",
}

BLOCKING_WARNING_TYPES = {
    "possible_duplicate_destination",
    "possible_artist_alias",
    "possible_archived_duplicate_candidate",
    "destination_file_conflict",
    "child_album_metadata_missing",
    "discography_destination_exists",
    "movie_destination_exists",
    "tv_destination_exists",
    "partial_duplicate_tracks_detected",
    "tv_review_file_sync_unmatched",
    "tv_review_count_mismatch",
    "tv_file_metadata_not_ready",
}


def _item(item_type: str, message: str, **details: Any) -> dict:
    return {"type": item_type, "message": message, **details}


def build_review_state(detected_type: str, metadata: dict | None) -> dict:
    meta = dict(metadata or {})
    warnings = list(dict.fromkeys(meta.get("metadata_warnings", [])))
    blocking: list[dict] = []
    non_blocking: list[dict] = []

    for warning in warnings:
        target = blocking if warning in BLOCKING_WARNING_TYPES else non_blocking
        if warning == "tv_review_file_sync_unmatched":
            unmatched = meta.get("tv_review_file_sync_unmatched") or []
            if unmatched:
                target.append(_item(
                    "tv_review_file_sync_unmatched",
                    "Some reviewed TV episodes could not be matched back to source files. Move is blocked until review metadata and file metadata are synced.",
                    files=unmatched,
                    count=len(unmatched),
                ))
            else:
                target.append(_item(
                    "tv_review_file_sync_unmatched",
                    "Some reviewed TV episodes could not be matched back to source files.",
                ))
        elif warning == "tv_review_count_mismatch":
            detail = meta.get("tv_review_count_mismatch")
            target.append(_item(
                warning,
                "Episode count mismatch between batch and files. Batch-level and file-level counts must match before moving.",
                detail=detail,
            ) if detail else _item(
                warning,
                "Episode count mismatch between batch and files.",
            ))
        elif warning == "tv_file_metadata_not_ready":
            detail = meta.get("tv_file_metadata_not_ready")
            target.append(_item(
                warning,
                "Some TV file metadata is not ready for moving. Review each file's season, episode, and code fields.",
                detail=detail,
            ) if detail else _item(
                warning,
                "Some TV file metadata is not ready for moving.",
            ))
        else:
            target.append(_item(warning, warning.replace("_", " ").capitalize()))

    if detected_type == "music_album":
        if not str(meta.get("artist") or meta.get("albumartist") or "").strip():
            blocking.append(_item("artist_missing", "Artist is required before approval."))
        if not str(meta.get("album") or "").strip():
            blocking.append(_item("album_missing", "Album title is required before approval."))
        if not str(meta.get("year") or meta.get("date") or "")[:4].isdigit():
            blocking.append(_item("year_missing", "A four-digit year is required before approval."))
    elif detected_type == "music_discography":
        if not str(meta.get("artist") or "").strip():
            blocking.append(_item("artist_missing", "Discography artist is required."))
        for album in meta.get("albums", []):
            if not isinstance(album, dict) or not album.get("include", True):
                continue
            source = str(album.get("source_folder") or "")
            if not str(album.get("album") or "").strip():
                blocking.append(_item(
                    "album_missing_title",
                    "Included release is missing a title.",
                    source_folder=source,
                ))
            if not str(album.get("year") or "").strip():
                blocking.append(_item(
                    "album_missing_year",
                    "Included release is missing a year.",
                    source_folder=source,
                ))
    elif detected_type == "video_movie":
        if not str(meta.get("title") or "").strip():
            blocking.append(_item("movie_title_missing", "Movie title is required."))
        year = str(meta.get("year") or "")
        if len(year) != 4 or not year.isdigit():
            blocking.append(_item("movie_year_missing", "A four-digit movie year is required."))
        video_file_count = int(meta.get("video_file_count") or 0)
        if video_file_count > 1:
            video_files = meta.get("video_files") or []
            if _all_same_movie(video_files):
                non_blocking.append(_item(
                    "multiple_movie_editions",
                    f"{video_file_count} video files detected — looks like multiple editions or versions of the same movie.",
                ))
            else:
                blocking.append(_item(
                    "multiple_movie_candidates",
                    f"{video_file_count} video files found. Could not determine if they are editions, duplicates, or unrelated files.",
                ))
    elif detected_type == "video_tv_show":
        if not str(meta.get("show_title") or "").strip():
            blocking.append(_item("tv_show_title_missing", "TV show title is required."))
        episodes = [
            episode
            for season in meta.get("seasons", [])
            if isinstance(season, dict)
            for episode in season.get("episodes", [])
            if isinstance(episode, dict)
        ]
        if not episodes:
            blocking.append(_item("no_parseable_episodes", "No parseable TV episodes were found."))

        included_codes: list[str] = []
        for episode in episodes:
            source_file = episode.get("source_file")
            include = episode.get("include", True)

            # Excluded episodes: skip all checks
            if not include:
                continue

            is_special = bool(episode.get("is_special"))
            preserve = bool(episode.get("preserve_source_filename"))
            special_label = str(episode.get("special_label") or "").strip()

            season_number = episode.get("season_number")
            episode_number = episode.get("episode_number")

            if season_number is None:
                # Specials with a destination_group don't need a normal season number
                dest_group = episode.get("destination_group")
                if not (is_special and dest_group in {"specials", "oad", "extras"}):
                    blocking.append(_item(
                        "missing_season_number",
                        "Episode is missing a season number.",
                        file_name=source_file,
                    ))

            if episode_number is None:
                # Specials with a label satisfy the episode number requirement
                if is_special and special_label:
                    pass  # resolved via special_label
                elif preserve:
                    pass  # will use source filename, no code needed
                else:
                    blocking.append(_item(
                        "missing_episode_number",
                        "Episode is missing an episode number.",
                        file_name=source_file,
                    ))

            if not str(episode.get("episode_title") or "").strip():
                if not preserve:
                    non_blocking.append(_item(
                        "missing_episode_title",
                        "Episode title is missing; the source filename will be preserved.",
                        file_name=source_file,
                    ))

            code = episode.get("episode_code")
            if code:
                included_codes.append(str(code))

        for code, count in Counter(included_codes).items():
            if count > 1:
                blocking.append(_item(
                    "duplicate_episode_code",
                    f"Episode code {code} appears more than once.",
                    episode_code=code,
                ))

        # Unresolved video files — each is a blocking item with no safe destination
        for unresolved in meta.get("unresolved_video_files", []):
            source_file = unresolved.get("source_file")
            blocking.append(_item(
                "unresolved_video_file",
                "Unresolved video file needs a classification before approval.",
                file_name=source_file,
            ))

        # Special episodes — check for missing labels and duplicate labels
        special_labels_seen: dict[str, list[str]] = {}
        for special in meta.get("special_episodes", []):
            source_file = special.get("source_file")
            special_label = str(special.get("special_label") or "").strip()
            dest_group = str(special.get("destination_group") or "specials").strip()

            if not special_label:
                blocking.append(_item(
                    "missing_special_label",
                    "Special/OVA episode is missing a label.",
                    file_name=source_file,
                ))

            label_key = f"{dest_group}:{special_label}"
            if special_label:
                special_labels_seen.setdefault(label_key, [])
                special_labels_seen[label_key].append(
                    source_file or "unknown"
                )

        for label_key, sources in special_labels_seen.items():
            if len(sources) > 1:
                dest_group, special_label = label_key.split(":", 1)
                blocking.append(_item(
                    "duplicate_special_label",
                    f"Duplicate special label '{special_label}' in '{dest_group}' group.",
                    special_label=special_label,
                    file_name=sources[0],
                ))
    elif detected_type in {"unknown_type", "unsupported_file"}:
        blocking.append(_item(
            "quarantine_review_required",
            "Unknown and unsupported items require quarantine review.",
        ))

    def unique(items: list[dict]) -> list[dict]:
        seen = set()
        result = []
        for value in items:
            key = (
                value.get("type"),
                value.get("file_name"),
                value.get("source_folder"),
                value.get("episode_code"),
            )
            if key not in seen:
                seen.add(key)
                result.append(value)
        return result

    blocking = unique(blocking)
    non_blocking = unique(non_blocking)
    confirmed = bool(meta.get("review_confirmed", False))
    quality = str(meta.get("metadata_quality") or "weak")
    if blocking:
        quality = "broken" if quality == "broken" else "weak"
    elif quality in {"weak", "broken", "unsupported"} and confirmed:
        quality = "fair"

    meta.update({
        "metadata_quality": quality,
        "metadata_warnings": warnings,
        "blocking_review_items": blocking,
        "non_blocking_review_items": non_blocking,
        "review_confirmed": confirmed,
        "review_type": REVIEW_TYPES.get(detected_type, detected_type),
    })
    return meta


def has_blocking_review_items(detected_type: str, metadata: dict | None) -> bool:
    return bool(build_review_state(detected_type, metadata)["blocking_review_items"])
