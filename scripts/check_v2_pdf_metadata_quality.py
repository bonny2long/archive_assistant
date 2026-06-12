"""Bounded checks for v2.062 PDF metadata quality guards."""

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
    canonicalize_author_name,
    is_garbage_document_title,
    make_candidate,
    normalize_metadata_text,
)
from app.services.title_display import destination_title  # noqa: E402


def main() -> None:
    assert METADATA_ASSIST_VERSION == "v2.062"
    assert normalize_metadata_text("Bad\x00  title\nvalue") == "Bad title value"

    assert is_garbage_document_title("tmpezE58S\x00")
    assert is_garbage_document_title("tmp12345")
    assert is_garbage_document_title("document")
    assert not is_garbage_document_title(
        "Atomic Habits: An Easy & Proven Way to Build Good Habits & Break Bad Ones"
    )
    assert not is_garbage_document_title("The Ultimate Prepper's Guide")

    candidate = make_candidate(
        field="title",
        value="tmpezE58S\x00",
        source="pdf_document_info_title",
        source_label="PDF document metadata",
        confidence=0.92,
    )
    assert candidate is not None
    assert candidate["value"] == "tmpezE58S"
    assert candidate["ignored"] is True
    assert candidate["confidence_label"] == "low"
    assert "garbage PDF document title" in candidate["notes"]

    parsed = book_metadata.parse_book_name(
        "The Pocket Guide to Prepper K.pdf"
    )
    assert parsed["title"] == "The Pocket Guide to Prepper K", parsed

    original_collect = book_metadata.collect_book_files
    original_reader = book_metadata.read_pdf_metadata
    book_metadata.collect_book_files = lambda source: {
        "books": [Path("The Pocket Guide to Prepper K.pdf")],
        "artwork": [],
        "sidecars": [],
        "other": [],
    }
    book_metadata.read_pdf_metadata = lambda path, source_labels=None: (
        {
            "title": "tmpezE58S\x00",
            "year": "2018",
        },
        [],
    )
    try:
        metadata = book_metadata.build_single_book_metadata(
            Path("The Pocket Guide to Prepper K.pdf"),
            Path("Books"),
        )
    finally:
        book_metadata.collect_book_files = original_collect
        book_metadata.read_pdf_metadata = original_reader
    assert metadata["title"] == "The Pocket Guide to Prepper K", metadata
    assert metadata["author"] == "Unknown Author", metadata
    assert metadata["year"] == "2018", metadata
    assert metadata["candidate_runtime"][
        "pdf_garbage_candidates_blocked"
    ] == 1

    book_metadata.read_pdf_metadata = lambda path, source_labels=None: (
        {
            "title": "Useful Title",
            "author": "Smith, Rachel",
            "year": "2020",
        },
        [],
    )
    book_metadata.collect_book_files = lambda source: {
        "books": [Path("Useful Title.pdf")],
        "artwork": [],
        "sidecars": [],
        "other": [],
    }
    try:
        canonical_metadata = book_metadata.build_single_book_metadata(
            Path("Useful Title.pdf"),
            Path("Books"),
        )
    finally:
        book_metadata.collect_book_files = original_collect
        book_metadata.read_pdf_metadata = original_reader
    assert canonical_metadata["author"] == "Rachel Smith"
    assert canonical_metadata["candidate_runtime"][
        "author_names_canonicalized"
    ] == 1

    assert canonicalize_author_name("Smith, Rachel") == "Rachel Smith"
    assert canonicalize_author_name("Brocklesby, Ray") == "Ray Brocklesby"
    assert canonicalize_author_name("Dunton, Cory") == "Cory Dunton"
    assert canonicalize_author_name(
        "Footprint Press, Small"
    ) == "Footprint Press, Small"
    assert canonicalize_author_name(
        "Kristin Celello,Hanan Kholoussy"
    ) == "Kristin Celello,Hanan Kholoussy"
    assert canonicalize_author_name(
        "Harriet Lerner, Ph.D."
    ) == "Harriet Lerner, Ph.D."

    assert destination_title(
        "Atomic Habits: An Easy & Proven Way to Build Good Habits & Break Bad Ones"
    ) == "Atomic Habits"
    assert destination_title(
        "The Complete Prepper's Guide to Survival:"
    ) == "The Complete Prepper's Guide to Survival"
    assert destination_title(
        "Prepper’s Long Term Survival Guide: A Comprehensive Beginner’s Guide "
        "to learn the Realms from A-Z of Self-Sufficient Living"
    ) == "Prepper’s Long Term Survival Guide"

    print("v2.062 PDF metadata quality checks passed")


if __name__ == "__main__":
    main()
