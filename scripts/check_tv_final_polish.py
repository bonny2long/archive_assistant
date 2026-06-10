"""Final TV polish regression test.

Verifies:
- TV count display format (seasons · episodes · specials · videos)
- Metadata locking after approve/move
- Move destination structure
- No unused dependencies
"""

from __future__ import annotations

import json
import shutil
import sys
import tempfile
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = PROJECT_ROOT / "backend"
sys.path.insert(0, str(BACKEND_ROOT))

from app.services.mover import _lock_metadata_for_move, _tv_special_group_destination, _validate_tv_file_metadata_ready
from app.services.batch_display import build_batch_display_fields
from app.services.video_metadata import parse_tv_episode_name


def test_tv_count_display():
    metadata = {
        "season_count": 4,
        "episode_count": 86,
        "special_episode_count": 11,
        "video_file_count": 97,
        "show_title": "Shingeki no Kyojin",
    }
    display = build_batch_display_fields(_make_fake_batch("video_tv_show", metadata))
    secondary = display.get("secondary_name", "")
    assert "4 seasons" in secondary
    assert "86 episodes" in secondary
    assert "11 specials" in secondary
    assert "97 videos" in secondary
    print("  PASS: TV count display shows seasons, episodes, specials, videos")


def test_tv_count_display_no_specials():
    metadata = {
        "season_count": 1,
        "episode_count": 10,
        "special_episode_count": 0,
        "video_file_count": 10,
        "show_title": "Rick and Morty",
    }
    display = build_batch_display_fields(_make_fake_batch("video_tv_show", metadata))
    secondary = display.get("secondary_name", "")
    assert "1 season" in secondary
    assert "10 episodes" in secondary
    assert "specials" not in secondary
    assert "videos" not in secondary
    print("  PASS: TV count display omits specials/videos when zero or equal")


def test_tv_count_display_weak_quality():
    metadata = {
        "season_count": 1,
        "episode_count": 5,
        "metadata_quality": "weak",
        "show_title": "Test",
    }
    display = build_batch_display_fields(_make_fake_batch("video_tv_show", metadata))
    secondary = display.get("secondary_name", "")
    assert "needs episode review" in secondary
    print("  PASS: TV count display includes needs episode review for weak quality")


def test_lock_metadata_for_move():
    batch = _make_fake_batch("video_tv_show", {"show_title": "Test", "review_confirmed": False})
    batch.metadata_confirmed = False
    _lock_metadata_for_move(batch)
    meta = batch.metadata_json or {}
    assert meta.get("review_confirmed") is True
    assert meta.get("metadata_locked_for_move") is True
    assert meta.get("metadata_locked_at") is not None
    assert batch.metadata_confirmed is True
    print("  PASS: _lock_metadata_for_move sets review_confirmed, locked_for_move, locked_at, metadata_confirmed")


def test_special_group_destination():
    root = Path("/TV/Library/Show")
    assert _tv_special_group_destination(root, "specials") == root / "Specials"
    assert _tv_special_group_destination(root, "oad") == root / "Specials"
    assert _tv_special_group_destination(root, "extras") == root / "Extras"
    print("  PASS: special group destination routing correct")


def test_parse_big_anime_show():
    files = [
        ("Big Anime Show - S01E01 - Pilot.mkv", {"season_number": 1, "episode_number": 1, "is_special": False}),
        ("Big Anime Show - S01E02 - Second.mkv", {"season_number": 1, "episode_number": 2, "is_special": False}),
        ("Big Anime Show - S01E02.5 - Recap.mkv", {"season_number": 1, "is_special": True, "special_label": "S01E02.5"}),
        ("Big Anime Show - S02E01 - Return.mkv", {"season_number": 2, "episode_number": 1, "is_special": False}),
        ("Big Anime Show - OADE01 - Bonus One.mkv", {"is_special": True, "special_label": "OAD01", "destination_group": "oad"}),
        ("Big Anime Show - OADE02 - Bonus Two.mkv", {"is_special": True, "special_label": "OAD02", "destination_group": "oad"}),
    ]
    for filename, expected in files:
        parsed = parse_tv_episode_name(filename)
        for key, value in expected.items():
            assert parsed.get(key) == value, (
                f"{filename}: expected {key}={value!r}, got {parsed.get(key)!r}"
            )
    print("  PASS: all Big Anime Show files parse correctly")


def test_no_new_dependencies():
    requirements = (PROJECT_ROOT / "backend" / "requirements.txt").read_text(encoding="utf-8")
    blocked = ["mutagen", "pymediainfo", "ffmpeg-python", "tinytag"]
    for dep in blocked:
        assert dep not in requirements.lower(), f"Blocked dependency found: {dep}"
    print("  PASS: no blocked dependencies in requirements.txt")


def _make_fake_batch(detected_type: str, metadata: dict):
    from types import SimpleNamespace

    batch = SimpleNamespace()
    batch.detected_type = detected_type
    batch.metadata_json = dict(metadata)
    batch.metadata_confirmed = False
    batch.status = "approved"
    batch.id = 0
    batch.source_path = ""
    batch.suggested_destination = ""
    batch.files = []
    batch.updated_at = None
    return batch


def main() -> int:
    tests = [
        ("TV count display", test_tv_count_display),
        ("TV count display no specials", test_tv_count_display_no_specials),
        ("TV count display weak quality", test_tv_count_display_weak_quality),
        ("Lock metadata for move", test_lock_metadata_for_move),
        ("Special group destination", test_special_group_destination),
        ("Parse Big Anime Show", test_parse_big_anime_show),
        ("No new dependencies", test_no_new_dependencies),
    ]

    failures = 0
    for name, fn in tests:
        try:
            fn()
        except Exception as exc:
            print(f"  FAIL: {name}: {exc}")
            failures += 1

    print()
    if failures:
        print(f"FAILED: {failures} of {len(tests)} tests")
    else:
        print(f"PASSED: all {len(tests)} tests")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
