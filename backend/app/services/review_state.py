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
    "video_movie_collection": "movie_collection",
    "video_tv_show": "tv_show",
    "book": "book",
    "audiobook": "audiobook",
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
    "book_collection_duplicate_destination",
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
        artist = str(meta.get("artist") or meta.get("albumartist") or "").strip()
        album = str(meta.get("album") or "").strip()
        if (
            (not artist or artist.casefold() in {"unknown", "unknown artist", "unkn"})
            and not meta.get("accepted_unknown_album_artist")
        ):
            blocking.append(_item("artist_missing", "Artist is required before approval."))
        if (
            (not album or album.casefold() in {"unknown", "unknown album", "unkn"})
            and not meta.get("accepted_unknown_album_title")
        ):
            blocking.append(_item("album_missing", "Album title is required before approval."))
        year = str(meta.get("year") or meta.get("date") or "")[:4]
        if not year.isdigit():
            non_blocking.append(_item(
                "year_missing",
                "Year is missing. It may be accepted as unknown and reviewed later.",
            ))
    elif detected_type == "music_discography":
        artist = str(meta.get("artist") or "").strip()
        if (
            (not artist or artist.casefold() in {"unknown", "unknown artist", "unkn"})
            and not meta.get("accepted_unknown_discography_artist")
        ):
            blocking.append(_item("artist_missing", "Discography artist is required."))
        for album in meta.get("albums", []):
            if not isinstance(album, dict) or not album.get("include", True):
                continue
            source = str(album.get("source_folder") or "")
            if (
                not str(album.get("album") or "").strip()
                and not album.get("accepted_unknown_album_title")
            ):
                blocking.append(_item(
                    "album_missing_title",
                    "Included release is missing a title.",
                    source_folder=source,
                ))
            if not str(album.get("year") or "").strip():
                non_blocking.append(_item(
                    "album_missing_year",
                    "Included release is missing a year and may be reviewed later.",
                    source_folder=source,
                ))
    elif detected_type == "video_movie":
        # Determine resolved review_type — preserve movie_collection if set
        existing_review_type = str(meta.get("review_type") or "")
        has_movie_items = bool(meta.get("movie_items"))
        if existing_review_type == "movie_collection" or has_movie_items:
            resolved_review_type = "movie_collection"
        else:
            resolved_review_type = "movie"
        meta["review_type"] = resolved_review_type

        if resolved_review_type != "movie_collection":
            title = str(meta.get("title") or "").strip()
            if (
                (not title or title.casefold() in {"unknown", "unknown movie"})
                and not meta.get("accepted_unknown_title")
            ):
                blocking.append(_item("movie_title_missing", "Movie title is required."))
            year = str(meta.get("year") or "")
            if len(year) != 4 or not year.isdigit():
                non_blocking.append(_item(
                    "movie_year_missing",
                    "Movie year is missing and may be accepted as unknown.",
                ))
        video_file_count = int(meta.get("video_file_count") or 0)
        if video_file_count > 1:
            # If resolved as movie_collection, the ambiguity is resolved.
            if resolved_review_type == "movie_collection" and meta.get("movie_items"):
                pass  # resolved via collection review
            else:
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

        # If movie_items have been set by a movie collection review,
        # check each included item has title and year.
        included_count = 0
        for movie_item in meta.get("movie_items", []):
            if not isinstance(movie_item, dict):
                continue
            if not movie_item.get("include", True):
                continue
            included_count += 1
            source_file = str(movie_item.get("source_file") or "")
            title = str(movie_item.get("title") or "").strip()
            accepted_unknown_title = bool(
                movie_item.get("accepted_unknown_title")
            )
            accepted_unknown_year = bool(
                movie_item.get("accepted_unknown_year")
            )
            if (
                (not title or title.casefold() in {
                    "unknown",
                    "unknown movie",
                    "unknown title",
                })
                and not accepted_unknown_title
            ):
                blocking.append(_item(
                    "movie_collection_item_missing_title",
                    "Movie in collection is missing a title.",
                    file_name=source_file,
                ))
            elif not title and accepted_unknown_title:
                non_blocking.append(_item(
                    "movie_collection_item_unknown_title_accepted",
                    "Unknown movie title was explicitly accepted.",
                    file_name=source_file,
                ))
            raw_year = str(movie_item.get("year") or "")
            if len(raw_year) != 4 or not raw_year.isdigit():
                if accepted_unknown_year:
                    non_blocking.append(_item(
                        "movie_collection_item_unknown_year_accepted",
                        "Unknown movie year was explicitly accepted.",
                        file_name=source_file,
                    ))
                else:
                    blocking.append(_item(
                        "movie_collection_item_missing_year",
                        "Movie in collection is missing a year.",
                        file_name=source_file,
                    ))

        # At least one movie must be included
        if has_movie_items and included_count == 0:
            blocking.append(_item(
                "movie_collection_no_included_items",
                "At least one movie must be included before approval.",
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
    elif detected_type == "book":
        items = meta.get("book_items") or []
        collection = meta.get("review_type") == "book_collection" or bool(items)
        meta["review_type"] = "book_collection" if collection else "book"
        if collection:
            included = 0
            destinations: dict[str, str] = {}
            for item in items:
                if not isinstance(item, dict) or not item.get("include", True):
                    continue
                included += 1
                source = str(item.get("source_file") or "")
                if not str(item.get("title") or "").strip():
                    blocking.append(_item("book_item_missing_title", "Included book is missing a title.", file_name=source))
                if str(item.get("author") or "").strip().casefold() in {
                    "",
                    "unknown",
                    "unknown author",
                    "unkn",
                }:
                    if item.get("accepted_unknown_author", False):
                        non_blocking.append(_item(
                            "book_author_unknown_accepted",
                            "Book author is unknown but accepted for this review.",
                            file_name=source,
                        ))
                    else:
                        blocking.append(_item("book_item_missing_author", "Included book is missing an author.", file_name=source))
                if item.get("lookup_later", False):
                    non_blocking.append(_item(
                        "book_lookup_later",
                        "Book metadata is marked for later lookup.",
                        file_name=source,
                    ))
                raw_year = str(item.get("year") or "").strip()
                if raw_year and (len(raw_year) != 4 or not raw_year.isdigit()):
                    blocking.append(_item("book_item_invalid_year", "Book year must be four digits when provided.", file_name=source))
                destination = str(
                    item.get("destination_preview")
                    or item.get("destination_path")
                    or ""
                ).strip()
                if destination:
                    destination_key = destination.replace("\\", "/").casefold()
                    existing_source = destinations.get(destination_key)
                    if existing_source:
                        blocking.append(_item(
                            "book_collection_duplicate_destination",
                            "Two included books resolve to the same destination.",
                            destination=destination.replace("\\", "/"),
                            file_name=source,
                            other_file_name=existing_source,
                        ))
                    else:
                        destinations[destination_key] = source
            if items and included == 0:
                blocking.append(_item("book_collection_no_included_items", "At least one book must be included before approval."))
        else:
            if str(meta.get("title") or "").strip().casefold() in {"", "unknown title"}:
                blocking.append(_item("book_title_missing", "Book title is required before approval."))
            if str(meta.get("author") or "").strip().casefold() in {"", "unknown author"}:
                blocking.append(_item("book_author_missing", "Book author is required before approval."))
            raw_year = str(meta.get("year") or "").strip()
            if raw_year and (len(raw_year) != 4 or not raw_year.isdigit()):
                blocking.append(_item("book_year_invalid", "Book year must be four digits when provided."))
            if not raw_year:
                non_blocking.append(_item("book_year_missing", "Book year is missing; destination will use Unknown Year."))
    elif detected_type == "audiobook":
        meta["review_type"] = "audiobook"
        meta["review_mode"] = "single_item"
        author = str(meta.get("author") or "").strip().casefold()
        title = str(meta.get("title") or "").strip().casefold()
        raw_year = str(meta.get("year") or "").strip()
        if author in {"", "unknown author", "unknown", "unkn"}:
            if meta.get("accepted_unknown_author", False):
                non_blocking.append(_item(
                    "audiobook_author_unknown_accepted",
                    "Audiobook author is unknown but accepted for this review.",
                ))
            else:
                blocking.append(_item(
                    "audiobook_author_missing",
                    "Audiobook author is required before approval.",
                ))
        if title in {"", "unknown title", "unknown", "unkn"}:
            blocking.append(_item(
                "audiobook_title_missing",
                "Audiobook title is required before approval.",
            ))
        year_unknown = raw_year.casefold() in {
            "",
            "unknown",
            "unknown year",
            "unkn",
        }
        if (
            raw_year
            and not year_unknown
            and (len(raw_year) != 4 or not raw_year.isdigit())
        ):
            blocking.append(_item(
                "audiobook_year_invalid",
                "Audiobook year must be four digits when provided.",
            ))
        if year_unknown:
            non_blocking.append(_item(
                (
                    "audiobook_year_unknown_accepted"
                    if meta.get("accepted_unknown_year", False)
                    else "audiobook_year_missing"
                ),
                (
                    "Audiobook year is unknown but accepted for this review."
                    if meta.get("accepted_unknown_year", False)
                    else "Audiobook year is missing; destination will use Unknown Year."
                ),
            ))
        if str(meta.get("narrator") or "").strip().casefold() in {
            "",
            "unknown",
            "unknown narrator",
            "unkn",
        }:
            non_blocking.append(_item(
                (
                    "audiobook_narrator_unknown_accepted"
                    if meta.get("accepted_unknown_narrator", False)
                    else "audiobook_narrator_missing"
                ),
                (
                    "Narrator is unknown but accepted for this review."
                    if meta.get("accepted_unknown_narrator", False)
                    else "Narrator is missing."
                ),
            ))
        if meta.get("lookup_later", False):
            non_blocking.append(_item(
                "audiobook_lookup_later",
                "Audiobook metadata is marked for later lookup.",
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
    elif (
        detected_type in {"book", "audiobook"}
        and (
            meta.get("accepted_unknown_author", False)
            or meta.get("accepted_unknown_year", False)
            or meta.get("accepted_unknown_narrator", False)
            or any(
                isinstance(item, dict)
                and (
                    item.get("accepted_unknown_author", False)
                    or item.get("accepted_unknown_year", False)
                )
                for item in (meta.get("book_items") or [])
            )
        )
    ):
        quality = "accepted_with_unknowns"
    elif quality in {"weak", "broken", "unsupported"} and confirmed:
        quality = "fair"

    # Cap confidence while blockers exist
    if blocking:
        existing_confidence = float(meta.get("confidence") or 0.5)
        if existing_confidence > 0.8:
            meta["confidence"] = 0.75

    # Determine review_mode
    if detected_type == "video_tv_show":
        review_mode = "guided_episode_review"
    elif detected_type in {"music_discography"}:
        review_mode = "item_list"
    elif detected_type == "video_movie" and meta.get("review_type") == "movie_collection":
        review_mode = "item_list"
    elif detected_type == "book" and meta.get("review_type") == "book_collection":
        review_mode = "item_list"
    elif detected_type in {"unknown_type", "unsupported_file"}:
        review_mode = "quarantine_review"
    else:
        review_mode = "single_item"

    meta.update({
        "metadata_quality": quality,
        "metadata_warnings": warnings,
        "blocking_review_items": blocking,
        "non_blocking_review_items": non_blocking,
        "review_confirmed": confirmed,
        "review_type": meta.get("review_type") or REVIEW_TYPES.get(detected_type, detected_type),
        "review_mode": review_mode,
    })
    return meta


def has_blocking_review_items(detected_type: str, metadata: dict | None) -> bool:
    return bool(build_review_state(detected_type, metadata)["blocking_review_items"])
