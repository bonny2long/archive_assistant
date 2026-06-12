"""Bounded checks for v2.062 metadata parser guardrails."""

from __future__ import annotations

import os
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
os.environ["DEBUG"] = "true"
sys.path.insert(0, str(ROOT / "backend"))

from app.services import audiobook_metadata, book_metadata  # noqa: E402
from app.services.book_metadata import (  # noqa: E402
    build_single_book_metadata,
    parse_book_name,
)
from app.services.metadata_candidates import (  # noqa: E402
    METADATA_ASSIST_VERSION,
    make_candidate,
    preferred_candidate_value,
)


def assert_book(
    source: str,
    *,
    title: str,
    author: str = "Unknown Author",
    year: str | None = None,
) -> None:
    parsed = parse_book_name(source)
    assert parsed["title"] == title, parsed
    assert parsed["author"] == author, parsed
    assert parsed.get("year") == year, parsed


def main() -> None:
    assert METADATA_ASSIST_VERSION == "v2.062"

    assert_book(
        "@SoftSkills101 - Atomic Habits.pdf",
        title="Atomic Habits",
    )
    assert_book(
        "@SomeUploader - Book Title.epub",
        title="Book Title",
    )
    assert_book(
        "[Uploader] Book Title.pdf",
        title="Book Title",
    )
    assert_book(
        "UploaderName_ Book Title.pdf",
        title="Book Title",
    )
    assert_book(
        "52 Prepper Projects - A Proje.epub",
        title="52 Prepper Projects",
    )
    assert_book(
        "Countdown To Preparedness - T.epub",
        title="Countdown To Preparedness",
    )
    assert_book(
        "Prepper Guns - Firearms, Ammo.epub",
        title="Prepper Guns",
    )
    assert_book(
        "Prepper's Food Storage - 101 .epub",
        title="Prepper's Food Storage 101",
    )
    assert_book(
        "Winter Survival - 20 Tips To .epub",
        title="Winter Survival - 20 Tips To",
    )
    assert_book(
        "Prepper Collection - Prepper's Hacks Box Set.epub",
        title="Prepper Collection - Prepper's Hacks Box Set",
    )
    assert_book(
        "Book 1 - Dune (1965).epub",
        title="Dune",
        year="1965",
    )
    parsed_series = parse_book_name(
        "Dune Saga 01 - Dune - Frank Herbert (1965).epub"
    )
    assert parsed_series["series"] == "Dune Saga", parsed_series
    assert parsed_series["series_index"] == "01", parsed_series
    assert_book(
        "Dune - Frank Herbert (1965).epub",
        title="Dune",
        author="Frank Herbert",
        year="1965",
    )

    generic_album = "Unknown Album (11/19/2011 3:04:25 PM)"
    candidate = make_candidate(
        "title",
        generic_album,
        "audio_tag_title",
        "Embedded audio tags",
        0.88,
    )
    assert candidate is not None
    assert candidate["ignored"] is True
    assert candidate["confidence"] <= 0.35
    assert candidate["confidence_label"] == "low"
    assert "generic embedded tag" in candidate["notes"]
    assert preferred_candidate_value(
        {"title": [candidate]},
        "title",
        "Star Wars The Old Republic Revan",
    ) == "Star Wars The Old Republic Revan"

    book_file = Path("@SoftSkills101 - Atomic Habits.pdf")
    original_collect_books = book_metadata.collect_book_files
    original_extract_pdf = book_metadata.extract_pdf_metadata
    book_metadata.collect_book_files = lambda source: {
        "books": [book_file],
        "artwork": [],
        "sidecars": [],
        "other": [],
    }
    book_metadata.extract_pdf_metadata = lambda path: {}
    try:
        built_book = build_single_book_metadata(
            book_file,
            Path("Books"),
        )
    finally:
        book_metadata.collect_book_files = original_collect_books
        book_metadata.extract_pdf_metadata = original_extract_pdf
    assert built_book["metadata_assist_version"] == "v2.062"
    assert built_book["title"] == "Atomic Habits"
    assert built_book["author"] == "Unknown Author"
    assert built_book["candidate_runtime"][
            "candidate_filter_active"
    ] is True

    original_extract = audiobook_metadata.extract_audio_metadata
    audiobook_metadata.extract_audio_metadata = lambda path: {
        "title": generic_album,
        "chapter_title": "Track 1",
    }
    try:
        candidates, _, _, summary = (
            audiobook_metadata.build_audiobook_metadata_candidates(
                Path("Star Wars The Old Republic Revan"),
                [Path("Star Wars The Old Republic Revan/01 Track 1.mp3")],
                [],
            )
        )
    finally:
        audiobook_metadata.extract_audio_metadata = original_extract
    assert all(
        item.get("ignored")
        for item in candidates["title"]
        if item["value"] == generic_album
    )
    assert summary["generic_audio_tag_count"] == 2

    original_collect_audio = audiobook_metadata.collect_audiobook_files
    audiobook_metadata.collect_audiobook_files = lambda source: {
        "audio": [
            Path("Star Wars The Old Republic Revan/01 Track 1.mp3"),
        ],
        "artwork": [],
        "sidecars": [],
        "other": [],
    }
    audiobook_metadata.extract_audio_metadata = lambda path: {
        "title": generic_album,
        "chapter_title": "Track 1",
    }
    try:
        built_audiobook = audiobook_metadata.build_audiobook_metadata(
            Path("Star Wars The Old Republic Revan"),
            Path("Audiobooks"),
        )
    finally:
        audiobook_metadata.collect_audiobook_files = original_collect_audio
        audiobook_metadata.extract_audio_metadata = original_extract
    assert built_audiobook["metadata_assist_version"] == "v2.062"
    assert built_audiobook["title"] == "Star Wars The Old Republic Revan"
    assert built_audiobook["author"] == "Unknown Author"
    assert built_audiobook["candidate_runtime"][
        "generic_audio_tags_hidden"
    ] == 2

    scanner_source = (
        ROOT / "backend/app/services/scanner.py"
    ).read_text(encoding="utf-8")
    assert scanner_source.count(
        '"metadata_assist_version": METADATA_ASSIST_VERSION'
    ) >= 3

    print("v2.062 metadata parser guardrail checks passed")


if __name__ == "__main__":
    main()
