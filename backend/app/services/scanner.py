from collections import defaultdict
from pathlib import Path
from sqlalchemy.orm import Session
from app.core.config import settings
from app.models.archive import IngestBatch, IngestFile
from app.services.checksum import file_sha256
from app.services.music_metadata import (
    album_group_key,
    evaluate_music_album_metadata,
    extract_music_metadata,
    build_suggested_metadata,
    is_audio_file,
    suggest_music_destination,
)
from app.services.report_writer import write_json_report


def scan_music_ingest(db: Session) -> list[IngestBatch]:
    settings.ingest_music_dir.mkdir(parents=True, exist_ok=True)
    
    # 1. Recursive discovery
    audio_files = [p for p in settings.ingest_music_dir.rglob("*") if p.is_file() and is_audio_file(p)]
    if not audio_files: return []

    # 2. Extract metadata and group
    groups = defaultdict(list)
    file_metadata = {}

    for path in audio_files:
        # Check for existing
        checksum = file_sha256(path)
        existing = db.query(IngestFile).filter((IngestFile.checksum == checksum) | (IngestFile.file_path == str(path))).first()
        if existing: continue

        meta = extract_music_metadata(path)
        file_metadata[str(path)] = meta
        
        # KEY: Force grouping by a key we know will be consistent
        key = album_group_key(meta)
        groups[key].append(path)

    batches = []
    # 3. Create batches
    for key, paths in groups.items():
        if not paths: continue
        
        # Sample for batch-level data
        sample_path = paths[0]
        sample_meta = file_metadata[str(sample_path)]
        
        # Build detected album metadata. Suggestions remain separate until confirmed.
        discs = {m.get("discnumber", 1) for p, m in file_metadata.items() if Path(p) in paths}
        track_metadata = [file_metadata[str(path)] for path in paths]
        album_meta = {
            "artist": sample_meta["albumartist"],
            "album": sample_meta["album"],
            "year": sample_meta["date"],
            "genre": sample_meta.get("genre"),
            "disc_count": len(discs),
            "track_count": len(paths),
            "format": "FLAC" if "flac" in sample_meta.get("extension", "") else "MP3",
            "tracks": []
        }

        # Evaluate quality
        quality_res = evaluate_music_album_metadata(album_meta)
        album_meta.update(quality_res)

        # Determine initial status
        status = "pending_review"
        if quality_res["metadata_quality"] == "weak":
            status = "needs_metadata_review"
        elif quality_res["metadata_quality"] == "broken":
            status = "metadata_recovery"

        # Source path: parent of paths[0] (or parent of parent if multi-disc)
        source_path = sample_path.parent
        if len(discs) > 1: source_path = source_path.parent
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

        batch = IngestBatch(
            source_kind="manual-drop",
            source_path=str(source_path),
            detected_type="music_album",
            status=status,
            confidence=quality_res["confidence"],
            suggested_destination=str(destination),
            suggested_metadata=suggested_metadata,
            metadata_json=album_meta
        )
        db.add(batch)
        db.flush()

        for path in paths:
            meta = file_metadata[str(path)]
            ingest_file = IngestFile(
                batch_id=batch.id,
                file_path=str(path),
                file_name=path.name,
                extension=path.suffix.lower(),
                size_bytes=path.stat().st_size,
                checksum=file_sha256(path),
                detected_role="music_track",
                metadata_json=meta
            )
            db.add(ingest_file)
            
            album_meta["tracks"].append({
                "title": meta["title"],
                "track_number": meta["tracknumber"],
                "disc_number": meta["discnumber"]
            })

        db.commit()
        db.refresh(batch)
        
        write_json_report(settings.reports_dir, batch.id, album_meta)
        batches.append(batch)

    return batches
