"""Bounded checks for v2.062 generic embedded book values."""

from __future__ import annotations

import os
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
os.environ["DEBUG"] = "true"
sys.path.insert(0, str(ROOT / "backend"))

from app.services import book_metadata  # noqa: E402
from app.services.metadata_candidates import (  # noqa: E402
    METADATA_ASSIST_VERSION,
    is_generic_book_metadata_value,
)


def main() -> None:
    assert METADATA_ASSIST_VERSION == "v2.066"
    for value in (
        "[No data]", "No data", "N/A", "Unknown", "Unknown Title",
        "Untitled", "Document", "Microsoft Word - Document", "Title",
    ):
        assert is_generic_book_metadata_value(value), value

    source = Path(
        "Attraction Explained - The Science of How We Form Relationships.epub"
    )
    original_collect = book_metadata.collect_book_files
    original_extract = book_metadata.extract_epub_metadata
    book_metadata.collect_book_files = lambda path: {
        "books": [source],
        "alternates": [],
        "artwork": [],
        "sidecars": [],
        "other": [],
    }
    book_metadata.extract_epub_metadata = lambda path: {
        "title": "[No data]",
        "author": "N/A",
        "date": "2016",
    }
    try:
        metadata = book_metadata.build_single_book_metadata(
            source,
            Path("Books"),
        )
    finally:
        book_metadata.collect_book_files = original_collect
        book_metadata.extract_epub_metadata = original_extract

    assert metadata["title"] == (
        "Attraction Explained - The Science of How We Form Relationships"
    ), metadata
    assert metadata["author"] == "Unknown Author", metadata
    assert metadata["year"] == "2016", metadata
    ignored_titles = [
        candidate
        for candidate in metadata["metadata_candidates"]["title"]
        if candidate["value"] == "[No data]"
    ]
    assert ignored_titles and ignored_titles[0]["ignored"] is True
    assert ignored_titles[0]["confidence"] == 0.2
    assert "generic embedded book metadata ignored" in ignored_titles[0]["notes"]

    print("v2.062 generic metadata value checks passed")


if __name__ == "__main__":
    main()
