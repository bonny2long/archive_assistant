from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.archive import IngestBatch, IngestFile
from app.services.checksum import file_sha256
from app.services.music_metadata import (
    album_group_key,
    build_suggested_metadata,
    evaluate_music_album_metadata,
    extract_music_metadata,
    is_audio_file,
    suggest_music_destination,
)
from app.services.report_writer import write_json_report


@dataclass(frozen=True)
class ScanMusicResult:
    created: int
    skipped_duplicates: int
    batches: list[IngestBatch]


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


def scan_music_ingest(db: Session) -> ScanMusicResult:
    settings.ingest_music_dir.mkdir(parents=True, exist_ok=True)
    audio_files = [
        path
        for path in settings.ingest_music_dir.rglob("*")
        if path.is_file() and is_audio_file(path)
    ]
    if not audio_files:
        return ScanMusicResult(created=0, skipped_duplicates=0, batches=[])

    groups: dict[str, list[Path]] = defaultdict(list)
    file_metadata: dict[str, dict] = {}
    file_checksums: dict[str, str] = {}

    for path in audio_files:
        metadata = extract_music_metadata(path)
        file_metadata[str(path)] = metadata
        file_checksums[str(path)] = file_sha256(path)
        groups[album_group_key(metadata)].append(path)

    batches: list[IngestBatch] = []
    skipped_duplicates = 0

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
            "artist": sample_meta["albumartist"],
            "album": sample_meta["album"],
            "year": sample_meta["date"],
            "genre": sample_meta.get("genre"),
            "disc_count": len(discs),
            "track_count": len(paths),
            "format": "FLAC" if "flac" in sample_meta.get("extension", "") else "MP3",
            "tracks": [],
        }

        quality = evaluate_music_album_metadata(album_meta)
        album_meta.update(quality)

        source_path = sample_path.parent
        if len(discs) > 1:
            source_path = source_path.parent
        suggested_metadata = build_suggested_metadata(
            source_path,
            track_metadata,
            album_meta,
        )
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

        for path in new_paths:
            metadata = file_metadata[str(path)]
            db.add(
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
            album_meta["tracks"].append(
                {
                    "title": metadata["title"],
                    "track_number": metadata["tracknumber"],
                    "disc_number": metadata["discnumber"],
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
