"""Movie final polish regression test.

Verifies:
- parse_movie_name handles Black Panther, Mortal Kombat II, Blade Runner
- edition-aware destination paths
- movie review state rules
- Normalize TV counts (shared utility still works)
- No forbidden dependencies
- Video files list in movie metadata
"""

from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = PROJECT_ROOT / "backend"
sys.path.insert(0, str(BACKEND_ROOT))

from app.services.video_metadata import (
    normalize_tv_counts,
    parse_movie_name,
    safe_movie_path_part,
)
from app.services.review_state import build_review_state


def test_parse_black_panther():
    result = parse_movie_name("Black Panther (2018) [BluRay] [1080p] [YTS.AM]")
    assert result["title"] == "Black Panther", f"Expected 'Black Panther', got {result['title']!r}"
    assert result["year"] == "2018"
    tags = result["release_tags_removed"]
    assert "BluRay" in tags
    assert "1080p" in tags
    print("  PASS: parse_movie_name — Black Panther folder name")


def test_parse_black_panther_filename():
    result = parse_movie_name("Black.Panther.2018.1080p.BluRay.x264-[YTS.AM].mp4")
    assert result["title"] == "Black Panther"
    assert result["year"] == "2018"
    tags = result["release_tags_removed"]
    assert "BluRay" in tags
    assert "1080p" in tags
    assert "x264" in tags
    print("  PASS: parse_movie_name — Black Panther filename")


def test_parse_mortal_kombat():
    result = parse_movie_name("Mortal.Kombat.II.2026.1080p.WEBRip.AAC5.1.10bits.x265-Rapta.mkv")
    assert result["title"] == "Mortal Kombat II", f"Expected 'Mortal Kombat II', got {result['title']!r}"
    assert result["year"] == "2026"
    tags = result["release_tags_removed"]
    assert "1080p" in tags
    assert "WEBRip" in tags
    assert "x265" in tags
    print("  PASS: parse_movie_name — Mortal Kombat II filename")


def test_parse_blade_runner():
    result = parse_movie_name("Blade.Runner.1982.Final.Cut.1080p.mkv")
    assert result["title"] == "Blade Runner"
    assert result["year"] == "1982"
    print("  PASS: parse_movie_name — Blade Runner filename")


def test_edition_destination():
    folder = safe_movie_path_part("1982 - Blade Runner [Final Cut]")
    assert folder == "1982 - Blade Runner [Final Cut]", f"Got {folder!r}"
    folder = safe_movie_path_part("2018 - Black Panther")
    assert folder == "2018 - Black Panther", f"Got {folder!r}"
    print("  PASS: edition-aware destination path")


def test_movie_review_title_missing():
    meta = build_review_state("video_movie", {"title": "", "year": "2020", "video_file_count": 1})
    assert any(item["type"] == "movie_title_missing" for item in meta["blocking_review_items"])
    print("  PASS: review_state blocks missing title")


def test_movie_review_year_missing():
    meta = build_review_state("video_movie", {"title": "Test", "year": "", "video_file_count": 1})
    assert any(item["type"] == "movie_year_missing" for item in meta["blocking_review_items"])
    print("  PASS: review_state blocks missing year")


def test_movie_review_multiple_videos_ambiguous():
    meta = build_review_state("video_movie", {
        "title": "Test", "year": "2020", "video_file_count": 2,
        "video_files": ["Random.2020.mkv", "Other.2021.mkv"],
    })
    assert any(item["type"] == "multiple_movie_candidates" for item in meta["blocking_review_items"])
    print("  PASS: review_state blocks ambiguous multiple movie videos")


def test_movie_review_multiple_editions_warning():
    meta = build_review_state("video_movie", {
        "title": "Blade Runner", "year": "1982", "video_file_count": 2,
        "video_files": [
            "Blade.Runner.1982.Final.Cut.1080p.mkv",
            "Blade.Runner.1982.Theatrical.Cut.1080p.mkv",
        ],
    })
    assert any(item["type"] == "multiple_movie_editions" for item in meta["non_blocking_review_items"])
    assert not any(item["type"] == "multiple_movie_candidates" for item in meta["blocking_review_items"])
    print("  PASS: review_state warns on clear editions (non-blocking)")


def test_movie_review_passes():
    meta = build_review_state("video_movie", {"title": "Black Panther", "year": "2018", "video_file_count": 1})
    assert len(meta["blocking_review_items"]) == 0
    print("  PASS: review_state passes for clean movie metadata")


def test_normalize_tv_counts():
    metadata = {
        "seasons": [
            {"season_number": 1, "episode_count": 24, "episodes": [{"episode_number": i} for i in range(1, 25)]},
        ],
        "special_episodes": [{"special_label": "OAD01"}],
    }
    result = normalize_tv_counts(metadata)
    assert result["episode_count"] == 24
    assert result["special_episode_count"] == 1
    assert result["video_file_count"] == 25
    assert result["season_count"] == 1
    print("  PASS: normalize_tv_counts (shared utility still works)")


def test_no_forbidden_dependencies():
    requirements = (PROJECT_ROOT / "backend" / "requirements.txt").read_text(encoding="utf-8")
    blocked = ["mutagen", "pymediainfo", "ffmpeg-python", "tinytag"]
    for dep in blocked:
        assert dep not in requirements.lower(), f"Blocked dependency found: {dep}"
    print("  PASS: no forbidden dependencies added")


def _make_fake_batch(detected_type: str, metadata: dict):
    batch = SimpleNamespace()
    batch.detected_type = detected_type
    batch.metadata_json = dict(metadata)
    batch.metadata_confirmed = False
    batch.status = "pending_review"
    batch.id = 0
    batch.source_path = ""
    batch.suggested_destination = ""
    batch.files = []
    batch.updated_at = None
    return batch


def main() -> int:
    tests = [
        ("Parse Black Panther folder", test_parse_black_panther),
        ("Parse Black Panther filename", test_parse_black_panther_filename),
        ("Parse Mortal Kombat II", test_parse_mortal_kombat),
        ("Parse Blade Runner", test_parse_blade_runner),
        ("Edition-aware destination", test_edition_destination),
        ("Review — missing title", test_movie_review_title_missing),
        ("Review — missing year", test_movie_review_year_missing),
        ("Review — ambiguous multiple videos", test_movie_review_multiple_videos_ambiguous),
        ("Review — clear editions warning", test_movie_review_multiple_editions_warning),
        ("Review — passes clean metadata", test_movie_review_passes),
        ("Normalize TV counts (shared)", test_normalize_tv_counts),
        ("No forbidden dependencies", test_no_forbidden_dependencies),
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
        return 1
    else:
        print(f"PASSED: all {len(tests)} tests")
        return 0


if __name__ == "__main__":
    sys.exit(main())
