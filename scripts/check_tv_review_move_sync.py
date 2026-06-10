"""Verify TV review sync, identity helpers, and mover validation."""

from __future__ import annotations

import sys
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace


PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = PROJECT_ROOT / "backend"
sys.path.insert(0, str(BACKEND_ROOT))

from app.services.tv_review import (  # noqa: E402
    apply_tv_episode_review_patches,
    tv_episode_identity,
    ingest_file_identity,
    build_ingest_file_lookup,
    sync_tv_episode_metadata_to_ingest_files,
)
from app.services.mover import (  # noqa: E402
    _tv_special_group_destination,
    _validate_tv_file_metadata_ready,
)
from app.services.video_metadata import parse_tv_episode_name  # noqa: E402


def test_identity_normalization():
    key = tv_episode_identity(
        "Show - S01E01 - Pilot.mkv",
        "Season 01/Show - S01E01 - Pilot.mkv",
    )
    assert key[0] == "show - s01e01 - pilot.mkv"
    assert key[1] == "season 01\\show - s01e01 - pilot.mkv"
    print("  PASS: tv_episode_identity normalizes slashes, casefold, strip")


def test_ingest_file_identity():
    file = SimpleNamespace(
        metadata_json={
            "source_file": "Show - S01E01 - Pilot.mkv",
            "relative_source": "Season 01\\Show - S01E01 - Pilot.mkv",
        }
    )
    key = ingest_file_identity(file)
    assert key[0] == "show - s01e01 - pilot.mkv"
    assert key[1] == "season 01\\show - s01e01 - pilot.mkv"
    print("  PASS: ingest_file_identity matches tv_episode_identity format")


def test_build_ingest_file_lookup():
    files = [
        SimpleNamespace(
            metadata_json={
                "source_file": "S01E01.mkv",
                "relative_source": "Season 01\\S01E01.mkv",
            }
        ),
        SimpleNamespace(
            metadata_json={
                "source_file": "S01E02.mkv",
                "relative_source": "Season 01\\S01E02.mkv",
            }
        ),
    ]
    lookup = build_ingest_file_lookup(files)
    key0 = ("s01e01.mkv", "season 01\\s01e01.mkv")
    key1 = ("s01e02.mkv", "season 01\\s01e02.mkv")
    assert key0 in lookup
    assert key1 in lookup
    assert lookup[key0] is files[0]
    assert lookup[key1] is files[1]
    print("  PASS: build_ingest_file_lookup returns correct identity mapping")


def test_sync_writes_metadata_to_files():
    files = [
        SimpleNamespace(
            metadata_json={
                "source_file": "S01E01.mkv",
                "relative_source": "Season 01\\S01E01.mkv",
            }
        ),
    ]
    reviewed = [
        {
            "source_file": "S01E01.mkv",
            "relative_source": "Season 01\\S01E01.mkv",
            "show_title": "Test Show",
            "season_number": 1,
            "episode_number": 1,
            "episode_code": "S01E01",
            "episode_title": "Pilot",
            "include": True,
            "reviewed": True,
            "confidence": 0.95,
        },
    ]
    unmatched = sync_tv_episode_metadata_to_ingest_files(files, reviewed)
    assert len(unmatched) == 0, f"Unexpected unmatched: {unmatched}"
    meta = files[0].metadata_json
    assert meta.get("show_title") == "Test Show"
    assert meta.get("episode_code") == "S01E01"
    assert meta.get("reviewed") is True
    print("  PASS: sync writes reviewed fields to file metadata_json")


def test_sync_unmatched_identity():
    files = [
        SimpleNamespace(
            metadata_json={
                "source_file": "S01E01.mkv",
                "relative_source": "Season 01\\S01E01.mkv",
            }
        ),
    ]
    reviewed = [
        {
            "source_file": "NONEXISTENT.mkv",
            "relative_source": "Season 01\\NONEXISTENT.mkv",
            "show_title": "Ghost",
        },
    ]
    unmatched = sync_tv_episode_metadata_to_ingest_files(files, reviewed)
    assert len(unmatched) == 1
    assert "NONEXISTENT" in unmatched[0]
    print("  PASS: sync returns unmatched identities")


def test_apply_patches_returns_tuple():
    metadata = {
        "show_title": "Test",
        "seasons": [
            {
                "season_number": 1,
                "episode_count": 1,
                "episodes": [
                    {
                        "source_file": "S01E01.mkv",
                        "relative_source": "Season 01\\S01E01.mkv",
                        "season_number": 1,
                        "episode_number": 1,
                        "episode_code": "S01E01",
                        "include": True,
                    },
                ],
            },
        ],
    }
    result = apply_tv_episode_review_patches(metadata, [], [])
    assert isinstance(result, tuple)
    assert len(result) == 2
    assert isinstance(result[0], dict)
    assert isinstance(result[1], list)
    print("  PASS: apply_tv_episode_review_patches returns tuple[dict, list[dict]]")


def test_tv_special_group_destination():
    root = Path("/TV/Library/Test")
    assert _tv_special_group_destination(root, "specials") == root / "Specials"
    assert _tv_special_group_destination(root, "oad") == root / "Specials"
    assert _tv_special_group_destination(root, "ova") == root / "Specials"
    assert _tv_special_group_destination(root, "extras") == root / "Extras"
    print("  PASS: oad/ova both route to Specials folder")


def test_validate_tv_file_metadata_ready():
    good_file = SimpleNamespace(
        detected_role="tv_episode",
        file_name="S01E01.mkv",
        metadata_json={
            "season_number": 1,
            "episode_number": 1,
            "episode_code": "S01E01",
        },
    )
    special_file = SimpleNamespace(
        detected_role="tv_episode",
        file_name="OAD01.mkv",
        metadata_json={
            "is_special": True,
            "special_label": "OAD01",
            "destination_group": "oad",
        },
    )
    bad_file = SimpleNamespace(
        detected_role="tv_episode",
        file_name="Bad.mkv",
        metadata_json={
            "season_number": None,
            "episode_number": None,
        },
    )

    class FakeBatch:
        files = [good_file, special_file, bad_file]

    errors = _validate_tv_file_metadata_ready(FakeBatch())
    assert "missing season number" in errors[0].lower()
    assert "missing episode number" in errors[1].lower()
    assert "missing episode code" in errors[2].lower()
    print("  PASS: _validate_tv_file_metadata_ready catches missing required fields")


def test_oad_label_format():
    parsed = parse_tv_episode_name("Test Show - OADE01 - Extra Story.mkv")
    assert parsed["special_label"] == "OAD01", (
        f"Expected OAD01, got {parsed['special_label']}"
    )
    assert parsed["destination_group"] == "oad"
    print("  PASS: OADE01 -> OAD01 label format")


def test_sp_label_preserves_original():
    parsed = parse_tv_episode_name("Test Show - Special 1 - Extra.mkv")
    assert parsed["special_label"] is not None
    special_lower = parsed["special_label"].lower()
    assert "special" in special_lower
    assert "1" in special_lower
    print("  PASS: SP label preserves original text")


def main() -> int:
    tests = [
        ("Identity normalization", test_identity_normalization),
        ("Ingest file identity", test_ingest_file_identity),
        ("Build ingest file lookup", test_build_ingest_file_lookup),
        ("Sync writes metadata", test_sync_writes_metadata_to_files),
        ("Sync unmatched identity", test_sync_unmatched_identity),
        ("Apply patches returns tuple", test_apply_patches_returns_tuple),
        ("Special group destination", test_tv_special_group_destination),
        ("Validate metadata ready", test_validate_tv_file_metadata_ready),
        ("OAD label format", test_oad_label_format),
        ("SP label preservers original", test_sp_label_preserves_original),
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
