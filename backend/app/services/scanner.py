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
    common_album_artist,
    common_track_artist,
    evaluate_music_album_metadata,
    extract_music_metadata,
    has_mixed_track_artists,
    is_audio_file,
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


@dataclass(frozen=True)
class ScanMusicResult:
    created: int
    skipped_duplicates: int
    batches: list[IngestBatch]


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
}


def classify_ingest_item(path: Path) -> str:
    if path.name.casefold() in IGNORED_INGEST_NAMES:
        return "ignored_system_folder"
    if path.is_file():
        return "music_album" if is_audio_file(path) else "unknown_type"
    if not path.is_dir():
        return "unknown_type"

    audio_files = [
        candidate
        for candidate in path.rglob("*")
        if candidate.is_file() and is_audio_file(candidate)
    ]
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
    if looks_like_discography_parent(
        path,
        child_audio_folders,
        {str(child): [] for child in child_audio_folders},
    ):
        return "music_discography"
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

        album_summaries.append(
            {
                "source_folder": child.name,
                "artist": artist,
                "album": album,
                "year": year,
                "format": album_format,
                "track_count": len(paths),
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
    metadata = {
        "artist": artist,
        "collection_type": "discography",
        "album_count": len(album_summaries),
        "track_count": len(ingest_files),
        "format_summary": sorted(formats),
        "albums": album_summaries,
        "parent_cleanup": parent_parse,
        "artist_source": artist_source,
        "metadata_quality": "weak" if blocking else "good",
        "metadata_warnings": list(dict.fromkeys(warnings)),
        "confidence": 0.6 if blocking else 1.0,
    }
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
    audio_files = _root_music_audio_files()
    if not audio_files:
        return ScanMusicResult(created=0, skipped_duplicates=0, batches=[])

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

    batches: list[IngestBatch] = []
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

        quality = evaluate_music_album_metadata(album_meta)
        album_meta.update(quality)

        source_path = _release_source_path(sample_path)
        suggested_metadata = build_suggested_metadata(
            source_path,
            track_metadata,
            album_meta,
        )
        warnings = list(album_meta.get("metadata_warnings", []))
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
    )
