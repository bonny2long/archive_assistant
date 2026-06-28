#!/usr/bin/env python3
"""
check_universal_review_contract.py

Verifies that all media types produce a consistent review contract
in their metadata_json. Checks the universal fields that must always
be present after build_review_state() has been called.
"""
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

from app.services.review_state import build_review_state

UNIVERSAL_FIELDS = [
    "metadata_quality",
    "metadata_warnings",
    "blocking_review_items",
    "non_blocking_review_items",
    "review_confirmed",
    "review_type",
    "review_mode",
]

EXPECTED_REVIEW_MODES = {
    "music_album": "single_item",
    "music_discography": "item_list",
    "video_movie": "single_item",
    "video_tv_show": "guided_episode_review",
    "unknown_type": "quarantine_review",
    "unsupported_file": "quarantine_review",
}

EXPECTED_REVIEW_TYPES = {
    "music_album": "music_album",
    "music_discography": "music_discography",
    "video_movie": "movie",
    "video_tv_show": "tv_show",
    "unknown_type": "quarantine",
    "unsupported_file": "quarantine",
}

TEST_CASES = [
    {
        "detected_type": "music_album",
        "metadata": {
            "artist": "Nas",
            "album": "Illmatic",
            "year": "1994",
            "metadata_warnings": [],
        },
    },
    {
        "detected_type": "music_album",
        "metadata": {
            "metadata_warnings": [],
        },
        "expected_blockers": {"artist_missing", "album_missing"},
        "expected_non_blockers": {"year_missing"},
    },
    {
        "detected_type": "music_discography",
        "metadata": {
            "artist": "Nas",
            "albums": [
                {
                    "source_folder": "1994 - Illmatic",
                    "album": "Illmatic",
                    "year": "1994",
                    "include": True,
                }
            ],
            "metadata_warnings": [],
        },
    },
    {
        "detected_type": "video_movie",
        "metadata": {
            "title": "Black Panther",
            "year": "2018",
            "video_file_count": 1,
            "metadata_warnings": [],
        },
    },
    {
        "detected_type": "video_movie",
        "metadata": {
            "metadata_warnings": [],
        },
        "expected_blockers": {"movie_title_missing"},
        "expected_non_blockers": {"movie_year_missing"},
    },
    {
        "detected_type": "video_tv_show",
        "metadata": {
            "show_title": "Shingeki no Kyojin",
            "seasons": [
                {
                    "season_number": 1,
                    "episodes": [
                        {
                            "source_file": "S01E01.mkv",
                            "season_number": 1,
                            "episode_number": 1,
                            "episode_code": "S01E01",
                            "include": True,
                        }
                    ],
                }
            ],
            "metadata_warnings": [],
        },
    },
    {
        "detected_type": "unknown_type",
        "metadata": {"metadata_warnings": []},
        "expected_blockers": {"quarantine_review_required"},
    },
]


def run():
    failures = []

    for idx, case in enumerate(TEST_CASES):
        detected_type = case["detected_type"]
        metadata = case["metadata"]
        expected_blockers = case.get("expected_blockers", set())

        result = build_review_state(detected_type, metadata)

        # Check universal fields present
        for field in UNIVERSAL_FIELDS:
            if field not in result:
                failures.append(
                    f"Case {idx} ({detected_type}): missing universal field '{field}'"
                )

        # Check review_mode
        actual_mode = result.get("review_mode")
        if detected_type in EXPECTED_REVIEW_MODES:
            expected_mode = EXPECTED_REVIEW_MODES[detected_type]
            if actual_mode != expected_mode:
                failures.append(
                    f"Case {idx} ({detected_type}): review_mode={actual_mode!r}, expected {expected_mode!r}"
                )

        # Check review_type
        actual_type = result.get("review_type")
        if detected_type in EXPECTED_REVIEW_TYPES:
            expected_type = EXPECTED_REVIEW_TYPES[detected_type]
            if actual_type != expected_type:
                failures.append(
                    f"Case {idx} ({detected_type}): review_type={actual_type!r}, expected {expected_type!r}"
                )

        # Check expected blockers
        actual_blocker_types = {
            item.get("type") for item in result.get("blocking_review_items", [])
        }
        for expected_blocker in expected_blockers:
            if expected_blocker not in actual_blocker_types:
                failures.append(
                    f"Case {idx} ({detected_type}): expected blocker '{expected_blocker}' not found. "
                    f"Got: {actual_blocker_types}"
                )

        # Check expected non-blocking review items
        expected_non_blockers = case.get("expected_non_blockers", set())
        actual_non_blocker_types = {
            item.get("type") for item in result.get("non_blocking_review_items", [])
        }
        for expected_non_blocker in expected_non_blockers:
            if expected_non_blocker not in actual_non_blocker_types:
                failures.append(
                    f"Case {idx} ({detected_type}): expected non-blocking item "
                    f"'{expected_non_blocker}' not found. Got: {actual_non_blocker_types}"
                )

        # Check confidence cap when blockers exist
        blockers = result.get("blocking_review_items", [])
        if blockers:
            confidence = float(result.get("confidence") or 0)
            if confidence > 0.8:
                failures.append(
                    f"Case {idx} ({detected_type}): confidence {confidence} is too high while blockers exist"
                )

    if failures:
        print("FAIL - Universal review contract failures:")
        for f in failures:
            print(f"  x {f}")
        sys.exit(1)
    else:
        print(f"PASS - Universal review contract verified for {len(TEST_CASES)} test cases")


if __name__ == "__main__":
    run()
