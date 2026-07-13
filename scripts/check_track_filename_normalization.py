import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = PROJECT_ROOT / "backend"
os.environ["DEBUG"] = "true"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.services.music_metadata import (  # noqa: E402
    music_track_filename,
    normalize_track_title_for_destination,
)


def main() -> None:
    cases = [
        ("01 - Cats and Dogs", 1, "Cats and Dogs"),
        ("01. Cats and Dogs", 1, "Cats and Dogs"),
        ("01_Cats and Dogs", 1, "Cats and Dogs"),
        ("1 - Cats and Dogs", 1, "Cats and Dogs"),
        ("01 - 01 - Cats and Dogs", 1, "Cats and Dogs"),
        ("01 - 02 - Coeur D'Alene", 2, "Coeur D'Alene"),
        ("2 Of Amerikaz Most Wanted", 2, "2 Of Amerikaz Most Wanted"),
        ("99 Problems", 9, "99 Problems"),
        ("10 Crack Commandments", 10, "10 Crack Commandments"),
        ("10. Crack Commandments", 10, "Crack Commandments"),
        ("12 - 500 Degreez", 12, "500 Degreez"),
        ("1-02 - N95", 2, "N95"),
        ("01 - 02 - Coeur D'Alene", 2, "Coeur D'Alene"),
        ("02 - 2000 Watts", 2, "2000 Watts"),
        ("162 - Final Chapter", 162, "Final Chapter"),
    ]
    for raw, track, expected in cases:
        actual = normalize_track_title_for_destination(raw, track)
        assert actual == expected, f"{raw!r} normalized to {actual!r}, expected {expected!r}"

    assert music_track_filename(
        {"tracknumber": "1", "title": "01 - Cats and Dogs"},
        ".flac",
        1,
        "01 - Cats and Dogs.flac",
    ) == "01 - Cats and Dogs.flac"
    assert music_track_filename(
        {"discnumber": "1", "tracknumber": "1", "title": "01 - 01 - Cats and Dogs"},
        ".flac",
        2,
        "01 - 01 - Cats and Dogs.flac",
    ) == "1-01 - Cats and Dogs.flac"
    print("Track filename normalization checks passed.")


if __name__ == "__main__":
    main()