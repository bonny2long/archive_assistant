"""Recognise disc markers at the end of album, book, and folder names.

Multi-disc releases are often tagged "Dune Disc 1", "Album (Disc 2)", or
"The Wall (1)" instead of carrying one album name plus a disc-number tag.
Grouping on those raw names splits one release into one batch per disc.
"""

from __future__ import annotations

import re
from typing import Any

DISC_FOLDER_RE = re.compile(r"^(?:cd|disc|disk|part)\s*0*\d+\b", re.IGNORECASE)

# A disc marker at the END of a name, after real text: "Dune Disc 1",
# "Album - CD 2", "Album (Disc 3)", "Album [CD4]". An explicit disc word is
# enough evidence on its own.
TRAILING_DISC_WORD_RE = re.compile(
    r"^(?P<base>.*?\w.*?)[\s._,:-]*[\(\[]?\s*(?:cd|disc|disk)[\s._-]*0*(?P<disc>\d{1,2})\s*[\)\]]?\s*$",
    re.IGNORECASE,
)
# A bare number in brackets at the end: "The Wall (1)". Only treated as a disc
# when the file's own disc-number tag agrees and it sits in a disc folder.
TRAILING_BARE_DISC_RE = re.compile(
    r"^(?P<base>.*?\w.*?)\s*[\(\[]\s*0*(?P<disc>\d{1,2})\s*[\)\]]\s*$",
)

def is_disc_folder_name(name: str | None) -> bool:
    """True for "CD 1" / "Disc 2" and for names ending in a disc word."""
    text = (name or "").strip()
    if not text:
        return False
    return bool(DISC_FOLDER_RE.match(text) or TRAILING_DISC_WORD_RE.match(text))


def split_disc_suffix(
    value: str | None,
    *,
    disc_tag: Any = None,
    folder_name: str | None = None,
) -> tuple[str | None, int | None]:
    """Split a trailing disc marker off an album/book name.

    Returns ``(base_name, disc_number)``, or ``(value, None)`` when the ending
    is not clearly a disc marker. Bare "(N)" endings need two agreeing pieces
    of evidence: the disc-number tag equals N and the file is in a disc folder
    for disc N.
    """
    text = str(value).strip() if value is not None else ""
    if not text:
        return value, None
    match = TRAILING_DISC_WORD_RE.match(text)
    if match:
        base = match.group("base").strip(" ._,:-")
        if base:
            return base, int(match.group("disc"))
    match = TRAILING_BARE_DISC_RE.match(text)
    if match:
        disc = int(match.group("disc"))
        tag_text = str(disc_tag or "").split("/")[0].strip()
        tag_disc = int(tag_text) if tag_text.isdigit() else None
        folder = (folder_name or "").strip()
        folder_match = re.search(r"(?:cd|disc|disk)[\s._-]*0*(\d{1,2})\s*[\)\]]?\s*$", folder, re.IGNORECASE)
        folder_disc = int(folder_match.group(1)) if folder_match else None
        base = match.group("base").strip(" ._,:-")
        if base and tag_disc == disc and folder_disc == disc:
            return base, disc
    return text, None
