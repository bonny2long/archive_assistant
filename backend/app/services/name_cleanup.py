"""Small name clean-ups shared by folder and file-name parsers."""

from __future__ import annotations

import re

# Windows adds " - Copy" or " - Copy (2)" when a folder or file is copied
# into the same place. It is never part of the real artist, album, or title.
WINDOWS_COPY_SUFFIX_RE = re.compile(
    r"\s+-\s+copy(?:\s*\(\d+\))?(?=(?:\.[A-Za-z0-9]{1,5})?$)",
    re.IGNORECASE,
)


def strip_windows_copy_suffix(value: str) -> str:
    """Remove a trailing Windows copy marker, keeping any file extension."""
    if not isinstance(value, str):
        return value
    return WINDOWS_COPY_SUFFIX_RE.sub("", value)
