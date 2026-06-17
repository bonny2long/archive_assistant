"""Bounded checks for v2.063 explicit unknown-value acceptance."""

from __future__ import annotations

import os
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
os.environ["DEBUG"] = "true"
sys.path.insert(0, str(ROOT / "backend"))

from app.services import audiobook_metadata  # noqa: E402
from app.services.review_state import build_review_state  # noqa: E402


def issue_types(metadata: dict, key: str) -> set[str]:
    return {
        str(item.get("type"))
        for item in metadata.get(key, [])
        if isinstance(item, dict)
    }


def check_book_acceptance() -> None:
    metadata = build_review_state("book", {
        "review_type": "book_collection",
        "metadata_quality": "weak",
        "book_items": [{
            "source_file": "Hunters of Dune.epub",
            "include": True,
            "title": "Hunters of Dune",
            "author": "Unknown Author",
            "year": None,
            "format": "EPUB",
            "accepted_unknown_author": True,
            "accepted_unknown_year": False,
            "lookup_later": True,
            "destination_preview": (
                "Books/Library/Unknown Author/Unknown Year - "
                "Hunters of Dune/Hunters of Dune.epub"
            ),
        }],
    })

    blockers = issue_types(metadata, "blocking_review_items")
    warnings = issue_types(metadata, "non_blocking_review_items")
    assert "book_item_missing_author" not in blockers, metadata
    assert "book_author_unknown_accepted" in warnings, metadata
    assert "book_lookup_later" in warnings, metadata
    assert metadata["metadata_quality"] == "accepted_with_unknowns"


def check_audiobook_acceptance() -> None:
    metadata = build_review_state("audiobook", {
        "metadata_quality": "weak",
        "author": "Unknown Author",
        "title": "Unidentified Lecture",
        "year": None,
        "narrator": None,
        "accepted_unknown_author": True,
        "accepted_unknown_year": True,
        "accepted_unknown_narrator": True,
        "lookup_later": True,
        "artwork_count": 1,
        "generic_audio_tag_count": 3,
    })

    blockers = issue_types(metadata, "blocking_review_items")
    warnings = issue_types(metadata, "non_blocking_review_items")
    assert not blockers, metadata
    assert "audiobook_author_unknown_accepted" in warnings, metadata
    assert "audiobook_year_unknown_accepted" in warnings, metadata
    assert "audiobook_narrator_unknown_accepted" in warnings, metadata
    assert "audiobook_lookup_later" in warnings, metadata
    assert metadata["metadata_quality"] == "accepted_with_unknowns"


def check_multibook_stays_one_batch() -> None:
    source = Path("Star Wars Darth Bane Trilogy")
    audio = [
        source / "Star Wars Darth Bane Path Of Destruction (Book 1).mp3",
        source / "Star Wars Darth Bane Rule Of Two (Book 2).mp3",
        source / "Star Wars Darth Bane Dynasty Of Evil (Book 3).mp3",
    ]
    preview = audiobook_metadata.detect_audiobook_collection(source, audio)
    assert preview["audiobook_collection_type"] == "multi_book_trilogy"
    assert len(preview["contained_books"]) == 3


def check_manifest_contract() -> None:
    mover_source = (
        ROOT / "backend" / "app" / "services" / "mover.py"
    ).read_text(encoding="utf-8")
    for flag in (
        "accepted_unknown_author",
        "accepted_unknown_year",
        "accepted_unknown_narrator",
        "lookup_later",
    ):
        assert flag in mover_source, flag


def main() -> None:
    check_book_acceptance()
    check_audiobook_acceptance()
    check_multibook_stays_one_batch()
    check_manifest_contract()
    print("v2.063 review acceptance flag checks passed")


if __name__ == "__main__":
    main()
