"""Bounded checks for the v2 read-only metadata candidate foundation."""

from __future__ import annotations

import os
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
os.environ["DEBUG"] = "true"
sys.path.insert(0, str(ROOT / "backend"))

from app.services.audiobook_metadata import (  # noqa: E402
    build_audiobook_metadata_candidates,
)
from app.services.book_metadata import build_book_metadata_candidates  # noqa: E402
from app.services.metadata_candidates import (  # noqa: E402
    add_candidate,
    confidence_label,
    make_candidate,
)


def main() -> None:
    assert confidence_label(0.9) == "high"
    assert confidence_label(0.7) == "medium"
    assert confidence_label(0.4) == "low"
    assert make_candidate("title", "", "test", "Test", 0.9) is None

    candidates: dict[str, list[dict]] = {}
    candidate = make_candidate(
        "title",
        "Dune",
        "filename",
        "Filename",
        0.7,
    )
    add_candidate(candidates, candidate)
    add_candidate(candidates, candidate)
    assert len(candidates["title"]) == 1
    assert candidates["title"][0]["applied"] is False

    manual_book = {
        "title": "Manual Book Title",
        "author": "Manual Author",
    }
    book_candidates, artwork_candidates = build_book_metadata_candidates(
        Path("Dune - Frank Herbert (1965).epub"),
        Path("Dune - Frank Herbert (1965).epub"),
        [],
    )
    assert manual_book == {
        "title": "Manual Book Title",
        "author": "Manual Author",
    }
    assert book_candidates["title"][0]["value"] == "Dune"
    assert book_candidates["author"][0]["value"] == "Frank Herbert"
    assert artwork_candidates == []

    manual_audiobook = {
        "title": "Manual Audio Title",
        "author": "Manual Audio Author",
    }
    audiobook_candidates, chapters, artwork = (
        build_audiobook_metadata_candidates(
            Path("Dune - Frank Herbert (1965) Audiobook"),
            [Path("Dune - Frank Herbert (1965) Audiobook.mp3")],
            [],
        )
    )
    assert manual_audiobook == {
        "title": "Manual Audio Title",
        "author": "Manual Audio Author",
    }
    assert audiobook_candidates["title"][0]["value"] == "Dune"
    assert audiobook_candidates["author"][0]["value"] == "Frank Herbert"
    assert chapters == []
    assert artwork == []

    print("v2 metadata candidate checks passed")


if __name__ == "__main__":
    main()
