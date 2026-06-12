from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
import re

from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.archive import IngestBatch, IngestFile
from app.services.checksum import file_sha256
from app.services.music_metadata import (
    album_group_key,
    build_suggested_metadata,
    canonical_artist_key,
    clean_compilation_artist,
    compilation_artist_cleanup_from_folder,
    common_album_artist,
    common_track_artist,
    evaluate_music_album_metadata,
    extract_music_metadata,
    has_mixed_track_artists,
    is_audio_file,
    is_artwork_file,
    is_compilation_artist,
    metadata_mismatch_warnings,
    music_folder_release_tags,
    normalize_key,
    looks_like_discography_parent,
    parse_discography_parent_folder,
    parse_music_folder_name,
    sort_music_tracks,
    suggest_music_destination,
    UNKNOWN_VALUES,
)
from app.services.report_writer import write_json_report
from app.services.video_metadata import (
    is_ignored_video_sidecar,
    is_movie_artwork,
    is_subtitle_file,
    is_video_file,
    folder_looks_like_tv_show,
    looks_like_tv,
    looks_like_tv_episode,
    normalize_tv_counts,
    parse_movie_name,
    parse_tv_folder_name,
    parse_tv_episode_name,
    safe_movie_path_part,
    safe_tv_path_part,
    tv_artwork_scope,
    tv_subtitle_language_suffix,
    useful_movie_name,
)
from app.services.review_state import build_review_state
from app.services.metadata_candidates import (
    METADATA_ASSIST_VERSION,
    preferred_candidate_value,
)
from app.services.title_display import clean_display_title, destination_title
from app.services.book_metadata import (
    book_format_for,
    build_book_metadata_candidates,
    build_book_collection_groups,
    build_book_item_destination,
    build_single_book_metadata,
    collect_book_files,
    is_book_file,
    parse_book_name,
)
from app.services.audiobook_metadata import (
    build_audiobook_metadata,
    collect_audiobook_files,
    has_explicit_audiobook_signal,
    is_audiobook_audio_file,
    looks_like_generic_multidisc_audiobook_source,
    looks_like_audiobook_source,
)


@dataclass(frozen=True)
class ScanMusicResult:
    created: int
    skipped_duplicates: int
    batches: list[IngestBatch]
    music_albums_found: int = 0
    discographies_found: int = 0
    unknown_items: int = 0
    unsupported_files: int = 0
    ignored_system_files: int = 0
    artwork_files_found: int = 0
    movie_batches_found: int = 0
    tv_shows_found: int = 0
    tv_episodes_found: int = 0
    subtitle_files_found: int = 0
    book_batches_found: int = 0
    book_files_found: int = 0
    audiobook_batches_found: int = 0
    audiobook_files_found: int = 0


IGNORED_INGEST_NAMES = {
    "_checks",
    "_reports",
    "_staging",
    "_quarantine",
    "music",
    "library",
    "metadata",
    "docs",
    "frontend",
    "backend",
    "scripts",
    ".git",
    "__pycache__",
    "node_modules",
    ".venv",
    ".ds_store",
    "thumbs.db",
    "desktop.ini",
    "__macosx",
}

RECOGNIZED_MEDIA_TYPES = {
    "music_album",
    "music_discography",
    "video_movie",
    "video_tv_show",
    "book",
    "audiobook",
}

QUARANTINE_TYPES = {"unknown_type", "unsupported_file"}

ACTIVE_REVIEW_STATUSES = {
    "needs_quarantine_review",
    "quarantined",
    "needs_metadata_review",
    "pending_review",
    "approved",
}


def _all_files(path: Path) -> list[Path]:
    if path.is_file():
        return [path]
    if path.is_dir():
        return sorted(
            candidate
            for candidate in path.rglob("*")
            if candidate.is_file()
        )
    return []


def _has_supported_audio_or_video(path: Path) -> bool:
    return any(
        is_audio_file(candidate) or is_video_file(candidate)
        for candidate in _all_files(path)
    )


def _has_any_real_files(path: Path) -> bool:
    return bool(_all_files(path))


def _is_empty_source_leftover(path: Path) -> bool:
    """Return True only when a source directory contains no files."""
    return path.is_dir() and not _has_any_real_files(path)


def classify_ingest_item(path: Path) -> str:
    if path.name.casefold() in IGNORED_INGEST_NAMES:
        return "ignored_system_folder"
    if path.is_file():
        if is_audiobook_audio_file(path) and looks_like_audiobook_source(path):
            return "audiobook"
        if is_audio_file(path):
            return "music_album"
        if is_video_file(path):
            return "video_movie"
        if is_book_file(path):
            return "book"
        return "unsupported_file"
    if not path.is_dir():
        return "unknown_type"

    audio_files = [
        candidate
        for candidate in path.rglob("*")
        if candidate.is_file() and is_audio_file(candidate)
    ]
    video_files = [
        candidate
        for candidate in path.rglob("*")
        if candidate.is_file() and is_video_file(candidate)
    ]
    book_files = [
        candidate
        for candidate in path.rglob("*")
        if candidate.is_file() and is_book_file(candidate)
    ]
    if video_files and not audio_files:
        if folder_looks_like_tv_show(path, video_files):
            return "video_tv_show"
        if len(video_files) >= 1:
            return "video_movie"
        return "unknown_type"
    if book_files and not audio_files and not video_files:
        return "book"
    if not audio_files:
        return "unknown_type"

    child_audio_folders = [
        child
        for child in path.iterdir()
        if child.is_dir()
        and any(
            candidate.is_file() and is_audio_file(candidate)
            for candidate in child.rglob("*")
        )
    ]
    if audio_files and not video_files:
        if has_explicit_audiobook_signal(path):
            return "audiobook"
        if looks_like_generic_multidisc_audiobook_source(path):
            return "audiobook"
    if looks_like_discography_parent(
        path,
        child_audio_folders,
        {str(child): [] for child in child_audio_folders},
    ):
        return "music_discography"
    if audio_files and not video_files and looks_like_audiobook_source(path):
        return "audiobook"
    return "music_album"


def _root_music_audio_files() -> list[Path]:
    audio_files = []
    for item in sorted(settings.ingest_root.iterdir()):
        classification = classify_ingest_item(item)
        if classification not in {"music_album", "music_discography"}:
            continue
        if item.is_file():
            audio_files.append(item)
        else:
            audio_files.extend(
                path
                for path in item.rglob("*")
                if path.is_file() and is_audio_file(path)
            )
    return audio_files


def _artwork_files(root: Path) -> list[Path]:
    if not root.is_dir():
        return []
    return sorted(
        path for path in root.rglob("*")
        if path.is_file() and is_artwork_file(path)
    )


def _ignored_music_sidecars(root: Path) -> list[Path]:
    if not root.is_dir():
        return []
    return sorted(
        path
        for path in root.rglob("*")
        if path.is_file()
        and not is_audio_file(path)
        and not is_artwork_file(path)
        and path.name.casefold() not in IGNORED_INGEST_NAMES
    )


def _movie_files(root: Path) -> dict[str, list[Path]]:
    candidates = [root] if root.is_file() else [
        path for path in root.rglob("*") if path.is_file()
    ]
    video = sorted(path for path in candidates if is_video_file(path))
    artwork = sorted(path for path in candidates if is_movie_artwork(path))
    subtitles = sorted(path for path in candidates if is_subtitle_file(path))
    ignored = sorted(path for path in candidates if is_ignored_video_sidecar(path))
    recognized = {
        path.resolve()
        for path in [*video, *artwork, *subtitles, *ignored]
    }
    return {
        "video": video,
        "artwork": artwork,
        "subtitles": subtitles,
        "ignored": ignored,
        "other": sorted(
            path
            for path in candidates
            if path.resolve() not in recognized
        ),
    }


def _tv_files(root: Path) -> dict[str, list[Path]]:
    candidates = [
        path for path in root.rglob("*")
        if path.is_file()
    ]
    all_video = sorted(path for path in candidates if is_video_file(path))
    # Zero-byte video files are test/stub/corrupt artifacts. They must not become
    # TV episodes, must not inflate counts, and must not create duplicate blockers.
    video = [path for path in all_video if path.stat().st_size > 0]
    zero_byte_video = [path for path in all_video if path.stat().st_size == 0]
    artwork = sorted(path for path in candidates if is_movie_artwork(path))
    subtitles = sorted(path for path in candidates if is_subtitle_file(path))
    ignored = sorted(path for path in candidates if is_ignored_video_sidecar(path))
    recognized = {
        path.resolve()
        for path in [*all_video, *artwork, *subtitles, *ignored]
    }
    return {
        "video": video,
        "zero_byte_video": zero_byte_video,
        "artwork": artwork,
        "subtitles": subtitles,
        "ignored": ignored,
        "other": sorted(
            path for path in candidates
            if path.resolve() not in recognized
        ),
    }


def _season_number_from_path(path: Path, root: Path) -> int | None:
    for parent in [path.parent, *path.parents]:
        if parent == root.parent:
            break
        parsed = parse_tv_episode_name(parent.name)
        if parsed["season_number"] is not None:
            return int(parsed["season_number"])
        if parent == root:
            break
    return None


def _clean_tv_show_folder_name(value: str) -> str:
    return str(parse_tv_folder_name(value).get("show_title") or "")


def _tv_episode_metadata(path: Path, root: Path) -> dict:
    parsed = parse_tv_episode_name(path.name)
    if parsed["season_number"] is None:
        parsed["season_number"] = _season_number_from_path(path, root)
    if (
        parsed["season_number"] is not None
        and parsed["episode_number"] is not None
    ):
        parsed["episode_code"] = (
            f"S{int(parsed['season_number']):02d}"
            f"E{int(parsed['episode_number']):02d}"
        )
    parsed["source_file"] = path.name
    parsed["relative_source"] = str(path.relative_to(root))
    return parsed


def _tv_subtitle_metadata(
    path: Path,
    root: Path,
    episodes: list[tuple[Path, dict]],
) -> dict:
    parsed = _tv_episode_metadata(path, root)
    matched_path = None
    matched_episode = None
    for episode_path, episode in episodes:
        same_stem = path.stem.casefold() == episode_path.stem.casefold()
        same_code = (
            parsed.get("episode_code")
            and parsed.get("episode_code") == episode.get("episode_code")
        )
        if same_stem or same_code:
            matched_path = episode_path
            matched_episode = episode
            if same_stem:
                break

    if matched_episode:
        parsed.update({
            "show_title": matched_episode.get("show_title"),
            "season_number": matched_episode.get("season_number"),
            "episode_number": matched_episode.get("episode_number"),
            "episode_code": matched_episode.get("episode_code"),
            "episode_title": matched_episode.get("episode_title"),
            "matched_episode_file": matched_path.name if matched_path else None,
            "language_suffix": tv_subtitle_language_suffix(
                path,
                matched_path,
            ),
            "unmatched_subtitle": False,
        })
    else:
        parsed["language_suffix"] = tv_subtitle_language_suffix(path)
        parsed["unmatched_subtitle"] = True
    return parsed


def _tv_artwork_metadata(
    path: Path,
    root: Path,
    only_season_number: int | None,
) -> dict:
    metadata = tv_artwork_scope(path, root)
    if (
        metadata.get("artwork_scope") == "season"
        and metadata.get("season_number") is None
    ):
        metadata["season_number"] = only_season_number
    return metadata


def _tv_batch_data(source: Path) -> dict | None:
    files = _tv_files(source)
    if not files["video"]:
        return None

    all_episode_rows = [
        (path, _tv_episode_metadata(path, source))
        for path in files["video"]
    ]

    # Categorize: normal episodes, special episodes, unresolved files
    normal_rows: list[tuple[Path, dict]] = []
    special_rows: list[tuple[Path, dict]] = []
    unresolved_rows: list[tuple[Path, dict]] = []
    for path, metadata in all_episode_rows:
        if metadata.get("is_special"):
            special_rows.append((path, metadata))
        elif (
            metadata.get("season_number") is not None
            and metadata.get("episode_number") is not None
            and metadata.get("episode_code") is not None
        ):
            normal_rows.append((path, metadata))
        else:
            unresolved_rows.append((path, metadata))

    episodes = [metadata for _, metadata in normal_rows]
    # Subtitles still matched against all rows (including specials/unresolved)
    subtitles = [
        _tv_subtitle_metadata(path, source, all_episode_rows)
        for path in files["subtitles"]
    ]

    # TV warning details — per-file information for actionable warnings
    unparsed_video_files = [
        {
            "source_file": metadata["source_file"],
            "relative_source": metadata.get("relative_source"),
            "raw_name": metadata["raw_name"],
        }
        for _, metadata in unresolved_rows
    ]
    generic_title_files = [
        {
            "source_file": metadata["source_file"],
            "relative_source": metadata.get("relative_source"),
        }
        for _, metadata in all_episode_rows
        if not metadata.get("episode_title")
    ]

    # Special episodes list
    special_episodes = [metadata for _, metadata in special_rows]
    # Unresolved files list
    unresolved_files = [
        {
            "source_file": metadata["source_file"],
            "relative_source": metadata.get("relative_source"),
            "raw_name": metadata["raw_name"],
            "show_title": metadata.get("show_title"),
        }
        for _, metadata in unresolved_rows
    ]

    parsed_titles = [
        str(episode["show_title"]).strip()
        for episode in episodes
        if episode.get("show_title")
    ]
    folder_metadata = parse_tv_folder_name(source.name)
    folder_title = str(folder_metadata.get("show_title") or "")
    show_title = (
        Counter(parsed_titles).most_common(1)[0][0]
        if parsed_titles
        else folder_title
    )
    warnings = []
    if not parsed_titles:
        warnings.append("tv_show_title_from_folder")
    if not show_title:
        show_title = "Unknown TV Show"
        warnings.append("tv_show_title_missing")

    parse_failed = any(
        episode.get("season_number") is None
        or episode.get("episode_number") is None
        or not episode.get("episode_code")
        for episode in episodes
    )
    if parse_failed:
        warnings.append("tv_episode_parse_failed")
    if unresolved_rows:
        warnings.append("tv_episode_parse_failed")
    folder_only_title = not parsed_titles
    if folder_only_title:
        warnings.append("tv_metadata_review_required")
    if any(not episode.get("episode_title") for episode in episodes):
        warnings.append("tv_episode_titles_missing")
    if any(subtitle.get("unmatched_subtitle") for subtitle in subtitles):
        warnings.append("tv_unmatched_subtitle")
    zero_byte_videos = files.get("zero_byte_video", [])
    if zero_byte_videos:
        warnings.append("zero_byte_video_files_ignored")

    subtitle_counts = Counter(
        subtitle.get("episode_code")
        for subtitle in subtitles
        if subtitle.get("episode_code")
    )
    for episode in episodes:
        episode["subtitle_count"] = subtitle_counts.get(
            episode.get("episode_code"),
            0,
        )

    seasons_by_number: dict[int, list[dict]] = defaultdict(list)
    for episode in episodes:
        if episode.get("season_number") is not None:
            seasons_by_number[int(episode["season_number"])].append(episode)
    seasons = [
        {
            "season_number": season_number,
            "episode_count": len(season_episodes),
            "episodes": sorted(
                season_episodes,
                key=lambda item: int(item.get("episode_number") or 0),
            ),
        }
        for season_number, season_episodes in sorted(seasons_by_number.items())
    ]
    year_values = [
        episode.get("year")
        for episode in episodes
        if episode.get("year")
    ]
    year = (
        Counter(year_values).most_common(1)[0][0]
        if year_values
        else folder_metadata.get("year")
    )
    metadata = {
        "media_kind": "tv_show",
        "show_title": show_title,
        "year": year,
        "season_number": (
            seasons[0]["season_number"] if len(seasons) == 1 else None
        ),
        "season_count": len(seasons),
        "episode_count": len(episodes),
        "video_file_count": len(files["video"]),
        "special_episode_count": len(special_episodes),
        "unresolved_video_count": len(unresolved_files),
        "format": files["video"][0].suffix.lstrip(".").upper(),
        "subtitle_count": len(files["subtitles"]),
        "artwork_count": len(files["artwork"]),
        "ignored_sidecar_count": len(files["ignored"]),
        "ignored_corrupt_video_count": len(zero_byte_videos),
        "ignored_corrupt_video_files": [
            str(path.relative_to(source)) for path in zero_byte_videos
        ],
        "artwork_files": [
            str(path.relative_to(source)) for path in files["artwork"]
        ],
        "subtitle_files": [
            str(path.relative_to(source)) for path in files["subtitles"]
        ],
        "subtitles": subtitles,
        "ignored_sidecar_files": [
            str(path.relative_to(source)) for path in files["ignored"]
        ],
        "seasons": seasons,
        "special_episodes": special_episodes,
        "unresolved_video_files": unresolved_files,
        "tv_warning_details": {
            "unparsed_video_files": unparsed_video_files,
            "generic_title_files": generic_title_files,
        },
        "metadata_quality": (
            "weak" if parse_failed or folder_only_title else "good"
        ),
        "metadata_warnings": list(dict.fromkeys(warnings)),
        "confidence": (
            0.6 if parse_failed
            else 0.65 if folder_only_title
            else 0.85
        ),
    }
    metadata = build_review_state("video_tv_show", metadata)
    metadata = normalize_tv_counts(metadata)
    return {
        "files": files,
        "metadata": metadata,
        "status": (
            "needs_metadata_review"
            if parse_failed or folder_only_title or unresolved_rows
            else "pending_review"
        ),
        "suggested_destination": str(
            settings.tv_dir / safe_tv_path_part(show_title)
        ),
        "suggested_metadata": {
            "show_title": show_title,
            "year": year,
            "sources": {
                "show_title": (
                    "episode filenames" if parsed_titles else "folder name"
                ),
                "year": (
                    "episode filenames" if year_values else "folder name"
                ),
            },
        },
    }


def _apply_tv_batch_data(
    db: Session,
    batch: IngestBatch,
    source: Path,
    data: dict,
) -> None:
    db.query(IngestFile).filter(IngestFile.batch_id == batch.id).delete()
    batch.detected_type = "video_tv_show"
    batch.status = data["status"]
    batch.confidence = data["metadata"]["confidence"]
    batch.suggested_destination = data["suggested_destination"]
    batch.suggested_metadata = data["suggested_metadata"]
    batch.metadata_json = data["metadata"]
    batch.metadata_confirmed = False
    db.add(batch)
    db.flush()

    files = data["files"]
    episode_rows = [
        (path, _tv_episode_metadata(path, source))
        for path in files["video"]
    ]
    role_rows = (
        [(path, "tv_episode", metadata) for path, metadata in episode_rows]
        + [
            (
                path,
                "tv_subtitle",
                _tv_subtitle_metadata(path, source, episode_rows),
            )
            for path in files["subtitles"]
        ]
        + [
            (
                path,
                "tv_artwork",
                _tv_artwork_metadata(
                    path,
                    source,
                    data["metadata"].get("season_number"),
                ),
            )
            for path in files["artwork"]
        ]
    )
    for path, role, file_metadata in role_rows:
        db.add(
            IngestFile(
                batch_id=batch.id,
                file_path=str(path),
                file_name=path.name,
                extension=path.suffix.lower(),
                size_bytes=path.stat().st_size,
                checksum=None,
                detected_role=role,
                metadata_json=file_metadata,
            )
        )


def _create_tv_batch(db: Session, source: Path) -> IngestBatch | None:
    stale_batches = (
        db.query(IngestBatch)
        .filter(
            IngestBatch.source_path == str(source),
            IngestBatch.detected_type.in_(
                ["unknown_type", "unsupported_file"]
            ),
            IngestBatch.status.in_(
                [
                    "needs_quarantine_review",
                    "quarantined",
                    "needs_metadata_review",
                    "pending_review",
                ]
            ),
        )
        .all()
    )
    existing = (
        db.query(IngestBatch)
        .filter(
            IngestBatch.source_path == str(source),
            IngestBatch.detected_type == "video_tv_show",
            IngestBatch.status != "merged",
        )
        .first()
    )
    if existing:
        for stale_batch in stale_batches:
            stale_batch.status = "merged"
        if stale_batches:
            db.commit()
        return None

    data = _tv_batch_data(source)
    if data is None:
        return None
    if stale_batches:
        batch = stale_batches[0]
        for stale_batch in stale_batches[1:]:
            stale_batch.status = "merged"
    else:
        batch = IngestBatch(
            source_kind="manual-drop",
            source_path=str(source),
        )
        db.add(batch)
        db.flush()
    _apply_tv_batch_data(db, batch, source, data)
    db.commit()
    db.refresh(batch)
    write_json_report(settings.reports_dir, batch.id, data["metadata"])
    return batch


def _create_movie_batch(db: Session, source: Path) -> IngestBatch | None:
    stale_batches = (
        db.query(IngestBatch)
        .filter(
            IngestBatch.source_path == str(source),
            IngestBatch.detected_type.in_(
                ["unknown_type", "unsupported_file"]
            ),
            IngestBatch.status.in_(
                [
                    "needs_quarantine_review",
                    "quarantined",
                    "needs_metadata_review",
                    "pending_review",
                ]
            ),
        )
        .all()
    )
    existing = (
        db.query(IngestBatch)
        .filter(
            IngestBatch.source_path == str(source),
            IngestBatch.detected_type == "video_movie",
            IngestBatch.status != "merged",
        )
        .first()
    )
    if existing:
        for stale_batch in stale_batches:
            stale_batch.status = "merged"
        if stale_batches:
            db.commit()
        return None
    files = _movie_files(source)
    if not files["video"]:
        return None
    for stale_batch in stale_batches:
        stale_batch.status = "merged"
    main_video = files["video"][0]
    original_release_name = source.name if source.is_dir() else main_video.name
    parsed = parse_movie_name(original_release_name)
    file_parsed = parse_movie_name(main_video.name)
    if (
        not useful_movie_name(parsed)
        or (not parsed["year"] and file_parsed["year"])
    ):
        parsed = file_parsed
    release_tags_removed = list(
        dict.fromkeys(
            [
                *parsed["release_tags_removed"],
                *file_parsed["release_tags_removed"],
            ]
        )
    )
    title = parsed["title"]
    year = parsed["year"]
    edition = parsed.get("edition")
    if edition and re.search(r"\d", edition):
        edition = None
    video_files = [path.name for path in files["video"]]
    video_file_count = len(files["video"])
    folder = safe_movie_path_part(
        f"{year or 'Unknown Year'} - {title}"
        if not edition
        else f"{year or 'Unknown Year'} - {title} [{edition}]"
    )
    destination = settings.movies_dir / folder
    warnings = [] if year else ["movie_year_missing"]
    metadata = {
        "media_kind": "movie",
        "title": title,
        "year": year,
        "edition": edition,
        "format": main_video.suffix.lstrip(".").upper(),
        "video_file_count": video_file_count,
        "video_files": video_files,
        "artwork_count": len(files["artwork"]),
        "subtitle_count": len(files["subtitles"]),
        "ignored_sidecar_count": len(files["ignored"]),
        "artwork_files": [path.name for path in files["artwork"]],
        "subtitle_files": [path.name for path in files["subtitles"]],
        "ignored_sidecar_files": [
            str(path.relative_to(source)) if source.is_dir() else path.name
            for path in files["ignored"]
        ],
        "original_release_name": original_release_name,
        "primary_video_file": main_video.name,
        "release_tags_removed": release_tags_removed,
        "metadata_quality": "good" if year else "weak",
        "metadata_warnings": warnings,
        "confidence": 0.8 if year else 0.7,
    }
    metadata = build_review_state("video_movie", metadata)
    batch = IngestBatch(
        source_kind="manual-drop",
        source_path=str(source),
        detected_type="video_movie",
        status="pending_review" if year else "needs_metadata_review",
        confidence=metadata["confidence"],
        suggested_destination=str(destination),
        suggested_metadata={"title": title, "year": year, "edition": edition} if edition else {"title": title, "year": year},
        metadata_json=metadata,
    )
    db.add(batch)
    db.flush()
    (
        db.query(IngestBatch)
        .filter(
            IngestBatch.id != batch.id,
            IngestBatch.source_path == str(source),
            IngestBatch.detected_type.in_(["unknown_type", "unsupported_file"]),
            IngestBatch.status != "quarantined",
        )
        .update({"status": "merged"}, synchronize_session=False)
    )
    roles = (
        [(path, "video_file") for path in files["video"]]
        + [(path, "movie_artwork") for path in files["artwork"]]
        + [(path, "subtitle") for path in files["subtitles"]]
    )
    for path, role in roles:
        db.add(
            IngestFile(
                batch_id=batch.id,
                file_path=str(path),
                file_name=path.name,
                extension=path.suffix.lower(),
                size_bytes=path.stat().st_size,
                checksum=file_sha256(path),
                detected_role=role,
                metadata_json=None,
            )
        )
    db.commit()
    db.refresh(batch)
    write_json_report(settings.reports_dir, batch.id, metadata)
    return batch


def _create_book_batch(db: Session, source: Path) -> IngestBatch | None:
    files = collect_book_files(source)
    book_files = files["books"]
    if not book_files:
        return None
    checksums = {file_sha256(path) for path in book_files}
    existing_checksums = {
        row.checksum
        for row in db.query(IngestFile)
        .filter(IngestFile.checksum.in_(checksums))
        .all()
        if row.checksum
    }
    if checksums and checksums.issubset(existing_checksums):
        return None

    metadata = build_single_book_metadata(source, settings.books_dir)
    collection_groups, collection_summary = build_book_collection_groups(
        source,
        files,
    )
    primary_book_files = [group["primary"] for group in collection_groups]
    parsed = [parse_book_name(path.name) for path in primary_book_files]
    identities = {
        (
            item["author"].casefold(),
            item["title"].casefold(),
            item.get("year"),
        )
        for item in parsed
    }
    if len(identities) > 1:
        items = []
        for group, item in sorted(
            zip(collection_groups, parsed),
            key=lambda pair: pair[0]["primary"].name.casefold(),
        ):
            path = group["primary"]
            fmt = book_format_for(path)
            item_metadata = {
                "item_kind": "book",
                "source_key": path.name,
                "source_file": path.name,
                "include": True,
                "author": (
                    item["author"]
                    if item.get("author_guess_confidence") == "high"
                    else "Unknown Author"
                ),
                "title": item["title"],
                "year": item.get("year"),
                "series": item.get("series"),
                "series_index": item.get("series_index"),
                "format": fmt,
                "metadata_assist_version": METADATA_ASSIST_VERSION,
                "matched_artwork": group["matched_artwork"],
                "alternate_formats": group["alternate_formats"],
                "accepted_unknown_author": False,
                "accepted_unknown_year": False,
                "lookup_later": False,
            }
            candidate_runtime: dict = {}
            item_candidates, _ = build_book_metadata_candidates(
                path,
                path,
                [],
                candidate_runtime,
            )
            item_metadata["metadata_candidates"] = item_candidates
            item_metadata["candidate_notes"] = []
            item_metadata["candidate_runtime"] = candidate_runtime
            item_metadata["author"] = preferred_candidate_value(
                item_candidates,
                "author",
                item_metadata["author"],
                min_confidence="high",
                require_not_filename_guess=True,
            )
            item_metadata["title"] = preferred_candidate_value(
                item_candidates,
                "title",
                item_metadata["title"],
            )
            item_metadata["year"] = preferred_candidate_value(
                item_candidates,
                "year",
                item_metadata["year"],
            )
            item_metadata["metadata_title"] = item_metadata["title"]
            item_metadata["display_title"] = clean_display_title(
                item_metadata["title"]
            )
            item_metadata["destination_title"] = destination_title(
                item_metadata["title"]
            )
            destination = build_book_item_destination(
                books_root=settings.books_dir,
                item=item_metadata,
            )
            item_metadata["destination_path"] = str(destination)
            item_metadata["destination_preview"] = (
                destination.relative_to(settings.data_root).as_posix()
            )
            items.append(item_metadata)
        collection_summary["needs_repair_count"] = sum(
            item["author"] == "Unknown Author"
            or item["title"] == "Unknown Title"
            for item in items
        )
        metadata.update({
            "review_type": "book_collection",
            "review_mode": "item_list",
            "author": "Mixed Authors",
            "title": source.name,
            "year": None,
            "collection_title": None,
            "keep_collection_together": False,
            "collection_destination_root": None,
            "book_items": items,
            "collection_summary": collection_summary,
            "metadata_quality": "weak",
            "metadata_warnings": list(dict.fromkeys([
                *metadata.get("metadata_warnings", []),
                "multiple_book_candidates",
            ])),
            "confidence": min(float(metadata.get("confidence") or 0.65), 0.75),
        })
    metadata = build_review_state("book", metadata)
    destination = metadata.get("suggested_destination_preview")
    batch = IngestBatch(
        source_kind="manual-drop",
        source_path=str(source),
        detected_type="book",
        status=(
            "needs_metadata_review"
            if metadata.get("blocking_review_items")
            else "pending_review"
        ),
        confidence=float(metadata.get("confidence") or 0.65),
        suggested_destination=str(destination) if destination else None,
        suggested_metadata={
            "metadata_assist_version": METADATA_ASSIST_VERSION,
            "author": preferred_candidate_value(
                metadata.get("metadata_candidates") or {},
                "author",
                metadata.get("author"),
            ),
            "title": preferred_candidate_value(
                metadata.get("metadata_candidates") or {},
                "title",
                metadata.get("title"),
            ),
            "year": preferred_candidate_value(
                metadata.get("metadata_candidates") or {},
                "year",
                metadata.get("year"),
            ),
            "format": metadata.get("format"),
        },
        metadata_json=metadata,
    )
    db.add(batch)
    db.flush()
    roles = (
        [(path, "book_file") for path in files["books"]]
        + [
            (path, "book_alternate_format")
            for path in files.get("alternates", [])
        ]
        + [(path, "book_artwork") for path in files["artwork"]]
        + [(path, "book_sidecar") for path in files["sidecars"]]
    )
    for path, role in roles:
        db.add(IngestFile(
            batch_id=batch.id,
            file_path=str(path),
            file_name=path.name,
            extension=path.suffix.lower(),
            size_bytes=path.stat().st_size,
            checksum=file_sha256(path),
            detected_role=role,
            metadata_json=None,
        ))
    db.commit()
    db.refresh(batch)
    write_json_report(settings.reports_dir, batch.id, metadata)
    return batch


def _create_audiobook_batch(db: Session, source: Path) -> IngestBatch | None:
    files = collect_audiobook_files(source)
    audio_files = files["audio"]
    if not audio_files:
        return None
    checksums = {file_sha256(path) for path in audio_files}
    existing_checksums = {
        row.checksum
        for row in db.query(IngestFile)
        .filter(IngestFile.checksum.in_(checksums))
        .all()
        if row.checksum
    }
    if checksums and checksums.issubset(existing_checksums):
        return None

    metadata = build_audiobook_metadata(source, settings.audiobooks_dir)
    metadata = build_review_state("audiobook", metadata)
    destination = metadata.get("suggested_destination_preview")
    batch = IngestBatch(
        source_kind="manual-drop",
        source_path=str(source),
        detected_type="audiobook",
        status=(
            "needs_metadata_review"
            if metadata.get("blocking_review_items")
            else "pending_review"
        ),
        confidence=float(metadata.get("confidence") or 0.65),
        suggested_destination=str(destination) if destination else None,
        suggested_metadata={
            "metadata_assist_version": METADATA_ASSIST_VERSION,
            "author": preferred_candidate_value(
                metadata.get("metadata_candidates") or {},
                "author",
                metadata.get("author"),
            ),
            "title": preferred_candidate_value(
                metadata.get("metadata_candidates") or {},
                "title",
                metadata.get("title"),
            ),
            "year": preferred_candidate_value(
                metadata.get("metadata_candidates") or {},
                "year",
                metadata.get("year"),
            ),
            "narrator": preferred_candidate_value(
                metadata.get("metadata_candidates") or {},
                "narrator",
                metadata.get("narrator"),
            ),
            "format": metadata.get("format"),
        },
        metadata_json=metadata,
    )
    db.add(batch)
    db.flush()
    roles = (
        [(path, "audiobook_audio") for path in files["audio"]]
        + [(path, "audiobook_artwork") for path in files["artwork"]]
        + [(path, "audiobook_sidecar") for path in files["sidecars"]]
    )
    for path, role in roles:
        db.add(IngestFile(
            batch_id=batch.id,
            file_path=str(path),
            file_name=path.name,
            extension=path.suffix.lower(),
            size_bytes=path.stat().st_size,
            checksum=file_sha256(path),
            detected_role=role,
            metadata_json=None,
        ))
    db.commit()
    db.refresh(batch)
    write_json_report(settings.reports_dir, batch.id, metadata)
    return batch


def _merge_active_quarantine_rows_for_source(
    db: Session,
    source: Path,
    *,
    reason: str,
) -> int:
    """Retire obsolete quarantine rows for one exact source path."""
    stale_rows = (
        db.query(IngestBatch)
        .filter(
            IngestBatch.source_path == str(source),
            IngestBatch.detected_type.in_(QUARANTINE_TYPES),
            IngestBatch.status.in_(ACTIVE_REVIEW_STATUSES),
        )
        .all()
    )
    merged = 0
    for batch in stale_rows:
        metadata = dict(batch.metadata_json or {})
        metadata["stale_quarantine_merged"] = True
        metadata["stale_quarantine_merge_reason"] = reason
        batch.metadata_json = metadata
        batch.status = "merged"
        merged += 1
    return merged


def repair_stale_media_batches(
    db: Session,
    classifications: dict[Path, str],
) -> list[IngestBatch]:
    """Repair obsolete quarantine rows without suppressing active media."""
    repaired: list[IngestBatch] = []

    for source, classification in classifications.items():
        if classification in RECOGNIZED_MEDIA_TYPES:
            _merge_active_quarantine_rows_for_source(
                db,
                source,
                reason=f"current_scan_classified_as_{classification}",
            )

            if classification == "video_tv_show":
                batch = _create_tv_batch(db, source)
                if batch:
                    repaired.append(batch)
            elif classification == "video_movie":
                batch = _create_movie_batch(db, source)
                if batch:
                    repaired.append(batch)
            elif classification == "book":
                batch = _create_book_batch(db, source)
                if batch:
                    repaired.append(batch)
            elif classification == "audiobook":
                batch = _create_audiobook_batch(db, source)
                if batch:
                    repaired.append(batch)
            continue

        if (
            classification == "unknown_type"
            and source.is_dir()
            and _is_empty_source_leftover(source)
        ):
            _merge_active_quarantine_rows_for_source(
                db,
                source,
                reason="empty_source_leftover",
            )

    stale_rows = (
        db.query(IngestBatch)
        .filter(
            IngestBatch.detected_type.in_(QUARANTINE_TYPES),
            IngestBatch.status.in_(ACTIVE_REVIEW_STATUSES),
        )
        .all()
    )
    for batch in stale_rows:
        source = Path(batch.source_path)
        if not source.exists():
            metadata = dict(batch.metadata_json or {})
            quarantine_destination = Path(
                metadata.get("quarantine_destination") or ""
            )
            if (
                batch.status == "quarantined"
                and quarantine_destination.exists()
            ):
                continue
            metadata["stale_quarantine_merged"] = True
            metadata["stale_quarantine_merge_reason"] = "source_path_missing"
            batch.metadata_json = metadata
            batch.status = "merged"

    db.commit()
    return repaired


def _unknown_metadata(
    path: Path,
    classification: str,
    *,
    music_parent: Path | None = None,
) -> dict:
    if path.is_file():
        reason = (
            "Unsupported file found inside a recognized music collection"
            if music_parent
            else "Unsupported loose file in _INGEST"
        )
        return {
            "name": path.name,
            "reason": reason,
            "file_count": 1,
            "folder_count": 0,
            "size_bytes": path.stat().st_size,
            "sample_files": [path.name],
            "music_parent": str(music_parent) if music_parent else None,
            "relative_path": (
                str(path.relative_to(music_parent))
                if music_parent
                else path.name
            ),
            "recommended_action": "Move to quarantine",
            "metadata_quality": "unsupported",
            "metadata_warnings": ["quarantine_review_required"],
        }
    files = sorted(candidate for candidate in path.rglob("*") if candidate.is_file())
    folders = [candidate for candidate in path.rglob("*") if candidate.is_dir()]
    extensions = {candidate.suffix.casefold() for candidate in files}
    video_extensions = {".mkv", ".mp4", ".avi", ".mov", ".wmv", ".m4v"}
    document_extensions = {".pdf", ".epub", ".mobi", ".azw", ".azw3"}
    if extensions & video_extensions:
        reason = "Unclassified video folder"
    elif extensions and extensions.issubset(document_extensions):
        reason = "Book/document support not implemented yet"
    elif len(extensions) > 1:
        reason = "Mixed unsupported file types"
    elif files:
        reason = "No supported audio files found"
    else:
        reason = "Folder does not match a known media structure"
    return {
        "name": path.name,
        "reason": reason,
        "file_count": len(files),
        "folder_count": len(folders) + 1,
        "size_bytes": sum(candidate.stat().st_size for candidate in files),
        "sample_files": [
            str(candidate.relative_to(path)) for candidate in files[:10]
        ],
        "recommended_action": "Move to quarantine",
        "metadata_quality": "unsupported",
        "metadata_warnings": ["quarantine_review_required"],
    }


def _create_unknown_batch(
    db: Session,
    path: Path,
    classification: str,
    *,
    music_parent: Path | None = None,
) -> IngestBatch | None:
    if path.is_dir() and _is_empty_source_leftover(path):
        _merge_active_quarantine_rows_for_source(
            db,
            path,
            reason="empty_source_leftover_no_new_unknown_batch",
        )
        db.commit()
        return None

    if path.is_dir() and _has_supported_audio_or_video(path):
        return None

    if path.is_dir():
        video_files = _movie_files(path)
        if folder_looks_like_tv_show(path, video_files["video"]):
            return None
        if len(video_files["video"]) >= 1:
            return None
        if any(
            candidate.is_file() and is_audio_file(candidate)
            for candidate in path.rglob("*")
        ):
            return None

    existing = (
        db.query(IngestBatch)
        .filter(
            IngestBatch.source_path == str(path),
            IngestBatch.status != "quarantined",
        )
        .first()
    )
    if existing:
        return None
    metadata = _unknown_metadata(
        path,
        classification,
        music_parent=music_parent,
    )
    batch = IngestBatch(
        source_kind="manual-drop",
        source_path=str(path),
        detected_type=classification,
        status="needs_quarantine_review",
        confidence=0.0,
        metadata_json=metadata,
    )
    db.add(batch)
    db.commit()
    db.refresh(batch)
    write_json_report(settings.reports_dir, batch.id, metadata)
    return batch


def _retire_noisy_unsupported_batches(
    db: Session,
    music_roots: list[Path],
    loose_files: list[Path],
) -> None:
    loose_paths = {str(path) for path in loose_files}
    active = (
        db.query(IngestBatch)
        .filter(
            IngestBatch.detected_type == "unsupported_file",
            IngestBatch.status != "quarantined",
            IngestBatch.status != "merged",
        )
        .all()
    )
    for batch in active:
        source = Path(batch.source_path)
        metadata = batch.metadata_json or {}
        nested_in_music = any(
            source.resolve().is_relative_to(root.resolve())
            for root in music_roots
            if root.exists()
        ) or bool(metadata.get("music_parent"))
        if nested_in_music or batch.source_path in loose_paths:
            batch.status = "merged"
    db.commit()


def _create_grouped_loose_files_batch(
    db: Session,
    paths: list[Path],
) -> IngestBatch | None:
    if not paths:
        return None
    existing = (
        db.query(IngestBatch)
        .filter(
            IngestBatch.source_path == str(settings.ingest_root),
            IngestBatch.detected_type == "unsupported_file",
            IngestBatch.status == "needs_quarantine_review",
        )
        .first()
    )
    metadata = {
        "name": "Unsupported loose files",
        "reason": "Unsupported loose files in _INGEST",
        "file_count": len(paths),
        "folder_count": 0,
        "size_bytes": sum(path.stat().st_size for path in paths),
        "grouped_loose_files": [str(path) for path in paths],
        "sample_files": [path.name for path in paths[:10]],
        "recommended_action": "Move group to quarantine",
        "metadata_quality": "unsupported",
        "metadata_warnings": ["cleanup_review_required"],
    }
    if existing:
        existing.metadata_json = metadata
        existing.files.clear()
        batch = existing
    else:
        batch = IngestBatch(
            source_kind="manual-drop",
            source_path=str(settings.ingest_root),
            detected_type="unsupported_file",
            status="needs_quarantine_review",
            confidence=0.0,
            metadata_json=metadata,
        )
        db.add(batch)
        db.flush()
    for path in paths:
        batch.files.append(
            IngestFile(
                file_path=str(path),
                file_name=path.name,
                extension=path.suffix.lower(),
                size_bytes=path.stat().st_size,
                detected_role="unsupported_loose_file",
                metadata_json=None,
            )
        )
    db.commit()
    db.refresh(batch)
    write_json_report(settings.reports_dir, batch.id, metadata)
    return batch


def _update_existing_music_sidecars(
    db: Session,
    music_roots: list[Path],
) -> None:
    for root in music_roots:
        batch = (
            db.query(IngestBatch)
            .filter(
                IngestBatch.source_path == str(root),
                IngestBatch.detected_type.in_(
                    ["music_album", "music_discography"]
                ),
                IngestBatch.status != "merged",
            )
            .order_by(IngestBatch.id.desc())
            .first()
        )
        if not batch:
            continue
        sidecars = _ignored_music_sidecars(root)
        metadata = dict(batch.metadata_json or {})
        metadata["ignored_sidecar_count"] = len(sidecars)
        metadata["ignored_sidecar_files"] = [
            str(path.relative_to(root)) for path in sidecars
        ]
        batch.metadata_json = metadata
    db.commit()


def _destination_contains_all_checksums(
    destination: Path,
    expected_checksums: set[str],
) -> bool:
    if not destination.exists() or not expected_checksums:
        return False
    found: set[str] = set()
    for path in destination.rglob("*"):
        if not path.is_file() or not is_audio_file(path):
            continue
        checksum = file_sha256(path)
        if checksum in expected_checksums:
            found.add(checksum)
        if found == expected_checksums:
            return True
    return False


def _release_source_path(path: Path) -> Path:
    if re.fullmatch(r"(?:cd|disc|disk)\s*\d+", path.parent.name, flags=re.IGNORECASE):
        return path.parent.parent
    return path.parent


def _group_key(path: Path, metadata: dict) -> str:
    source_path = _release_source_path(path)
    if source_path.resolve() != settings.ingest_root.resolve():
        return f"source|{source_path.resolve()}"
    return album_group_key(metadata)


def _representative_value(track_metadata: list[dict], key: str, default: str) -> str:
    values = [
        str(metadata.get(key) or "").strip()
        for metadata in track_metadata
        if normalize_key(str(metadata.get(key) or "")) not in UNKNOWN_VALUES
    ]
    if not values:
        return default
    counts = Counter(normalize_key(value) for value in values)
    winner = counts.most_common(1)[0][0]
    return next(value for value in values if normalize_key(value) == winner)


def _discography_groups(
    audio_files: list[Path],
    file_metadata: dict[str, dict],
) -> dict[Path, dict[Path, list[Path]]]:
    candidates: dict[Path, dict[Path, list[Path]]] = {}
    ingest_root = settings.ingest_root.resolve()
    top_level_dirs = sorted(
        path for path in settings.ingest_root.iterdir()
        if path.is_dir()
        and classify_ingest_item(path) in {"music_album", "music_discography"}
    )
    for parent in top_level_dirs:
        child_groups: dict[Path, list[Path]] = {}
        for child in sorted(path for path in parent.iterdir() if path.is_dir()):
            child_files = [
                path for path in audio_files
                if path.resolve().is_relative_to(child.resolve())
            ]
            if child_files:
                child_groups[child] = child_files
        child_metadata = {
            str(child): [file_metadata[str(path)] for path in paths]
            for child, paths in child_groups.items()
        }
        if (
            parent.resolve().parent == ingest_root
            and looks_like_discography_parent(
                parent,
                list(child_groups),
                child_metadata,
            )
        ):
            candidates[parent] = child_groups
    return candidates


def _create_discography_batch(
    db: Session,
    parent: Path,
    child_groups: dict[Path, list[Path]],
    file_metadata: dict[str, dict],
    file_checksums: dict[str, str],
) -> IngestBatch | None:
    all_paths = [path for paths in child_groups.values() for path in paths]
    checksums = {file_checksums[str(path)] for path in all_paths}
    existing_checksums = {
        row.checksum
        for row in db.query(IngestFile)
        .filter(IngestFile.checksum.in_(checksums))
        .all()
        if row.checksum
    }
    if checksums and checksums.issubset(existing_checksums):
        return None

    all_track_metadata = [file_metadata[str(path)] for path in all_paths]
    parent_parse = parse_discography_parent_folder(parent.name)
    parent_artist = parent_parse.get("artist")
    embedded_artist = common_album_artist(all_track_metadata)
    if embedded_artist and (
        not parent_artist
        or canonical_artist_key(embedded_artist) == canonical_artist_key(parent_artist)
        or bool(parent_parse.get("removed_tokens"))
    ):
        artist = embedded_artist
        artist_source = "common embedded albumartist + cleaned parent folder"
    else:
        artist = parent_artist or common_track_artist(all_track_metadata) or "Unknown Artist"
        artist_source = (
            "cleaned parent folder"
            if parent_artist
            else "common embedded track artist"
        )
    album_summaries = []
    formats = set()
    warnings = ["discography_grouping_used"]
    ingest_files = []

    for child, paths in sorted(child_groups.items(), key=lambda item: item[0].name.lower()):
        folder = parse_music_folder_name(child.name)
        track_metadata = [file_metadata[str(path)] for path in paths]
        album = folder.get("album") or child.name
        year = folder.get("year")
        extensions = {path.suffix.lower() for path in paths}
        child_formats = {
            "FLAC" if extension == ".flac" else "MP3"
            for extension in extensions
        }
        formats.update(child_formats)
        album_format = ", ".join(sorted(child_formats))
        child_warnings = []
        release_tags = music_folder_release_tags(child.name)
        if not year:
            child_warnings.append("album_missing_year")
        if not album or normalize_key(album) in UNKNOWN_VALUES:
            child_warnings.append("album_missing_title")
        if len(paths) == 1:
            child_warnings.extend(["one_track_release", "possible_single_or_ep"])
            release_type = "single"
        elif len(paths) <= 3 and re.search(r"\bep\b", album, flags=re.IGNORECASE):
            release_type = "ep"
        elif len(paths) <= 3:
            release_type = "single"
        else:
            release_type = "album"
        embedded_years = [
            str(metadata.get("date") or "")[:4]
            for metadata in track_metadata
            if re.fullmatch(r"(?:19|20)\d{2}", str(metadata.get("date") or "")[:4])
        ]
        if year and embedded_years:
            common_year, common_year_count = Counter(embedded_years).most_common(1)[0]
            if common_year_count * 10 >= len(track_metadata) * 7 and common_year != year:
                child_warnings.append("suspicious_year")
        folder_artist = folder.get("artist")
        if (
            folder_artist
            and not is_compilation_artist(folder_artist)
            and canonical_artist_key(folder_artist) != canonical_artist_key(artist)
            and canonical_artist_key(artist) not in canonical_artist_key(folder_artist)
        ):
            child_warnings.append("folder_artist_mismatch")
        if release_tags:
            child_warnings.append("release_tag_removed")
        if album != child.name:
            child_warnings.append("album_title_from_folder_cleanup")
        if len(extensions) > 1:
            child_warnings.append("mixed_formats")
        if {"album_missing_year", "album_missing_title"} & set(child_warnings):
            warnings.append("child_album_metadata_missing")
        child_blocking = bool(
            {"album_missing_year", "album_missing_title"} & set(child_warnings)
        )
        artwork_paths = _artwork_files(child)
        ignored_sidecars = _ignored_music_sidecars(child)

        album_summaries.append(
            {
                "source_folder": child.name,
                "artist": artist,
                "album": album,
                "year": year,
                "format": album_format,
                "track_count": len(paths),
                "artwork_count": len(artwork_paths),
                "artwork_files": [path.name for path in artwork_paths],
                "ignored_sidecar_count": len(ignored_sidecars),
                "ignored_sidecar_files": [path.name for path in ignored_sidecars],
                "release_type": release_type,
                "include": True,
                "status": "needs_review" if child_blocking else (
                    "warning" if child_warnings else "ready"
                ),
                "warnings": list(dict.fromkeys(child_warnings)),
                "release_tags_removed": release_tags,
            }
        )
        for path in paths:
            if file_checksums[str(path)] in existing_checksums:
                continue
            metadata = dict(file_metadata[str(path)])
            metadata["_discography_album"] = {
                "source_folder": child.name,
                "album": album,
                "year": year,
                "format": album_format,
                "release_type": release_type,
                "include": True,
            }
            ingest_files.append(
                IngestFile(
                    file_path=str(path),
                    file_name=path.name,
                    extension=path.suffix.lower(),
                    size_bytes=path.stat().st_size,
                    checksum=file_checksums[str(path)],
                    detected_role="discography_track",
                    metadata_json=metadata,
                )
            )
        for path in artwork_paths:
            ingest_files.append(
                IngestFile(
                    file_path=str(path),
                    file_name=path.name,
                    extension=path.suffix.lower(),
                    size_bytes=path.stat().st_size,
                    checksum=file_sha256(path),
                    detected_role="artwork",
                    metadata_json={
                        "_discography_album": {
                            "source_folder": child.name,
                            "album": album,
                            "year": year,
                            "format": album_format,
                            "release_type": release_type,
                            "include": True,
                        },
                    },
                )
            )

    if len(formats) > 1:
        warnings.append("mixed_formats")
    if existing_checksums:
        warnings.append("partial_duplicate_tracks_detected")

    blocking = (
        normalize_key(artist) in UNKNOWN_VALUES
        or "child_album_metadata_missing" in warnings
        or bool(existing_checksums)
    )
    destination = settings.music_discographies_dir / artist
    collection_sidecars = _ignored_music_sidecars(parent)
    metadata = {
        "artist": artist,
        "collection_type": "discography",
        "album_count": len(album_summaries),
        "release_count": len(album_summaries),
        "track_count": len(all_paths),
        "artwork_count": sum(album["artwork_count"] for album in album_summaries),
        "artwork_files": [
            name
            for album in album_summaries
            for name in album["artwork_files"]
        ],
        "ignored_sidecar_count": len(collection_sidecars),
        "ignored_sidecar_files": [
            str(path.relative_to(parent)) for path in collection_sidecars
        ],
        "format_summary": sorted(formats),
        "albums": album_summaries,
        "parent_cleanup": parent_parse,
        "artist_source": artist_source,
        "metadata_quality": "weak" if blocking else "good",
        "metadata_warnings": list(dict.fromkeys(warnings)),
        "confidence": 0.6 if blocking else 1.0,
    }
    metadata = build_review_state("music_discography", metadata)
    batch = IngestBatch(
        source_kind="manual-drop",
        source_path=str(parent),
        detected_type="music_discography",
        status="needs_metadata_review" if blocking else "pending_review",
        confidence=metadata["confidence"],
        suggested_destination=str(destination),
        suggested_metadata={
            "artist": artist,
            "sources": {"artist": artist_source},
        },
        metadata_json=metadata,
    )
    db.add(batch)
    db.flush()
    for ingest_file in sort_music_tracks(ingest_files):
        ingest_file.batch_id = batch.id
        db.add(ingest_file)
    db.commit()
    db.refresh(batch)
    write_json_report(settings.reports_dir, batch.id, metadata)
    return batch


def scan_music_ingest(db: Session) -> ScanMusicResult:
    settings.ingest_root.mkdir(parents=True, exist_ok=True)
    classifications = {
        item: classify_ingest_item(item)
        for item in sorted(settings.ingest_root.iterdir())
    }
    repaired_batches = repair_stale_media_batches(db, classifications)
    batches: list[IngestBatch] = list(repaired_batches)
    tv_batches = [
        batch
        for batch in repaired_batches
        if batch.detected_type == "video_tv_show"
    ]
    for item, classification in classifications.items():
        if classification != "video_tv_show":
            continue
        batch = _create_tv_batch(db, item)
        if batch:
            tv_batches.append(batch)
            batches.append(batch)
    movie_batches = [
        batch
        for batch in repaired_batches
        if batch.detected_type == "video_movie"
    ]
    for item, classification in classifications.items():
        if classification != "video_movie":
            continue
        batch = _create_movie_batch(db, item)
        if batch:
            movie_batches.append(batch)
            batches.append(batch)
    book_batches = [
        batch for batch in repaired_batches if batch.detected_type == "book"
    ]
    for item, classification in classifications.items():
        if classification != "book":
            continue
        batch = _create_book_batch(db, item)
        if batch:
            book_batches.append(batch)
            batches.append(batch)
    audiobook_batches = [
        batch
        for batch in repaired_batches
        if batch.detected_type == "audiobook"
    ]
    for item, classification in classifications.items():
        if classification != "audiobook":
            continue
        batch = _create_audiobook_batch(db, item)
        if batch:
            audiobook_batches.append(batch)
            batches.append(batch)

    unknown_batches = []
    for item, classification in classifications.items():
        if classification != "unknown_type":
            continue
        batch = _create_unknown_batch(db, item, classification)
        if batch:
            unknown_batches.append(batch)
    music_roots = [
        item
        for item, classification in classifications.items()
        if classification in {"music_album", "music_discography"} and item.is_dir()
    ]
    loose_unsupported = [
        item
        for item, classification in classifications.items()
        if classification == "unsupported_file"
    ]
    _retire_noisy_unsupported_batches(db, music_roots, loose_unsupported)
    _update_existing_music_sidecars(db, music_roots)
    grouped_loose_batch = _create_grouped_loose_files_batch(db, loose_unsupported)
    if grouped_loose_batch:
        unknown_batches.append(grouped_loose_batch)
    batches.extend(unknown_batches)

    audio_files = _root_music_audio_files()
    if not audio_files:
        return ScanMusicResult(
            created=len(batches),
            skipped_duplicates=0,
            batches=batches,
            unknown_items=sum(
                classification == "unknown_type"
                for classification in classifications.values()
            ),
            unsupported_files=len(loose_unsupported),
            ignored_system_files=sum(
                classification == "ignored_system_folder"
                for classification in classifications.values()
            ),
            movie_batches_found=sum(
                classification == "video_movie"
                for classification in classifications.values()
            ),
            tv_shows_found=sum(
                classification == "video_tv_show"
                for classification in classifications.values()
            ),
            tv_episodes_found=sum(
                len(_tv_files(item)["video"])
                for item, classification in classifications.items()
                if classification == "video_tv_show"
            ),
            subtitle_files_found=sum(
                len(_movie_files(item)["subtitles"])
                for item, classification in classifications.items()
                if classification == "video_movie"
            ) + sum(
                len(_tv_files(item)["subtitles"])
                for item, classification in classifications.items()
                if classification == "video_tv_show"
            ),
            artwork_files_found=sum(
                len(_movie_files(item)["artwork"])
                for item, classification in classifications.items()
                if classification == "video_movie"
            ) + sum(
                len(_tv_files(item)["artwork"])
                for item, classification in classifications.items()
                if classification == "video_tv_show"
            ),
            book_batches_found=len(book_batches),
            book_files_found=sum(
                int((batch.metadata_json or {}).get("book_file_count") or 0)
                for batch in book_batches
            ),
            audiobook_batches_found=len(audiobook_batches),
            audiobook_files_found=sum(
                int(
                    (batch.metadata_json or {}).get(
                        "audiobook_file_count"
                    ) or 0
                )
                for batch in audiobook_batches
            ),
        )

    file_metadata: dict[str, dict] = {}
    file_checksums: dict[str, str] = {}

    for path in audio_files:
        metadata = extract_music_metadata(path)
        file_metadata[str(path)] = metadata
        file_checksums[str(path)] = file_sha256(path)

    discography_groups = _discography_groups(audio_files, file_metadata)
    discography_paths = {
        path.resolve()
        for child_groups in discography_groups.values()
        for paths in child_groups.values()
        for path in paths
    }
    groups: dict[str, list[Path]] = defaultdict(list)
    for path in audio_files:
        if path.resolve() in discography_paths:
            continue
        groups[_group_key(path, file_metadata[str(path)])].append(path)

    skipped_duplicates = 0
    for parent, child_groups in discography_groups.items():
        batch = _create_discography_batch(
            db,
            parent,
            child_groups,
            file_metadata,
            file_checksums,
        )
        if batch:
            batches.append(batch)
        else:
            skipped_duplicates += 1

    for paths in groups.values():
        if not paths:
            continue

        group_checksums = {file_checksums[str(path)] for path in paths}
        existing_rows = (
            db.query(IngestFile)
            .filter(IngestFile.checksum.in_(group_checksums))
            .all()
        )
        existing_checksums = {
            ingest_file.checksum
            for ingest_file in existing_rows
            if ingest_file.checksum
        }
        if group_checksums.issubset(existing_checksums):
            skipped_duplicates += 1
            continue

        sample_path = paths[0]
        sample_meta = file_metadata[str(sample_path)]
        discs = {
            file_metadata[str(path)].get("discnumber", 1)
            for path in paths
        }
        track_metadata = [file_metadata[str(path)] for path in paths]
        album_meta = {
            "artist": _representative_value(
                track_metadata, "albumartist", sample_meta["albumartist"]
            ),
            "album": _representative_value(
                track_metadata, "album", sample_meta["album"]
            ),
            "year": _representative_value(
                track_metadata, "date", sample_meta["date"]
            ),
            "genre": _representative_value(
                track_metadata, "genre", sample_meta.get("genre") or "Unknown"
            ),
            "disc_count": len(discs),
            "track_count": len(paths),
            "format": "FLAC" if "flac" in sample_meta.get("extension", "") else "MP3",
            "tracks": [],
        }
        raw_artist = str(album_meta["artist"])
        display_artist, artist_cleanup = clean_compilation_artist(raw_artist)
        if artist_cleanup:
            album_meta["artist"] = display_artist
            album_meta["albumartist"] = display_artist
            album_meta["display_artist"] = display_artist
            album_meta["raw_artist"] = raw_artist
            album_meta["artist_cleanup"] = artist_cleanup
            album_meta["is_compilation"] = True

        quality = evaluate_music_album_metadata(album_meta)
        album_meta.update(quality)

        source_path = _release_source_path(sample_path)
        artwork_paths = _artwork_files(source_path)
        ignored_sidecars = _ignored_music_sidecars(source_path)
        album_meta["artwork_count"] = len(artwork_paths)
        album_meta["artwork_files"] = [path.name for path in artwork_paths]
        album_meta["ignored_sidecar_count"] = len(ignored_sidecars)
        album_meta["ignored_sidecar_files"] = [
            str(path.relative_to(source_path)) for path in ignored_sidecars
        ]
        suggested_metadata = build_suggested_metadata(
            source_path,
            track_metadata,
            album_meta,
        )
        folder_display_artist, folder_artist_cleanup = (
            compilation_artist_cleanup_from_folder(source_path.name)
        )
        if folder_artist_cleanup and not artist_cleanup:
            artist_cleanup = folder_artist_cleanup
            album_meta["artist"] = folder_display_artist
            album_meta["albumartist"] = folder_display_artist
            album_meta["display_artist"] = folder_display_artist
            album_meta["raw_artist"] = folder_artist_cleanup["raw_artist"]
            album_meta["artist_cleanup"] = folder_artist_cleanup
            album_meta["is_compilation"] = True
            suggested_metadata["artist"] = folder_display_artist
            suggested_metadata["compilation"] = True
            suggested_metadata.setdefault("sources", {})["artist"] = (
                "cleaned compilation folder"
            )
            quality = evaluate_music_album_metadata(album_meta)
            album_meta.update(quality)
        warnings = list(album_meta.get("metadata_warnings", []))
        if artist_cleanup:
            warnings.extend(["compilation_detected", "compilation_prefix_removed"])
        if source_path.resolve() != settings.ingest_root.resolve():
            warnings.append("release_folder_grouping_used")
            warnings.extend(
                metadata_mismatch_warnings(track_metadata, suggested_metadata)
            )
        album_meta["metadata_warnings"] = list(dict.fromkeys(warnings))

        mixed_track_artists = has_mixed_track_artists(track_metadata)
        if suggested_metadata.get("compilation") or mixed_track_artists:
            warnings = list(album_meta.get("metadata_warnings", []))
            if "compilation_suspected" not in warnings:
                warnings.append("compilation_suspected")
            album_meta["metadata_warnings"] = warnings
        if (
            mixed_track_artists
            and not suggested_metadata.get("artist")
            and not is_compilation_artist(album_meta.get("artist"))
        ):
            quality["metadata_quality"] = "weak"
            quality["confidence"] = min(float(quality["confidence"]), 0.6)
            quality["metadata_warnings"] = album_meta["metadata_warnings"]
            album_meta.update(quality)

        destination_metadata = {
            "albumartist": suggested_metadata.get("artist") or album_meta["artist"],
            "album": suggested_metadata.get("album") or album_meta["album"],
            "date": suggested_metadata.get("year") or album_meta["year"],
            "extension": sample_meta.get("extension", ""),
        }
        destination = suggest_music_destination(
            destination_metadata,
            settings.music_flac_dir,
            settings.music_mp3_dir,
        )

        if _destination_contains_all_checksums(destination, group_checksums):
            skipped_duplicates += 1
            continue

        new_paths = [
            path
            for path in paths
            if file_checksums[str(path)] not in existing_checksums
        ]
        if not new_paths:
            skipped_duplicates += 1
            continue

        status = "pending_review"
        if quality["metadata_quality"] == "weak":
            status = "needs_metadata_review"
        elif quality["metadata_quality"] == "broken":
            status = "metadata_recovery"

        if existing_checksums:
            warnings = list(album_meta.get("metadata_warnings", []))
            warnings.append("partial_duplicate_tracks_detected")
            album_meta["metadata_warnings"] = warnings
            album_meta["metadata_quality"] = "weak"
            album_meta["confidence"] = min(float(album_meta["confidence"]), 0.5)
            status = "needs_metadata_review"

        album_meta = build_review_state("music_album", album_meta)
        batch = IngestBatch(
            source_kind="manual-drop",
            source_path=str(source_path),
            detected_type="music_album",
            status=status,
            confidence=album_meta["confidence"],
            suggested_destination=str(destination),
            suggested_metadata=suggested_metadata,
            metadata_json=album_meta,
        )
        db.add(batch)
        db.flush()

        ingest_files = []
        for path in new_paths:
            metadata = file_metadata[str(path)]
            ingest_files.append(
                IngestFile(
                    batch_id=batch.id,
                    file_path=str(path),
                    file_name=path.name,
                    extension=path.suffix.lower(),
                    size_bytes=path.stat().st_size,
                    checksum=file_checksums[str(path)],
                    detected_role="music_track",
                    metadata_json=metadata,
                )
            )
        for path in artwork_paths:
            ingest_files.append(
                IngestFile(
                    batch_id=batch.id,
                    file_path=str(path),
                    file_name=path.name,
                    extension=path.suffix.lower(),
                    size_bytes=path.stat().st_size,
                    checksum=file_sha256(path),
                    detected_role="artwork",
                    metadata_json={"artwork_name": path.name},
                )
            )
        for ingest_file in sort_music_tracks(ingest_files):
            db.add(ingest_file)
            metadata = ingest_file.metadata_json or {}
            album_meta["tracks"].append(
                {
                    "title": metadata.get("title") or Path(ingest_file.file_name).stem,
                    "track_number": metadata.get("tracknumber", "1"),
                    "disc_number": metadata.get("discnumber", 1),
                }
            )

        db.commit()
        db.refresh(batch)
        write_json_report(settings.reports_dir, batch.id, album_meta)
        batches.append(batch)

    return ScanMusicResult(
        created=len(batches),
        skipped_duplicates=skipped_duplicates,
        batches=batches,
        music_albums_found=sum(
            classification == "music_album"
            for classification in classifications.values()
        ),
        discographies_found=sum(
            classification == "music_discography"
            for classification in classifications.values()
        ),
        unknown_items=sum(
            classification == "unknown_type"
            for classification in classifications.values()
        ),
        unsupported_files=len(loose_unsupported),
        ignored_system_files=sum(
            classification == "ignored_system_folder"
            for classification in classifications.values()
        ),
        artwork_files_found=sum(
            len(_artwork_files(item))
            for item, classification in classifications.items()
            if classification in {"music_album", "music_discography"}
        ) + sum(
            len(_movie_files(item)["artwork"])
            for item, classification in classifications.items()
            if classification == "video_movie"
        ) + sum(
            len(_tv_files(item)["artwork"])
            for item, classification in classifications.items()
            if classification == "video_tv_show"
        ),
        movie_batches_found=sum(
            classification == "video_movie"
            for classification in classifications.values()
        ),
        tv_shows_found=sum(
            classification == "video_tv_show"
            for classification in classifications.values()
        ),
        tv_episodes_found=sum(
            len(_tv_files(item)["video"])
            for item, classification in classifications.items()
            if classification == "video_tv_show"
        ),
        subtitle_files_found=sum(
            len(_movie_files(item)["subtitles"])
            for item, classification in classifications.items()
            if classification == "video_movie"
        ) + sum(
            len(_tv_files(item)["subtitles"])
            for item, classification in classifications.items()
            if classification == "video_tv_show"
        ),
        book_batches_found=len(book_batches),
        book_files_found=sum(
            int((batch.metadata_json or {}).get("book_file_count") or 0)
            for batch in book_batches
        ),
        audiobook_batches_found=len(audiobook_batches),
        audiobook_files_found=sum(
            int(
                (batch.metadata_json or {}).get("audiobook_file_count")
                or 0
            )
            for batch in audiobook_batches
        ),
    )
