from __future__ import annotations

import re


ILLEGAL_PATH_CHARS_RE = re.compile(r'[<>:"/\\|?*]')


def clean_display_title(value: str) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def destination_title(value: str, max_length: int = 120) -> str:
    """Return a readable filesystem title while preserving metadata elsewhere."""
    display = clean_display_title(value)
    main_title, separator, _ = display.partition(":")
    main_title = main_title.rstrip(" .,:;-")
    if separator and len(display) > 100 and 8 <= len(main_title) <= max_length:
        return ILLEGAL_PATH_CHARS_RE.sub("_", main_title)

    title = ILLEGAL_PATH_CHARS_RE.sub("_", display).rstrip(" .,:;-")
    if len(title) <= max_length:
        return title or "Unknown Title"

    shortened = title[:max_length].rstrip()
    if " " in shortened:
        shortened = shortened.rsplit(" ", 1)[0]
    return shortened.rstrip(" .,:;-") or "Unknown Title"
