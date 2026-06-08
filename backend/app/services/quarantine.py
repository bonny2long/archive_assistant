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

    source = Path(batch.source_path)
    if not source.exists():
        raise FileNotFoundError(f"Source not found: {source}")
    if not source.resolve().is_relative_to(settings.ingest_root.resolve()):
        raise ValueError("Quarantine source must be inside the ingest root")

    root = settings.quarantine_unknown_dir
    root.mkdir(parents=True, exist_ok=True)
    destination = _available_destination(root, source)
    shutil.move(str(source), str(destination))

    metadata = dict(batch.metadata_json or {})
    metadata["quarantine_destination"] = str(destination)
    moved_at = now_utc()
    metadata["quarantined_at"] = serialize_utc(moved_at)
    batch.metadata_json = metadata
    batch.suggested_destination = str(destination)
    batch.status = "quarantined"
    batch.updated_at = now_utc()
    db.commit()

    settings.quarantine_reports_dir.mkdir(parents=True, exist_ok=True)
    report = {
        "batch_id": batch.id,
        "source_path": str(source),
        "quarantine_path": str(destination),
        "detected_type": batch.detected_type,
        "status_before": "needs_quarantine_review",
        "status_after": "quarantined",
        "reason": metadata.get("reason"),
        "moved_at": serialize_utc(moved_at),
        "display_timezone": configured_timezone(),
        "file_count": metadata.get("file_count", 0),
        "folder_count": metadata.get("folder_count", 0),
        "size_bytes": metadata.get("size_bytes", 0),
    }
    timestamp = moved_at.strftime("%Y%m%dT%H%M%SZ")
    (settings.quarantine_reports_dir / f"quarantine_{batch.id}_{timestamp}.json").write_text(
        json.dumps(report, indent=2),
        encoding="utf-8",
    )
    return destination
