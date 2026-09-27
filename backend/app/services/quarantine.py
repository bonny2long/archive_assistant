"""Quarantine lifecycle for items Archive Assistant cannot file normally.

Lifecycle:

    needs_quarantine_review --quarantine--> quarantined
    quarantined --restore--> needs_quarantine_review (back in ingest)
    quarantined --discard--> discard_approved (still on disk)
    discard_approved --undo discard--> quarantined

Archive Assistant never deletes. Every decision writes a disposition record
(see ``dispositions.py``) that the separate Cleaner service may act on later.
"""

import json
import shutil
from pathlib import Path

from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.time import configured_timezone, now_utc, serialize_utc
from app.models.archive import IngestBatch
from app.services.dispositions import (
    build_file_list_inventory,
    write_disposition_record,
)


QUARANTINE_REVIEW_TYPES = {"unknown_type", "unsupported_file"}
DISCARD_REASON_MIN_LENGTH = 3


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


def _quarantine_root() -> Path:
    return settings.data_root / "_QUARANTINE"


def _append_history(metadata: dict, event: str, **values) -> None:
    history = list(metadata.get("quarantine_history") or [])
    history.append({"event": event, "at": serialize_utc(now_utc()), **values})
    metadata["quarantine_history"] = history


def _grouped_items(metadata: dict, destination: Path) -> list[dict]:
    """Return original/quarantine path pairs for a grouped loose-file batch."""
    items = metadata.get("quarantine_items")
    if isinstance(items, list) and items:
        return [
            {"original": str(item["original"]), "quarantined": str(item["quarantined"])}
            for item in items
            if isinstance(item, dict)
            and item.get("original")
            and item.get("quarantined")
        ]
    # Rows quarantined before item mapping existed: files kept their names.
    return [
        {
            "original": value,
            "quarantined": str(destination / Path(value).name),
        }
        for value in metadata.get("grouped_loose_files", [])
        if isinstance(value, str)
    ]


def quarantine_batch(db: Session, batch: IngestBatch) -> Path:
    if (
        batch.status != "needs_quarantine_review"
        or batch.detected_type not in QUARANTINE_REVIEW_TYPES
    ):
        raise ValueError("Batch is not eligible for quarantine review")

    root = (
        settings.quarantine_unsupported_dir
        if batch.detected_type == "unsupported_file"
        else settings.quarantine_unknown_dir
    )
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
    quarantine_items = []

    if grouped_paths:
        for source in grouped_paths:
            if source.exists() and (
                source.resolve().parent != settings.ingest_root.resolve()
            ):
                raise ValueError("Grouped quarantine files must be directly inside ingest")
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
            destination_file = _available_destination(destination, source)
            shutil.move(str(source), str(destination_file))
            files_moved.append(str(destination_file))
            quarantine_items.append({
                "original": str(source),
                "quarantined": str(destination_file),
            })
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
    if quarantine_items:
        metadata["quarantine_items"] = quarantine_items
    else:
        metadata.pop("quarantine_items", None)
    _append_history(metadata, "quarantined", destination=str(destination))
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
    write_disposition_record(
        batch=batch,
        action="quarantined",
        target_path=destination,
        reason=metadata.get("reason"),
        status_before="needs_quarantine_review",
    )
    return destination


def _quarantined_location(batch: IngestBatch) -> Path:
    metadata = dict(batch.metadata_json or {})
    recorded = (
        metadata.get("quarantine_destination")
        or batch.suggested_destination
        or ""
    )
    if not recorded:
        raise FileNotFoundError("Quarantine location is not recorded for this batch")
    location = Path(recorded)
    if not location.exists():
        raise FileNotFoundError(f"Quarantine source not found: {location}")
    if not location.resolve().is_relative_to(_quarantine_root().resolve()):
        raise ValueError("Quarantine location must be inside quarantine")
    return location


def _refresh_counts(metadata: dict, path: Path) -> None:
    if path.is_file():
        metadata["file_count"] = 1
        metadata["folder_count"] = 0
        metadata["size_bytes"] = path.stat().st_size
        return
    files = [item for item in path.rglob("*") if item.is_file()]
    metadata["file_count"] = len(files)
    metadata["folder_count"] = sum(1 for item in path.rglob("*") if item.is_dir())
    metadata["size_bytes"] = sum(item.stat().st_size for item in files)


def restore_quarantined_batch(db: Session, batch: IngestBatch) -> Path:
    """Move a quarantined item back into ingest and back into review.

    The batch returns to ``needs_quarantine_review``. Nothing is rescanned
    here; the next explicit Scan ingest re-classifies the restored item, so
    anything the user fixed while it sat in quarantine is picked up then.
    """
    if batch.status != "quarantined":
        raise ValueError("Batch is not quarantined")

    source = _quarantined_location(batch)
    metadata = dict(batch.metadata_json or {})
    ingest_root = settings.ingest_root.resolve()
    grouped = bool(metadata.get("grouped_loose_files"))
    restored_inventory = None

    if grouped:
        moves: list[tuple[Path, Path]] = []
        for pair in _grouped_items(metadata, source):
            quarantined = Path(pair["quarantined"])
            original = Path(pair["original"])
            if not quarantined.exists():
                continue
            if not quarantined.resolve().is_relative_to(source.resolve()):
                raise ValueError("Grouped quarantine file is outside its group folder")
            if original.resolve().parent != ingest_root:
                raise ValueError("Grouped restore target must be directly inside ingest")
            if original.exists():
                raise ValueError(f"Restore destination already exists: {original}")
            moves.append((quarantined, original))
        if not moves:
            raise FileNotFoundError("No quarantined files remain to restore")
        for quarantined, original in moves:
            shutil.move(str(quarantined), str(original))
        try:
            # Removes only the group folder Archive Assistant created, and
            # only when it is now empty. Anything else stays in place.
            source.rmdir()
        except OSError:
            pass
        restored_paths = [original for _, original in moves]
        restored_inventory = build_file_list_inventory(
            restored_paths, settings.ingest_root
        )
        metadata["grouped_loose_files"] = [str(path) for path in restored_paths]
        metadata["file_count"] = len(restored_paths)
        metadata["size_bytes"] = sum(path.stat().st_size for path in restored_paths)
        target = settings.ingest_root
    else:
        original = Path(batch.source_path)
        if not original.resolve().is_relative_to(ingest_root):
            raise ValueError("Restore destination must be inside ingest")
        if original.exists():
            raise ValueError(f"Restore destination already exists: {original}")
        original.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(source), str(original))
        _refresh_counts(metadata, original)
        target = original

    _append_history(
        metadata,
        "restored",
        from_path=str(source),
        to_path=str(target),
    )
    for key in (
        "quarantine_destination",
        "quarantined_at",
        "quarantine_items",
        "discard_approved_at",
        "discard_reason",
    ):
        metadata.pop(key, None)
    metadata["restored_from_quarantine_at"] = serialize_utc(now_utc())
    metadata["restored_to_ingest"] = str(target)
    metadata["recommended_action"] = (
        "Restored from quarantine. Run Scan ingest to re-classify it, "
        "or move it back to quarantine."
    )
    batch.metadata_json = metadata
    batch.suggested_destination = None
    batch.status = "needs_quarantine_review"
    batch.updated_at = now_utc()
    db.commit()

    write_disposition_record(
        batch=batch,
        action="restored",
        target_path=target,
        status_before="quarantined",
        inventory=restored_inventory,
    )
    return target


def discard_quarantined_batch(
    db: Session,
    batch: IngestBatch,
    reason: str,
) -> Path:
    """Record a human decision that a quarantined item is not needed.

    Nothing is deleted. The item stays in quarantine with status
    ``discard_approved`` and a disposition record that Cleaner may act on
    after its own waiting period. The decision can be undone until then.
    """
    if batch.status != "quarantined":
        raise ValueError("Only quarantined items can be discarded")
    cleaned_reason = (reason or "").strip()
    if len(cleaned_reason) < DISCARD_REASON_MIN_LENGTH:
        raise ValueError("A discard reason is required")

    location = _quarantined_location(batch)
    metadata = dict(batch.metadata_json or {})
    metadata["discard_approved_at"] = serialize_utc(now_utc())
    metadata["discard_reason"] = cleaned_reason
    _append_history(metadata, "discard_approved", reason=cleaned_reason)
    batch.metadata_json = metadata
    batch.status = "discard_approved"
    batch.updated_at = now_utc()
    db.commit()

    write_disposition_record(
        batch=batch,
        action="discard_approved",
        target_path=location,
        reason=cleaned_reason,
        status_before="quarantined",
    )
    return location


def revoke_discard(db: Session, batch: IngestBatch) -> Path:
    """Undo a discard decision while the item still exists in quarantine."""
    if batch.status != "discard_approved":
        raise ValueError("Batch is not marked for discard")

    location = _quarantined_location(batch)
    metadata = dict(batch.metadata_json or {})
    metadata.pop("discard_approved_at", None)
    previous_reason = metadata.pop("discard_reason", None)
    _append_history(metadata, "discard_revoked", previous_reason=previous_reason)
    batch.metadata_json = metadata
    batch.status = "quarantined"
    batch.updated_at = now_utc()
    db.commit()

    write_disposition_record(
        batch=batch,
        action="discard_revoked",
        target_path=location,
        status_before="discard_approved",
    )
    return location


def record_rejection(db: Session, batch: IngestBatch, status_before: str) -> Path:
    """Write the disposition record for a rejected batch.

    Rejected files stay where they are. The record lets Cleaner see the
    decision, and lists other batches that share the same source folder so
    Cleaner can refuse to treat a shared folder as rejected.
    """
    metadata = dict(batch.metadata_json or {})
    grouped = [
        Path(value)
        for value in metadata.get("grouped_loose_files", [])
        if isinstance(value, str)
    ]
    shared = [
        row.id
        for row in db.query(IngestBatch)
        .filter(
            IngestBatch.id != batch.id,
            IngestBatch.source_path == batch.source_path,
            IngestBatch.status != "merged",
        )
        .all()
    ]
    inventory = (
        build_file_list_inventory(grouped, settings.ingest_root)
        if grouped
        else None
    )
    return write_disposition_record(
        batch=batch,
        action="rejected",
        target_path=Path(batch.source_path),
        status_before=status_before,
        inventory=inventory,
        extra={
            "scope": "grouped_loose_files" if grouped else "source_path",
            "shared_source_batch_ids": shared,
        },
    )
