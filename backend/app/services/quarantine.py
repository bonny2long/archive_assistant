import json
import shutil
from pathlib import Path

from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.time import configured_timezone, now_utc, serialize_utc
from app.models.archive import IngestBatch


def _safe_name(value: str) -> str:
    safe = "".join(
        character if character not in '<>:"/\\|?*' else "_"
        for character in value
    ).strip(" .")
    return safe or "unknown-item"


def _available_destination(root: Path, source: Path) -> Path:
    safe_name = _safe_name(source.name)
    destination = root / safe_name
    if not destination.exists():
        return destination
    for index in range(1, 1000):
        if source.is_file():
            safe_stem = _safe_name(source.stem)
            name = f"{safe_stem}__duplicate_{index:03d}{source.suffix.lower()}"
        else:
            name = f"{safe_name}__duplicate_{index:03d}"
        candidate = root / name
        if not candidate.exists():
            return candidate
    raise RuntimeError("Could not allocate a safe quarantine destination")


def quarantine_batch(db: Session, batch: IngestBatch) -> Path:
    if (
        batch.status != "needs_quarantine_review"
        or batch.detected_type not in {"unknown_type", "unsupported_file"}
    ):
        raise ValueError("Batch is not eligible for quarantine review")

    root = settings.quarantine_unknown_dir
    root.mkdir(parents=True, exist_ok=True)
    metadata = dict(batch.metadata_json or {})
    moved_at = now_utc()
    grouped_paths = [
        Path(value)
        for value in metadata.get("grouped_loose_files", [])
        if isinstance(value, str)
    ]
    files_moved = []
    folders_moved = []

    if grouped_paths:
        group_root = root / "loose-files"
        timestamp = moved_at.strftime("%Y%m%dT%H%M%SZ")
        destination = _available_destination(
            group_root,
            Path(timestamp),
        )
        destination.mkdir(parents=True, exist_ok=False)
        for source in grouped_paths:
            if not source.exists():
                continue
            if source.resolve().parent != settings.ingest_root.resolve():
                raise ValueError("Grouped quarantine files must be directly inside ingest")
            destination_file = _available_destination(destination, source)
            shutil.move(str(source), str(destination_file))
            files_moved.append(str(destination_file))
    else:
        source = Path(batch.source_path)
        if not source.exists():
            raise FileNotFoundError(f"Source not found: {source}")
        if not source.resolve().is_relative_to(settings.ingest_root.resolve()):
            raise ValueError("Quarantine source must be inside the ingest root")
        destination = _available_destination(root, source)
        source_was_dir = source.is_dir()
        shutil.move(str(source), str(destination))
        if source_was_dir:
            folders_moved.append(str(destination))
        else:
            files_moved.append(str(destination))

    metadata["quarantine_destination"] = str(destination)
    metadata["quarantined_at"] = serialize_utc(moved_at)
    batch.metadata_json = metadata
    batch.suggested_destination = str(destination)
    batch.status = "quarantined"
    batch.updated_at = now_utc()
    db.commit()

    settings.quarantine_reports_dir.mkdir(parents=True, exist_ok=True)
    report = {
        "batch_id": batch.id,
        "source_path": batch.source_path,
        "destination_path": str(destination),
        "detected_type": batch.detected_type,
        "status_before": "needs_quarantine_review",
        "status_after": "quarantined",
        "reason": metadata.get("reason"),
        "moved_at": serialize_utc(moved_at),
        "display_timezone": configured_timezone(),
        "file_count": metadata.get("file_count", 0),
        "folder_count": metadata.get("folder_count", 0),
        "size_bytes": metadata.get("size_bytes", 0),
        "files_moved": files_moved,
        "folders_moved": folders_moved,
    }
    report_timestamp = moved_at.strftime("%Y%m%dT%H%M%SZ")
    (settings.quarantine_reports_dir / f"{report_timestamp}_{batch.id}.json").write_text(
        json.dumps(report, indent=2),
        encoding="utf-8",
    )
    return destination


def restore_quarantined_batch(db: Session, batch: IngestBatch) -> Path:
    if batch.status != "quarantined":
        raise ValueError("Batch is not quarantined")

    metadata = dict(batch.metadata_json or {})
    source = Path(
        metadata.get("quarantine_destination")
        or batch.suggested_destination
        or ""
    )
    if not source.exists():
        raise FileNotFoundError(f"Quarantine source not found: {source}")
    quarantine_root = settings.data_root / "_QUARANTINE"
    if not source.resolve().is_relative_to(quarantine_root.resolve()):
        raise ValueError("Restore source must be inside quarantine")

    original = Path(batch.source_path)
    if not original.resolve().is_relative_to(settings.ingest_root.resolve()):
        raise ValueError("Restore destination must be inside ingest")
    if original.exists():
        raise ValueError(f"Restore destination already exists: {original}")

    original.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(source), str(original))
    metadata["restored_from_quarantine_at"] = serialize_utc(now_utc())
    metadata["restored_to_ingest"] = str(original)
    batch.metadata_json = metadata
    batch.status = "merged"
    batch.updated_at = now_utc()
    db.commit()
    return original
