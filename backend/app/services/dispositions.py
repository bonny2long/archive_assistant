"""Durable disposition records for quarantine, discard, restore, and reject.

Archive Assistant never deletes anything. When a human decides what should
happen to an item that will not be moved into a final library, this module
writes a JSON record under ``_REPORTS/archive-assistant/dispositions`` so the
separate Cleaner service has on-disk evidence to act on later.

Records are append-only: each decision writes a new file and nothing is
rewritten. The newest record for a batch is its current disposition.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from app.core.config import settings
from app.core.time import now_utc, serialize_utc
from app.core.version import ARCHIVE_ASSISTANT_VERSION


DISPOSITION_VERSION = "v1"
DISPOSITION_ACTIONS = {
    "quarantined",
    "restored",
    "discard_approved",
    "discard_revoked",
    "rejected",
}
INVENTORY_FILE_LIMIT = 5000


def relative_to_data_root(path: Path) -> str:
    try:
        return path.resolve().relative_to(settings.data_root.resolve()).as_posix()
    except (OSError, ValueError):
        return path.as_posix()


def build_inventory(path: Path) -> dict:
    """Describe what exists at ``path`` right now.

    Cleaner compares this against the live tree before acting, so a record
    whose contents changed after the decision can be refused.
    """
    files: list[dict] = []
    folder_count = 0
    total_bytes = 0
    truncated = False
    if path.is_file():
        stat = path.stat()
        files.append({
            "relative_path": path.name,
            "size_bytes": stat.st_size,
            "modified_at": serialize_utc(
                datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc)
            ),
        })
        total_bytes = stat.st_size
    elif path.is_dir():
        for candidate in sorted(path.rglob("*"), key=lambda p: str(p).casefold()):
            if candidate.is_dir():
                folder_count += 1
                continue
            if not candidate.is_file():
                continue
            stat = candidate.stat()
            total_bytes += stat.st_size
            if len(files) >= INVENTORY_FILE_LIMIT:
                truncated = True
                continue
            files.append({
                "relative_path": candidate.relative_to(path).as_posix(),
                "size_bytes": stat.st_size,
                "modified_at": serialize_utc(
                    datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc)
                ),
            })
    file_count = (
        len(files)
        if not truncated
        else sum(1 for item in path.rglob("*") if item.is_file())
    )
    return {
        "exists": path.exists(),
        "kind": "file" if path.is_file() else "directory" if path.is_dir() else "missing",
        "file_count": file_count,
        "folder_count": folder_count,
        "total_bytes": total_bytes,
        "files": files,
        "files_truncated": truncated,
    }


def build_file_list_inventory(paths: list[Path], root: Path) -> dict:
    """Inventory an explicit list of files, relative to ``root``."""
    files: list[dict] = []
    total_bytes = 0
    for path in sorted(paths, key=lambda p: str(p).casefold()):
        if not path.is_file():
            continue
        stat = path.stat()
        total_bytes += stat.st_size
        try:
            relative = path.relative_to(root).as_posix()
        except ValueError:
            relative = path.name
        files.append({
            "relative_path": relative,
            "size_bytes": stat.st_size,
            "modified_at": serialize_utc(
                datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc)
            ),
        })
    return {
        "exists": bool(files),
        "kind": "file_list",
        "file_count": len(files),
        "folder_count": 0,
        "total_bytes": total_bytes,
        "files": files,
        "files_truncated": False,
    }


def write_disposition_record(
    *,
    batch,
    action: str,
    target_path: Path,
    reason: str | None = None,
    status_before: str | None = None,
    extra: dict | None = None,
    inventory: dict | None = None,
) -> Path:
    """Write one immutable disposition record and return its path."""
    if action not in DISPOSITION_ACTIONS:
        raise ValueError(f"Unknown disposition action: {action}")
    created_at = now_utc()
    record = {
        "record_type": "archive_assistant_disposition",
        "disposition_version": DISPOSITION_VERSION,
        "archive_assistant_version": ARCHIVE_ASSISTANT_VERSION,
        "created_at": serialize_utc(created_at),
        "action": action,
        "batch_id": batch.id,
        "detected_type": batch.detected_type,
        "status_before": status_before,
        "status_after": batch.status,
        "decided_by": "local-user",
        "reason": reason,
        "original_source_path": relative_to_data_root(Path(batch.source_path)),
        "current_path": relative_to_data_root(target_path),
        "inventory": inventory if inventory is not None else build_inventory(target_path),
        **(extra or {}),
    }
    directory = settings.dispositions_dir
    directory.mkdir(parents=True, exist_ok=True)
    stamp = created_at.strftime("%Y%m%dT%H%M%S%fZ")
    path = directory / f"{stamp}_{batch.id}_{action}.json"
    counter = 1
    while path.exists():
        path = directory / f"{stamp}_{batch.id}_{action}_{counter}.json"
        counter += 1
    path.write_text(json.dumps(record, indent=2), encoding="utf-8")
    return path
