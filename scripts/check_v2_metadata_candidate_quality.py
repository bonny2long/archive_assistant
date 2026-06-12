"""Targeted quality checks for v2 metadata suggestions."""

from __future__ import annotations

import os
import sys
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
os.environ["DEBUG"] = "true"
sys.path.insert(0, str(ROOT / "backend"))

from app.services import audiobook_metadata  # noqa: E402
from app.services.book_metadata import (  # noqa: E402
    build_book_metadata_candidates,
    parse_book_name,
)
from app.services.metadata_candidates import (  # noqa: E402
    METADATA_ASSIST_VERSION,
    make_candidate,
    preferred_candidate_value,
    should_hide_candidate,
)
from app.schemas.archive import BatchSummary  # noqa: E402


def main() -> None:
    bad_album = "Unknown Album (11/19/2011 3:14:38 PM)"
    candidate = make_candidate(
        "title",
        bad_album,
        "audio_tag_title",
        "Embedded audio tags",
        0.95,
    )
    assert candidate is not None
    assert candidate["ignored"] is True
    assert candidate["confidence_label"] == "low"
    assert should_hide_candidate("title", "Track 1", "audio_tag_title")
    assert preferred_candidate_value(
        {"title": [candidate]},
        "title",
        "Unknown Title",
    ) == "Unknown Title"
    summary = BatchSummary(
        id=1,
        detected_type="audiobook",
        status="needs_metadata_review",
        confidence=0.7,
        metadata_quality="weak",
        metadata_warnings=[],
        metadata_candidates={"title": [candidate]},
        item_count=1,
        created_at=datetime.now(timezone.utc),
    )
    serialized = summary.model_dump(mode="json")
    assert serialized["metadata_candidates"]["title"][0]["ignored"] is True

    original_extract = audiobook_metadata.extract_audio_metadata
    audiobook_metadata.extract_audio_metadata = lambda path: {
        "title": bad_album,
        "chapter_title": "Track 1",
        "track_number": "1",
    }
    try:
        candidates, chapters, _, summary = (
            audiobook_metadata.build_audiobook_metadata_candidates(
                Path("Star Wars The Old Republic Revan"),
                [
                    Path("Star Wars The Old Republic Revan")
                    / "Disc 1"
                    / "01 Track 1.mp3",
                    Path("Star Wars The Old Republic Revan")
                    / "Disc 2"
                    / "01 Track 1.mp3",
                ],
                [],
            )
        )
    finally:
        audiobook_metadata.extract_audio_metadata = original_extract

    visible_titles = [
        item
        for item in candidates["title"]
        if not item.get("ignored")
    ]
    assert visible_titles[0]["value"] == "Star Wars The Old Republic Revan"
    assert all(item["value"] != bad_album for item in visible_titles)
    assert chapters == []
    assert summary["generic_audio_tag_count"] == 4
    assert summary["detected_disc_count"] == 2

    parsed = parse_book_name("@SoftSkills101 - Atomic Habits.pdf")
    assert parsed["title"] == "Atomic Habits", parsed
    assert parsed["author"] == "Unknown Author", parsed
    title_like = parse_book_name(
        "131 Creative Conversations For Couples - "
        "Christ-honoring questions to deepen your relationship.pdf"
    )
    assert title_like["author"] == "Unknown Author", title_like

    item_candidates, _ = build_book_metadata_candidates(
        Path("@SoftSkills101 - Atomic Habits.pdf"),
        Path("@SoftSkills101 - Atomic Habits.pdf"),
        [],
    )
    collection_item = {
        "source_file": "@SoftSkills101 - Atomic Habits.pdf",
        "metadata_candidates": item_candidates,
    }
    assert collection_item["metadata_candidates"]["title"][0]["value"] == (
        "Atomic Habits"
    )
    assert "author" not in collection_item["metadata_candidates"]

    scanner_source = (
        ROOT / "backend/app/services/scanner.py"
    ).read_text(encoding="utf-8")
    assert 'item_metadata["metadata_candidates"] = item_candidates' in (
        scanner_source
    )
    assert "metadata_assist_version" in scanner_source
    assert METADATA_ASSIST_VERSION == "v2.057"

    print("v2 metadata candidate quality checks passed")


if __name__ == "__main__":
    main()
