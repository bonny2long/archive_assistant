"""Bounded checks for v2.061 book collection intelligence."""

from __future__ import annotations

import os
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
os.environ["DEBUG"] = "true"
sys.path.insert(0, str(ROOT / "backend"))

from app.services import audiobook_metadata, book_metadata  # noqa: E402
from app.services.metadata_candidates import METADATA_ASSIST_VERSION  # noqa: E402


def main() -> None:
    assert METADATA_ASSIST_VERSION == "v2.061"

    for title in (
        "1-2-3 Magic.epub",
        "5-Minute Self-Discipline Exercises.epub",
        "4,000 Questions for Getting to Know Anyone and Everyone.epub",
        "31 Days to Masculinity.epub",
        "50 Great Lessons from Life.epub",
        "51 Creative Ideas for Marriage Mentors.epub",
        "8 Keys to Stress Management.epub",
    ):
        parsed = book_metadata.parse_book_name(title)
        assert parsed["series_index"] is None, (title, parsed)

    source = Path("Collection")
    title = "The Prepper's Guide to Foraging"
    epub = source / f"{title}.epub"
    pdf = source / f"{title}.pdf"
    mobi = source / f"{title}.mobi"
    artwork = source / "Covers" / f"The Prepper\u2019s Guide to Foraging.jpg"
    second_pdf = source / "5-Minute Self-Discipline Exercises.pdf"
    files = {
        "books": [epub, pdf, second_pdf],
        "alternates": [mobi],
        "artwork": [artwork, source / "Covers" / "unmatched.jpg"],
        "sidecars": [source / f"{title}.opf", source / "notes.txt"],
        "other": [],
    }
    groups, summary = book_metadata.build_book_collection_groups(source, files)

    assert len(groups) == 2
    prepper = next(group for group in groups if group["primary"] == epub)
    assert prepper["matched_artwork"] == {
        "file": "Covers/The Prepper\u2019s Guide to Foraging.jpg",
        "match_method": "normalized_basename",
        "confidence": 0.95,
    }
    assert {entry["format"] for entry in prepper["alternate_formats"]} == {
        "PDF",
        "MOBI",
    }
    assert summary["primary_book_count"] == 2
    assert summary["epub_count"] == 1
    assert summary["pdf_count"] == 1
    assert summary["mobi_duplicate_count"] == 1
    assert summary["opf_sidecar_count"] == 1
    assert summary["artwork_count"] == 2
    assert summary["matched_artwork_count"] == 1
    assert summary["unmatched_artwork_count"] == 1
    assert summary["ignored_sidecar_count"] == 2
    assert summary["duplicate_format_groups"] == 1

    candidates, _ = book_metadata.build_book_metadata_candidates(
        Path(
            "Study Skills - Reducing Student Life Stress and "
            "Improving Academic Performance.pdf"
        ),
        Path(
            "Study Skills - Reducing Student Life Stress and "
            "Improving Academic Performance.pdf"
        ),
        [],
    )
    visible_authors = [
        candidate
        for candidate in candidates.get("author", [])
        if not candidate.get("ignored")
    ]
    assert all(
        candidate["value"]
        != "Reducing Student Life Stress and Improving Academic Performance"
        for candidate in visible_authors
    )

    original_extract = audiobook_metadata.extract_audio_metadata
    audiobook_metadata.extract_audio_metadata = lambda path: {
        "title": "Unknown Album",
        "album": "Unknown Album",
    }
    try:
        _, _, _, audio_summary = (
            audiobook_metadata.build_audiobook_metadata_candidates(
                Path("Star Wars The Old Republic Revan"),
                [Path("Star Wars The Old Republic Revan/001.mp3")],
                [],
            )
        )
    finally:
        audiobook_metadata.extract_audio_metadata = original_extract
    assert audio_summary["generic_audio_tag_count"] >= 1

    print("v2.061 collection intelligence checks passed")


if __name__ == "__main__":
    main()
