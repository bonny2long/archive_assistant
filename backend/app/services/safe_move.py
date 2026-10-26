"""Moves that rename and nothing else.

``shutil.move`` falls back to copying and then deleting whenever a rename fails, which is exactly
what happens when the source and the destination are on different filesystems (for example two
ZFS datasets, two Docker mounts, or two drives). A copy-then-delete is slow, is not atomic, and a
crash halfway leaves a partial file in the library. Archive Assistant never wants that, so every
move here is a rename. If one cannot be a rename, it fails before touching anything.
"""

from __future__ import annotations

import errno
import os
from pathlib import Path

# Windows reports "different disk drive" as winerror 17 (ERROR_NOT_SAME_DEVICE).
_WINERROR_NOT_SAME_DEVICE = 17

CROSS_DEVICE_MESSAGE = (
    "The source and the destination are on different filesystems. Archive Assistant only moves by "
    "rename and never copies then deletes. Keep the ingest folders and the libraries on one "
    "filesystem (one dataset, one mount)."
)


class CrossDeviceMoveError(OSError):
    """A move would have to copy because source and destination are on different filesystems."""


def _nearest_existing(path: Path) -> Path | None:
    current = Path(path)
    while True:
        if os.path.lexists(current):
            return current
        if current.parent == current:
            return None
        current = current.parent


def device_of(path: Path) -> int | None:
    """The filesystem a path is on, or, if it does not exist yet, the one it would be created on."""
    existing = _nearest_existing(Path(path))
    if existing is None:
        return None
    try:
        return os.stat(existing).st_dev
    except OSError:
        return None


def same_device(first: Path, second: Path) -> bool:
    """True when both paths are on the same filesystem. Unknown counts as the same, not as a block."""
    a, b = device_of(first), device_of(second)
    return a is None or b is None or a == b


def _is_cross_device(exc: OSError) -> bool:
    return exc.errno == errno.EXDEV or getattr(exc, "winerror", None) == _WINERROR_NOT_SAME_DEVICE


def move_by_rename(source: str | os.PathLike, destination: str | os.PathLike) -> None:
    """Rename ``source`` to ``destination``. Never copies, and never replaces anything that exists."""
    if os.path.lexists(destination):
        raise FileExistsError(errno.EEXIST, "Destination already exists", str(destination))
    try:
        os.rename(source, destination)
    except OSError as exc:
        if _is_cross_device(exc):
            raise CrossDeviceMoveError(exc.errno, f"{CROSS_DEVICE_MESSAGE} ({source} -> {destination})") from exc
        raise
