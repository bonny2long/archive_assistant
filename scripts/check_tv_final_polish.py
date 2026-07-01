"""Final TV polish regression test.

Verifies:
- TV count display format (seasons · episodes · specials · videos)
- Metadata locking after approve/move
- Move destination structure
- No new TV/video parser dependencies
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
from app.services.video_metadata import normalize_tv_counts, parse_tv_episode_name


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


def test_normalize_tv_counts():
    metadata = {
        "seasons": [
            {"season_number": 1, "episode_count": 24, "episodes": [{"episode_number": i} for i in range(1, 25)]},
            {"season_number": 2, "episode_count": 22, "episodes": [{"episode_number": i} for i in range(1, 23)]},
            {"season_number": 3, "episode_count": 20, "episodes": [{"episode_number": i} for i in range(1, 21)]},
            {"season_number": 4, "episode_count": 20, "episodes": [{"episode_number": i} for i in range(1, 21)]},
        ],
        "special_episodes": [
            {"special_label": "OAD01"}, {"special_label": "OAD02"}, {"special_label": "OAD03"},
            {"special_label": "OAD04"}, {"special_label": "OAD05"}, {"special_label": "OAD06"},
            {"special_label": "OAD07"}, {"special_label": "OAD08"},
            {"special_label": "S01E13.5"}, {"special_label": "Special 1"}, {"special_label": "Special 2"},
        ],
    }
    result = normalize_tv_counts(metadata)
    assert result["episode_count"] == 86
    assert result["special_episode_count"] == 11
    assert result["video_file_count"] == 97
    assert result["video_file_count"] == result["episode_count"] + result["special_episode_count"]
    assert result["season_count"] == 4
    print("  PASS: normalize_tv_counts sets correct counts and maintains video_file_count == episode_count + special_episode_count")


def test_no_new_tv_video_parser_dependencies():
    requirements = (PROJECT_ROOT / "backend" / "requirements.txt").read_text(encoding="utf-8")
    blocked = ["pymediainfo", "ffmpeg-python", "tinytag"]
    for dep in blocked:
        assert dep not in requirements.lower(), f"Blocked dependency found: {dep}"
    print("  PASS: no blocked TV/video parser dependencies in requirements.txt")


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
        ("Normalize TV counts", test_normalize_tv_counts),
        ("No new TV/video parser dependencies", test_no_new_tv_video_parser_dependencies),
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
