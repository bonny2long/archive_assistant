"""Check deterministic music folder parsing against ugly real-world examples."""

from __future__ import annotations

import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = PROJECT_ROOT / "backend"
sys.path.insert(0, str(BACKEND_ROOT))

from app.services.music_metadata import (  # noqa: E402
    canonical_album_key,
    canonical_artist_key,
    metadata_mismatch_warnings,
    parse_music_folder_name,
)


CASES = [
    (
        "Nas_-_Illmatic_(1994)_[FLAC_24bit_Remaster_320kbps]",
        {"artist": "Nas", "album": "Illmatic", "year": "1994"},
    ),
    (
        "2003 Get Rich Or Die Tryin",
        {"artist": None, "album": "Get Rich Or Die Tryin", "year": "2003"},
    ),
    (
        "Jay-Z_x_Kanye_West_-_Watch_The_Throne_2011_Deluxe_Edition",
        {"artist": "Jay-Z & Kanye West", "album": "Watch The Throne", "year": "2011"},
    ),
    (
        "Outkast - Aquemini",
        {"artist": "Outkast", "album": "Aquemini", "year": None},
    ),
    (
        "VA_-_90s_Hip_Hop_Classics_1998",
        {"artist": "Various Artists", "album": "90s Hip Hop Classics", "year": "1998"},
    ),
]

ARTIST_ALIASES = [
    "DJ Cinema - Lil Wayne",
    "DJ Cinema & Lil Wayne",
    "DJ_Cinema_and_Lil_Wayne",
    "DJ Cinema and Lil Wayne",
]


def main() -> int:
    failures = 0
    for folder_name, expected in CASES:
        actual = parse_music_folder_name(folder_name)
        if actual == expected:
            print(f"PASS {folder_name} => {actual['artist']} / {actual['album']} / {actual['year']}")
            continue

        failures += 1
        print(f"FAIL {folder_name}")
        print(f"  expected: {expected}")
        print(f"  actual:   {actual}")

    artist_keys = {canonical_artist_key(value) for value in ARTIST_ALIASES}
    if artist_keys == {"dj cinema lil wayne"}:
        print("PASS canonical artist aliases => dj cinema lil wayne")
    else:
        failures += 1
        print(f"FAIL canonical artist aliases => {artist_keys}")

    if canonical_album_key("reasonable doubt") == canonical_album_key("Reasonable Doubt"):
        print("PASS canonical album case comparison")
    else:
        failures += 1
        print("FAIL canonical album case comparison")

    mismatch_warnings = metadata_mismatch_warnings(
        [
            {
                "albumartist": "DJ Cinema & Lil Wayne",
                "artist": "Lil Wayne",
                "album": "Get Rich Or Die Tryin",
            },
            {
                "albumartist": "DJ Cinema",
                "artist": "DJ Cinema",
                "album": "Starring In Mardi Gras",
            },
        ],
        {
            "artist": "DJ Cinema & Lil Wayne",
            "album": "Get Rich Or Die Tryin",
        },
    )
    required_warnings = {
        "mixed_embedded_metadata_detected",
        "track_album_mismatch_detected",
        "track_artist_mismatch_detected",
    }
    if required_warnings.issubset(mismatch_warnings):
        print("PASS mixed embedded metadata warnings")
    else:
        failures += 1
        print(f"FAIL mixed embedded metadata warnings => {mismatch_warnings}")

    if failures:
        print(f"{failures} parser check(s) failed.")
        return 1
    print("All metadata parser checks passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
