"""Bounded checks for v2.065 music metadata assist.

This script uses synthetic metadata only. It does not scan, reset, move, or
write files in the real data tree.
"""

from pathlib import Path

from app.services.move_manifest import (
    ARCHIVE_ASSISTANT_VERSION,
    _accepted_unknowns,
    _confirmed_metadata,
    _lookup_later,
    _summary,
)
from app.services.music_metadata import build_music_metadata_candidates
from app.services.review_state import build_review_state


def main() -> None:
    tracks = [
        {
            "albumartist": "Various Artists",
            "artist": "Lil Wayne",
            "album": "Starring In Mardi Gras Bootleg",
            "date": "2008",
            "genre": "Hip-Hop",
            "title": "Track 01",
            "tracknumber": "1",
            "discnumber": "1",
        },
        {
            "albumartist": "Various Artists",
            "artist": "Lil Wayne",
            "album": "Starring In Mardi Gras Bootleg",
            "date": "2008",
            "genre": "Hip-Hop",
            "title": "A Real Song",
            "tracknumber": "2",
            "discnumber": "1",
        },
    ]
    candidates, track_candidates = build_music_metadata_candidates(
        Path("DJ Cinema & Lil Wayne - Starring In Mardi Gras Bootleg (2008)"),
        tracks,
    )
    artist_values = [
        item["value"] for item in candidates["album_artist"]
        if not item["ignored"]
    ]
    assert "DJ Cinema & Lil Wayne" in artist_values
    assert "Various Artists" not in artist_values
    assert candidates["album_title"][0]["value"] == (
        "Starring In Mardi Gras Bootleg"
    )
    assert candidates["year"][0]["value"] == "2008"
    assert [item["value"] for item in track_candidates] == ["A Real Song"]

    blocked = build_review_state("music_album", {
        "artist": "Unknown Artist",
        "album": "Known Album",
        "year": "",
        "metadata_warnings": [],
    })
    assert any(
        item["type"] == "artist_missing"
        for item in blocked["blocking_review_items"]
    )
    assert any(
        item["type"] == "year_missing"
        for item in blocked["non_blocking_review_items"]
    )

    accepted = build_review_state("music_album", {
        "artist": "Unknown Artist",
        "album": "Unknown Album",
        "year": "",
        "accepted_unknown_album_artist": True,
        "accepted_unknown_album_title": True,
        "accepted_unknown_year": True,
        "metadata_warnings": [],
    })
    assert accepted["blocking_review_items"] == []

    discography = build_review_state("music_discography", {
        "artist": "Unknown Artist",
        "accepted_unknown_discography_artist": True,
        "albums": [{
            "source_folder": "Mystery Release",
            "album": "Mystery Release",
            "year": None,
            "include": True,
            "accepted_unknown_year": True,
            "lookup_later": True,
        }],
        "metadata_warnings": [],
    })
    assert discography["blocking_review_items"] == []

    album_metadata = {
        "artist": "Unknown Artist",
        "album": "Known Album",
        "year": "",
        "format": "FLAC",
        "disc_count": 2,
        "track_count": 18,
        "accepted_unknown_album_artist": True,
        "accepted_unknown_year": True,
        "lookup_later": True,
    }
    assert ARCHIVE_ASSISTANT_VERSION == "v2.066"
    assert _confirmed_metadata("music_album", album_metadata)[
        "album_artist"
    ] == "Unknown Artist"
    assert _accepted_unknowns("music_album", album_metadata) == {
        "album_artist": True,
        "album_title": False,
        "year": True,
        "items": [],
    }
    assert _lookup_later("music_album", album_metadata)
    summary = _summary("music_album", album_metadata, {
        "artwork_moved": [{}],
        "sidecars_ignored": [],
        "failed_moves": [],
    })
    assert summary["disc_count"] == 2
    assert summary["track_count"] == 18
    assert summary["artwork_count"] == 1

    print("v2.065 music metadata assist checks passed")


if __name__ == "__main__":
    main()
