"""Bounded manifest-shape checks for v2.066 movies."""

from app.services.move_manifest import (
    ARCHIVE_ASSISTANT_VERSION,
    _accepted_unknowns,
    _confirmed_metadata,
    _lookup_later,
    _summary,
)


def main() -> None:
    metadata = {
        "review_type": "movie_collection",
        "collection_title": "Example Trilogy",
        "movie_items": [
            {
                "source_file": "Example One (2020).mkv",
                "title": "Example One",
                "year": "2020",
                "format": "MKV",
                "include": True,
            },
            {
                "source_file": "Example Two.mkv",
                "title": "Example Two",
                "year": None,
                "format": "MKV",
                "include": True,
                "accepted_unknown_year": True,
                "lookup_later": True,
            },
        ],
    }
    assert ARCHIVE_ASSISTANT_VERSION == "v2.066"
    confirmed = _confirmed_metadata("video_movie", metadata)
    assert len(confirmed["items"]) == 2
    accepted = _accepted_unknowns("video_movie", metadata)
    assert accepted["items"][0]["accepted_unknown_year"] is True
    assert _lookup_later("video_movie", metadata)[0]["scope"] == "movie"
    summary = _summary("video_movie", metadata, {
        "files_moved": [{}, {}],
        "artwork_moved": [{}],
        "subtitles_moved": [{}],
        "sidecars_ignored": [],
        "failed_moves": [],
    })
    assert summary["movie_count"] == 2
    assert summary["year_range"] == "2020"
    assert summary["files_moved_count"] == 4
    print("v2.066 movie move manifest checks passed")


if __name__ == "__main__":
    main()
