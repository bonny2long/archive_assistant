"""Check folder-first release grouping and loose-file metadata fallback."""

from __future__ import annotations

import os
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = PROJECT_ROOT / "backend"
os.environ["DEBUG"] = "true"
sys.path.insert(0, str(BACKEND_ROOT))

from app.core.config import settings  # noqa: E402
from app.services.scanner import _group_key, _release_source_path  # noqa: E402


def metadata(artist: str, album: str, year: str) -> dict:
    return {"albumartist": artist, "album": album, "date": year}


def check(label: str, condition: bool) -> int:
    print(f"{'PASS' if condition else 'FAIL'} {label}")
    return 0 if condition else 1


def main() -> int:
    root = settings.ingest_music_dir
    failures = 0

    release_a = root / "2003 Get Rich Or Die Tryin" / "01.mp3"
    release_b = root / "2003 Get Rich Or Die Tryin" / "33.mp3"
    failures += check(
        "same release folder ignores conflicting tags",
        _group_key(
            release_a,
            metadata("DJ Cinema", "Get Rich Or Die Tryin", "2003"),
        )
        == _group_key(
            release_b,
            metadata("Unknown Artist", "Starring In Mardi Gras", "2008"),
        ),
    )

    disc_one = root / "Kendrick Lamar - Mr. Morale" / "CD1" / "01.mp3"
    disc_two = root / "Kendrick Lamar - Mr. Morale" / "CD2" / "01.mp3"
    failures += check(
        "multi-disc folders share a release source",
        _release_source_path(disc_one) == _release_source_path(disc_two)
        and _group_key(disc_one, metadata("Kendrick Lamar", "Mr. Morale", "2022"))
        == _group_key(disc_two, metadata("Kendrick Lamar", "Mr. Morale", "2022")),
    )

    loose_one = root / "song1.mp3"
    loose_two = root / "song2.mp3"
    failures += check(
        "loose root files still group by embedded metadata",
        _group_key(loose_one, metadata("Artist", "Album", "2001"))
        == _group_key(loose_two, metadata("Artist", "Album", "2001")),
    )
    failures += check(
        "different loose metadata remains separate",
        _group_key(loose_one, metadata("Artist A", "Album A", "2001"))
        != _group_key(loose_two, metadata("Artist B", "Album B", "2002")),
    )

    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
