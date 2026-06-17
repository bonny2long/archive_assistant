"""Bounded checks for v2.062 audiobook artwork and set previews."""

from __future__ import annotations

import os
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
os.environ["DEBUG"] = "true"
sys.path.insert(0, str(ROOT / "backend"))

from app.services import audiobook_metadata  # noqa: E402


def main() -> None:
    artwork = Path(
        "Star Wars The Old Republic Revan/"
        "Star Wars The Old Republic Revan.jpg"
    )
    assert audiobook_metadata.is_audiobook_artwork(artwork)
    assert audiobook_metadata.is_audiobook_artwork(Path("poster.webp"))
    assert not audiobook_metadata.is_audiobook_artwork(Path("notes.txt"))

    trilogy_source = Path("Star Wars Darth Bane Trilogy")
    trilogy_audio = [
        trilogy_source / "Star Wars Darth Bane Dynasty Of Evil (Book 3) [Unabridged].mp3",
        trilogy_source / "Star Wars Darth Bane Path Of Destruction (Book 1) [Unabridged].mp3",
        trilogy_source / "Star Wars Darth Bane Rule Of Two (Book 2) [Unabridged].mp3",
    ]
    preview = audiobook_metadata.detect_audiobook_collection(
        trilogy_source,
        trilogy_audio,
    )
    assert preview["audiobook_collection_type"] == "multi_book_trilogy"
    assert preview["contained_books"] == [
        {"series_index": "1", "title": "Path Of Destruction"},
        {"series_index": "2", "title": "Rule Of Two"},
        {"series_index": "3", "title": "Dynasty Of Evil"},
    ], preview

    print("v2.062 audiobook artwork and multi-book checks passed")


if __name__ == "__main__":
    main()
