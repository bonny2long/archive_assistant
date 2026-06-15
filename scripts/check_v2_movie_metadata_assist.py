"""Bounded synthetic checks for v2.066 movie metadata assist."""

from pathlib import Path

from app.services.move_manifest import (
    ARCHIVE_ASSISTANT_VERSION,
    _accepted_unknowns,
    _confirmed_metadata,
    _lookup_later,
    _summary,
)
from app.services.review_state import build_review_state
from app.services.video_metadata import (
    build_movie_metadata_candidates,
    parse_movie_name,
)


def main() -> None:
    release = "Mortal.Kombat.II.2026.1080p.WEB-DL.x265-GROUP.mkv"
    parsed = parse_movie_name(release)
    assert parsed["title"] == "Mortal Kombat II"
    assert parsed["year"] == "2026"
    assert parsed["edition"] is None
    assert parsed["resolution"] == "1080P"
    assert parsed["source"] == "WEB-DL"
    assert parsed["release_tags_removed"] == [
        "1080p", "WEB-DL", "x265", "GROUP",
    ]

    candidates, items = build_movie_metadata_candidates(
        Path("Mortal.Kombat.II.2026.1080p.WEB-DL.x265-GROUP"),
        [Path(release)],
    )
    assert candidates["title"][0]["value"] == "Mortal Kombat II"
    assert candidates["year"][0]["value"] == "2026"
    assert candidates["format"][0]["value"] == "MKV"
    assert items[0]["release_cleanup"]["removed_tokens"][-1] == "GROUP"

    missing = build_review_state("video_movie", {
        "title": "Unknown Movie",
        "year": None,
        "video_file_count": 1,
        "metadata_warnings": ["movie_year_missing"],
    })
    assert any(
        item["type"] == "movie_title_missing"
        for item in missing["blocking_review_items"]
    )
    assert any(
        item["type"] == "movie_year_missing"
        for item in missing["non_blocking_review_items"]
    )

    accepted = build_review_state("video_movie", {
        "title": "Unknown Movie",
        "year": None,
        "accepted_unknown_title": True,
        "accepted_unknown_year": True,
        "video_file_count": 1,
        "metadata_warnings": ["movie_year_missing"],
    })
    assert accepted["blocking_review_items"] == []

    collection = build_review_state("video_movie", {
        "review_type": "movie_collection",
        "title": "Example Collection",
        "video_file_count": 2,
        "movie_items": [
            {
                "source_file": "Known (2020).mkv",
                "title": "Known",
                "year": "2020",
                "include": True,
            },
            {
                "source_file": "Mystery.mkv",
                "title": "",
                "year": None,
                "include": True,
                "accepted_unknown_title": True,
                "accepted_unknown_year": True,
                "lookup_later": True,
            },
        ],
        "metadata_warnings": [],
    })
    assert collection["blocking_review_items"] == []

    metadata = {
        "review_type": "movie",
        "title": "Mortal Kombat II",
        "year": "2026",
        "edition": None,
        "resolution": "1080P",
        "source": "WEB-DL",
        "format": "MKV",
        "video_file_count": 1,
        "accepted_unknown_title": False,
        "accepted_unknown_year": False,
        "lookup_later": True,
        "release_cleanup": {
            "original_name": release,
            "removed_tokens": parsed["release_tags_removed"],
        },
    }
    assert ARCHIVE_ASSISTANT_VERSION == "v2.066B"
    assert _confirmed_metadata("video_movie", metadata)["source"] == "WEB-DL"
    assert _accepted_unknowns("video_movie", metadata) == {
        "title": False,
        "year": False,
        "items": [],
    }
    assert _lookup_later("video_movie", metadata)
    summary = _summary("video_movie", metadata, {
        "files_moved": [{}],
        "artwork_moved": [{}],
        "subtitles_moved": [{}],
        "sidecars_ignored": [{}],
        "failed_moves": [],
    })
    assert summary["poster_count"] == 1
    assert summary["subtitle_count"] == 1
    assert summary["files_moved_count"] == 3

    print("v2.066 movie metadata assist checks passed")


if __name__ == "__main__":
    main()
