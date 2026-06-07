import json
import shutil
from datetime import datetime
from pathlib import Path
from sqlalchemy.orm import Session, selectinload
from app.core.config import settings
from app.models.archive import ArchiveItem, IngestBatch, MoveAction
from app.services.music_metadata import music_track_filename


def move_approved_batches(db: Session) -> tuple[int, list[str]]:
    approved = (
        db.query(IngestBatch)
        .options(selectinload(IngestBatch.files))
        .filter(IngestBatch.status == "approved")
        .all()
    )
    moved = 0
    errors: list[str] = []

    for batch in approved:
        moved_files = []
        failed_files = []
        album_meta = batch.metadata_json or {}

        try:
            if (
                album_meta.get("metadata_quality") in {"weak", "broken"}
                and not batch.metadata_confirmed
            ):
                batch.status = "needs_metadata_review"
                batch.updated_at = datetime.utcnow()
                db.commit()
                errors.append(f"Batch {batch.id}: weak metadata must be confirmed before move")
                continue

            destination_dir = Path(batch.suggested_destination or "")
            if not destination_dir:
                raise ValueError("Missing suggested destination")

            destination_dir.mkdir(parents=True, exist_ok=True)

            disc_count = album_meta.get("disc_count", 1)

            for ingest_file in batch.files:
                source = Path(ingest_file.file_path)
                if not source.exists():
                    failed_files.append(f"Source not found: {source}")
                    continue

                meta = ingest_file.metadata_json or {}
                new_name = music_track_filename(meta, ingest_file.extension, disc_count)
                destination_file = destination_dir / new_name

                if destination_file.exists():
                    stem = destination_file.stem
                    suffix = destination_file.suffix
                    counter = 1
                    while destination_file.exists():
                        destination_file = destination_dir / f"{stem}_duplicate-{counter:03d}{suffix}"
                        counter += 1

                action = MoveAction(
                    batch_id=batch.id,
                    source_path=str(source),
                    destination_path=str(destination_file),
                    status="running",
                )
                db.add(action)
                db.flush()

                try:
                    shutil.move(str(source), str(destination_file))
                    action.status = "completed"
                    action.completed_at = datetime.utcnow()
                    moved_files.append(str(destination_file))
                except Exception as exc:
                    failed_files.append(f"Failed to move {source}: {exc}")
                    action.status = "failed"
                    action.error_message = str(exc)
                    db.flush()
                    continue

            if failed_files or not moved_files:
                batch.status = "move_failed" if failed_files else "moved"
            else:
                batch.status = "moved"

            batch.updated_at = datetime.utcnow()
            db.flush()

            _write_move_log(batch, album_meta, moved_files, failed_files)

            for dest_path in moved_files:
                dest = Path(dest_path)
                metadata = batch.metadata_json or {}
                item = ArchiveItem(
                    media_type="music",
                    title=metadata.get("album") or dest.parent.name,
                    creator=metadata.get("artist") or metadata.get("album_artist"),
                    year=str(metadata.get("year") or "")[:4] or None,
                    primary_genre=metadata.get("genre"),
                    source_kind=batch.source_kind,
                    final_path=str(dest),
                    metadata_status="basic",
                )
                db.add(item)

            db.commit()
            if moved_files:
                moved += 1

        except Exception as exc:
            db.rollback()
            errors.append(f"Batch {batch.id}: {exc}")
            batch.status = "move_failed"
            batch.updated_at = datetime.utcnow()
            db.add(batch)
            db.commit()

    return moved, errors


def _write_move_log(batch: IngestBatch, album_meta: dict, moved_files: list[str], failed_files: list[str]) -> None:
    destination_dir = Path(batch.suggested_destination or "")
    metadata_dir = destination_dir / "metadata"
    metadata_dir.mkdir(exist_ok=True)
    (metadata_dir / f"batch-{batch.id}-move-log.json").write_text(
        json.dumps(
            {
                "batch_id": batch.id,
                "media_type": "music_album",
                "track_count": album_meta.get("track_count", len(moved_files)),
                "source_paths": [str(f.file_path) for f in batch.files],
                "destination_path": str(destination_dir),
                "moved_files": moved_files,
                "failed_files": failed_files,
                "status": "completed" if not failed_files else "partial",
                "moved_at": datetime.utcnow().isoformat(),
                "album_metadata": album_meta,
            },
            indent=2,
            default=str,
        ),
        encoding="utf-8",
    )
