import json
import shutil
from pathlib import Path

from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.time import now_utc, serialize_utc
from app.models.archive import IngestBatch


def _available_destination(root: Path, source: Path) -> Path:
    destination = root / source.name
    if not destination.exists():
        return destination
    for index in range(1, 1000):
        if source.is_file():
            name = f"{source.stem}__duplicate-{index:03d}{source.suffix}"
        else:
            name = f"{source.name}__duplicate-{index:03d}"
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

    root = (
        settings.quarantine_unknown_dir
        if batch.detected_type == "unknown_type"
        else settings.quarantine_unsupported_dir
    )
    root.mkdir(parents=True, exist_ok=True)
    destination = _available_destination(root, source)
    shutil.move(str(source), str(destination))

    metadata = dict(batch.metadata_json or {})
    metadata["quarantine_destination"] = str(destination)
    metadata["quarantined_at"] = serialize_utc(now_utc())
    batch.metadata_json = metadata
    batch.suggested_destination = str(destination)
    batch.status = "quarantined"
    batch.updated_at = now_utc()
    db.commit()

    settings.quarantine_reports_dir.mkdir(parents=True, exist_ok=True)
    report = {
        "batch_id": batch.id,
        "source_path": str(source),
        "destination_path": str(destination),
        "detected_type": batch.detected_type,
        "reason": metadata.get("reason"),
        "status": "completed",
        "created_at": serialize_utc(now_utc()),
    }
    (settings.quarantine_reports_dir / f"batch-{batch.id}-quarantine.json").write_text(
        json.dumps(report, indent=2),
        encoding="utf-8",
    )
    return destination
