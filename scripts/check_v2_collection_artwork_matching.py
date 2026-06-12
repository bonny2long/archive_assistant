"""Bounded regression for v2.062 collection cover matching."""

from __future__ import annotations

import os
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
os.environ["DEBUG"] = "true"
sys.path.insert(0, str(ROOT / "backend"))

from app.services.book_metadata import build_book_collection_groups  # noqa: E402


def main() -> None:
    source = Path("Prepper Collection")
    title = "The Prepper's Guide to Foraging"
    groups, summary = build_book_collection_groups(source, {
        "books": [source / f"{title}.epub"],
        "alternates": [],
        "artwork": [source / "Covers" / f"The Prepper\u2019s Guide to Foraging.jpg"],
        "sidecars": [],
        "other": [],
    })
    assert groups[0]["matched_artwork"] == {
        "file": "Covers/The Prepper\u2019s Guide to Foraging.jpg",
        "match_method": "normalized_basename",
        "confidence": 0.95,
    }
    assert summary["matched_artwork_count"] == 1
    assert summary["unmatched_artwork_count"] == 0
    print("v2.062 collection artwork matching checks passed")


if __name__ == "__main__":
    main()
