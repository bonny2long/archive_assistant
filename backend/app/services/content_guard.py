"""Last-line duplicate check by file content, for every media type.

Folder names and metadata can differ for two copies of the same file (one has a
year, the other does not), so name-based checks let both through. This guard
compares the actual bytes (SHA-256) of a batch's media files against

* files already moved into the library by earlier batches (found through the
  move records, so it still works when the file was renamed on the way in), and
* files still waiting in other live batches.

Artwork, subtitles, sidecars and empty files are ignored. Reading is cheap:
candidates are pre-filtered by file size, and a file is only hashed when another
file of exactly the same size exists. Nothing here writes to the database or the
disk; callers decide what to do with the result.
"""

from __future__ import annotations

import os
from collections import defaultdict
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable

from sqlalchemy.orm import Session

from app.core.time import now_utc
from app.models.archive import IngestBatch, IngestFile, MoveAction
from app.services.checksum import file_sha256

DUPLICATE_WARNING_TYPE = "duplicate_content_detected"

CONTENT_EXTENSIONS = frozenset({
    # audio and audiobooks
    ".flac", ".mp3", ".m4a", ".m4b", ".aac", ".ogg", ".opus", ".wav", ".wma",
    ".alac", ".aiff", ".aif", ".ape", ".wv",
    # video
    ".mkv", ".mp4", ".m4v", ".avi", ".mov", ".wmv", ".webm", ".flv", ".mpg",
    ".mpeg", ".ts",
    # books and comics
    ".epub", ".pdf", ".mobi", ".azw3", ".cbz", ".cbr",
})
NON_CONTENT_ROLE_WORDS = (
    "artwork", "subtitle", "sidecar", "poster", "cover", "nfo", "unsupported",
    "unclassified",
)
# A batch in one of these states no longer owns files that count as "already here".
IGNORED_BATCH_STATUSES = frozenset({
    "merged", "rejected", "quarantined", "needs_quarantine_review",
    "discard_approved",
})
MAX_REPORTED = 25
_SIZE_QUERY_CHUNK = 500
_HASH_CACHE_LIMIT = 8192
_hash_cache: dict[tuple[str, int, int], str] = {}


@dataclass(frozen=True)
class ContentDuplicate:
    file_name: str
    size_bytes: int
    sha256: str
    other_batch_id: int
    other_batch_status: str
    other_path: str

    def describe(self) -> str:
        where = (
            "already in the library"
            if self.other_batch_status == "moved"
            else f"also in batch {self.other_batch_id} ({self.other_batch_status})"
        )
        return (
            f"{self.file_name} is identical to {self.other_path}, {where} "
            f"(batch {self.other_batch_id})"
        )


def cached_sha256(path: Path) -> str:
    """SHA-256 of a file, remembered for as long as its path, size and mtime are unchanged."""
    stat = path.stat()
    key = (os.path.normcase(str(path)), stat.st_size, stat.st_mtime_ns)
    cached = _hash_cache.get(key)
    if cached is not None:
        return cached
    digest = file_sha256(path)
    if len(_hash_cache) >= _HASH_CACHE_LIMIT:
        _hash_cache.clear()
    _hash_cache[key] = digest
    return digest


def is_content_file(item: IngestFile) -> bool:
    role = (item.detected_role or "").lower()
    if any(word in role for word in NON_CONTENT_ROLE_WORDS):
        return False
    extension = (item.extension or Path(item.file_name or "").suffix or "").lower()
    if extension and not extension.startswith("."):
        extension = "." + extension
    return extension in CONTENT_EXTENSIONS and int(item.size_bytes or 0) > 0


def _same_path(a: str, b: str) -> bool:
    return os.path.normcase(os.path.abspath(a)) == os.path.normcase(os.path.abspath(b))


def _chunks(values: list[int], size: int) -> Iterable[list[int]]:
    for index in range(0, len(values), size):
        yield values[index:index + size]


def find_content_duplicates(db: Session, batch: IngestBatch) -> list[ContentDuplicate]:
    """Return the files of ``batch`` that already exist, byte for byte, somewhere else.

    A file in another batch that has not moved yet only counts against the batch
    with the higher id, so exactly one of two identical batches is held back and
    the older one can still go through.
    """
    mine = [
        item for item in batch.files
        if is_content_file(item) and Path(item.file_path).exists()
    ]
    if not mine:
        return []

    sizes = sorted({int(item.size_bytes) for item in mine})
    candidates: list[tuple[IngestFile, IngestBatch]] = []
    for chunk in _chunks(sizes, _SIZE_QUERY_CHUNK):
        candidates.extend(
            db.query(IngestFile, IngestBatch)
            .join(IngestBatch, IngestBatch.id == IngestFile.batch_id)
            .filter(
                IngestFile.size_bytes.in_(chunk),
                IngestFile.batch_id != batch.id,
                IngestBatch.status.notin_(IGNORED_BATCH_STATUSES),
            )
            .all()
        )
    by_size: dict[int, list[tuple[IngestFile, IngestBatch]]] = defaultdict(list)
    for other_file, other_batch in candidates:
        if is_content_file(other_file):
            by_size[int(other_file.size_bytes)].append((other_file, other_batch))
    if not by_size:
        return []

    moved_batch_ids = {
        other_batch.id for _, others in by_size.items()
        for _, other_batch in others if other_batch.status == "moved"
    }
    destinations: dict[tuple[int, str], str] = {}
    if moved_batch_ids:
        for action in (
            db.query(MoveAction)
            .filter(
                MoveAction.batch_id.in_(moved_batch_ids),
                MoveAction.status == "completed",
            )
            .all()
        ):
            destinations[(action.batch_id, os.path.normcase(action.source_path))] = (
                action.destination_path
            )

    found: list[ContentDuplicate] = []
    for item in mine:
        my_path = Path(item.file_path)
        my_hash: str | None = None
        for other_file, other_batch in by_size.get(int(item.size_bytes), []):
            if other_batch.status == "moved":
                location = destinations.get(
                    (other_batch.id, os.path.normcase(other_file.file_path))
                )
            else:
                if other_batch.id > batch.id:
                    continue
                location = other_file.file_path
            if not location or not Path(location).is_file():
                continue
            if _same_path(location, str(my_path)):
                continue
            if my_hash is None:
                my_hash = cached_sha256(my_path)
            if cached_sha256(Path(location)) != my_hash:
                continue
            found.append(ContentDuplicate(
                file_name=item.file_name,
                size_bytes=int(item.size_bytes),
                sha256=my_hash,
                other_batch_id=other_batch.id,
                other_batch_status=other_batch.status,
                other_path=str(location),
            ))
            break
    return found


def summarize(duplicates: list[ContentDuplicate]) -> str:
    if not duplicates:
        return ""
    first = duplicates[0]
    extra = f" (and {len(duplicates) - 1} more)" if len(duplicates) > 1 else ""
    return (
        f"Duplicate content: {first.describe()}{extra}. "
        "Nothing was moved. Reject this batch, or remove the other copy first."
    )


def apply_duplicate_state(batch: IngestBatch, duplicates: list[ContentDuplicate]) -> None:
    """Record (or clear) the duplicate warning and alert on the batch metadata."""
    metadata = dict(batch.metadata_json or {})
    had_state = DUPLICATE_WARNING_TYPE in metadata.get("metadata_warnings", []) or any(
        isinstance(value, dict) and value.get("type") == DUPLICATE_WARNING_TYPE
        for value in metadata.get("metadata_alerts", [])
    )
    if not duplicates and not had_state:
        return
    warnings = [
        value for value in metadata.get("metadata_warnings", [])
        if value != DUPLICATE_WARNING_TYPE
    ]
    alerts = [
        value for value in metadata.get("metadata_alerts", [])
        if not (isinstance(value, dict) and value.get("type") == DUPLICATE_WARNING_TYPE)
    ]
    if duplicates:
        warnings.append(DUPLICATE_WARNING_TYPE)
        alerts.append({
            "type": DUPLICATE_WARNING_TYPE,
            "message": summarize(duplicates),
            "duplicate_count": len(duplicates),
            "duplicates": [asdict(item) for item in duplicates[:MAX_REPORTED]],
            "detected_at": now_utc().isoformat(),
        })
    metadata["metadata_warnings"] = list(dict.fromkeys(warnings))
    metadata["metadata_alerts"] = alerts
    batch.metadata_json = metadata


def refresh_duplicate_state(db: Session, batch: IngestBatch) -> list[ContentDuplicate]:
    """Re-check a batch, update its warning/alert to match, and return what was found."""
    duplicates = find_content_duplicates(db, batch)
    apply_duplicate_state(batch, duplicates)
    return duplicates
