"""Check resilient canonical music track ordering and filename generation."""

from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace


PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = PROJECT_ROOT / "backend"
sys.path.insert(0, str(BACKEND_ROOT))

from app.services.music_metadata import (  # noqa: E402
    music_track_filename,
    music_track_numbers,
    sort_music_tracks,
)


def track(
    file_id: int,
    filename: str,
    tracknumber=None,
    discnumber=None,
    title: str | None = None,
):
    metadata = {"title": title or Path(filename).stem}
    if tracknumber is not None:
        metadata["tracknumber"] = tracknumber
    if discnumber is not None:
        metadata["discnumber"] = discnumber
    return SimpleNamespace(
        id=file_id,
        file_name=filename,
        extension=Path(filename).suffix,
        metadata_json=metadata,
    )


def check(label: str, condition: bool) -> int:
    print(f"{'PASS' if condition else 'FAIL'} {label}")
    return 0 if condition else 1


def main() -> int:
    failures = 0

    merged_order = [
        track(2, "02 - Nothing Can Stop Me.mp3", "2/24"),
        track(99, "01 - Intro.mp3", "1/24"),
        track(3, "03 - The Rapper Eater.mp3", "03"),
    ]
    ordered = sort_music_tracks(merged_order)
    failures += check(
        "merged insertion order becomes canonical track order",
        [item.file_name for item in ordered]
        == [
            "01 - Intro.mp3",
            "02 - Nothing Can Stop Me.mp3",
            "03 - The Rapper Eater.mp3",
        ],
    )

    multi_disc = [
        track(4, "2-01 - Count Me Out.mp3", "1", None, "Count Me Out"),
        track(1, "1-02 - N95.mp3", "2", "1", "N95"),
        track(3, "1-01 - United In Grief.mp3", "1/9", "1", "United In Grief"),
    ]
    ordered = sort_music_tracks(multi_disc)
    failures += check(
        "multi-disc filename fallback preserves disc then track order",
        [item.file_name for item in ordered]
        == [
            "1-01 - United In Grief.mp3",
            "1-02 - N95.mp3",
            "2-01 - Count Me Out.mp3",
        ],
    )
    failures += check(
        "multi-disc destination filename is stable",
        music_track_filename(
            multi_disc[0].metadata_json,
            ".mp3",
            2,
            multi_disc[0].file_name,
        )
        == "2-01 - Count Me Out.mp3",
    )

    filename_fallback = track(7, "02 DJ Cinema - New York Minute.mp3")
    failures += check(
        "numeric filename prefix supplies missing track number",
        music_track_numbers(
            filename_fallback.metadata_json,
            filename_fallback.file_name,
        )
        == (1, 2),
    )

    malformed = track(8, "unknown.mp3", "side-a", "disc-x", "Unknown")
    failures += check(
        "malformed metadata does not crash",
        music_track_numbers(malformed.metadata_json, malformed.file_name) == (1, None)
        and music_track_filename(
            malformed.metadata_json,
            ".mp3",
            1,
            malformed.file_name,
        )
        == "01 - Unknown.mp3",
    )

    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
