"""Bounded checks for v2.062 book series and year parsing."""

from __future__ import annotations

import os
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
os.environ["DEBUG"] = "true"
sys.path.insert(0, str(ROOT / "backend"))

from app.services import book_metadata  # noqa: E402


def main() -> None:
    false_series = book_metadata.parse_book_name(
        "1-2-3 Magic - 3-Step Discipline for Calm, Effective, "
        "and Happy Parenting.epub"
    )
    assert false_series["series"] is None, false_series
    assert false_series["series_index"] is None, false_series

    for name in (
        "5-Minute Self-Discipline Exercises.epub",
        "8 Keys to Stress Management.epub",
        "31 Days to Masculinity.epub",
        "50 Great Lessons from Life.epub",
        "51 Creative Ideas for Marriage Mentors.epub",
        "4,000 Questions for Getting to Know Anyone and Everyone.epub",
    ):
        parsed = book_metadata.parse_book_name(name)
        assert parsed["series_index"] is None, (name, parsed)

    dune = book_metadata.parse_book_name(
        "1 - Dune - Frank Herbert (1965).epub"
    )
    assert dune["title"] == "Dune", dune
    assert dune["author"] == "Frank Herbert", dune
    assert dune["year"] == "1965", dune

    series = book_metadata.parse_book_name(
        "Great Schools of Dune 2.5 - Red Plague.epub"
    )
    assert series["title"] == "Red Plague", series
    assert series["series"] == "Great Schools of Dune", series
    assert series["series_index"] == "2.5", series

    original_extract = book_metadata.extract_epub_metadata
    book_metadata.extract_epub_metadata = lambda path: {
        "title": "Dune",
        "author": "Frank Herbert",
        "date": "2010",
    }
    try:
        candidates, _ = book_metadata.build_book_metadata_candidates(
            Path("1 - Dune - Frank Herbert (1965).epub"),
            Path("1 - Dune - Frank Herbert (1965).epub"),
            [],
        )
    finally:
        book_metadata.extract_epub_metadata = original_extract
    preferred = book_metadata.preferred_candidate_value(
        candidates,
        "year",
        None,
    )
    assert preferred == "1965", candidates["year"]
    filename_year = next(
        item for item in candidates["year"] if item["source"] == "filename"
    )
    assert (
        "filename publication year preferred over package metadata year"
        in filename_year["notes"]
    )

    print("v2.062 series and year guardrail checks passed")


if __name__ == "__main__":
    main()
