"""Check discography release buckets and exclusion quarantine destinations."""

from __future__ import annotations

import os
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = PROJECT_ROOT / "backend"
os.environ["DEBUG"] = "true"
sys.path.insert(0, str(BACKEND_ROOT))

from app.services.mover import (  # noqa: E402
    _discography_album_destination,
    _discography_quarantine_destination,
)


def check(label: str, condition: bool) -> int:
    print(f"{'PASS' if condition else 'FAIL'} {label}")
    return 0 if condition else 1


def main() -> int:
    root = Path("Music/Discographies/Kanye West")
    single = _discography_album_destination(
        root,
        {"album": "All Day", "year": "2015", "release_type": "single"},
    )
    excluded = _discography_quarantine_destination(
        "Kanye West",
        {
            "source_folder": "(2015) Kanye West - Pacific Blues [16Bit-44.1kHz]",
            "release_type": "exclude",
            "include": False,
        },
        "01.flac",
    )
    failures = 0
    failures += check(
        "single routes to Singles year-title bucket",
        single.as_posix().endswith(
            "Music/Discographies/Kanye West/Singles/2015 - All Day"
        ),
    )
    failures += check(
        "excluded release routes to discography quarantine",
        "discography-excluded/Kanye West" in excluded.as_posix()
        and excluded.name == "01.flac",
    )
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
