"""Check deterministic music folder parsing against ugly real-world examples."""

from __future__ import annotations

import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = PROJECT_ROOT / "backend"
sys.path.insert(0, str(BACKEND_ROOT))

from app.services.music_metadata import parse_music_folder_name  # noqa: E402


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

    if failures:
        print(f"{failures} parser check(s) failed.")
        return 1
    print("All metadata parser checks passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
