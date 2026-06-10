#!/usr/bin/env python3
"""
check_tv_review_contract_no_regression.py

Ensures TV behavior is completely unchanged by the Universal Review Framework
additions. Shingeki no Kyojin pattern must still produce the same output.
"""
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

from app.services.review_state import build_review_state


SHINGEKI_SEASON_1_EPISODES = [
    {
        "source_file": f"S01E{i:02d}.mkv",
        "season_number": 1,
        "episode_number": i,
        "episode_code": f"S01E{i:02d}",
        "include": True,
        "is_special": False,
    }
    for i in range(1, 26)
]

SHINGEKI_SPECIALS = [
    {
        "source_file": "OAD01.mkv",
        "is_special": True,
        "special_label": "OAD01",
        "destination_group": "specials",
        "include": True,
    },
    {
        "source_file": "S01E13.5.mkv",
        "is_special": True,
        "special_label": "S01E13.5",
        "destination_group": "season",
        "season_number": 1,
        "include": True,
    },
]

SHINGEKI_METADATA = {
    "show_title": "Shingeki no Kyojin",
    "seasons": [
        {
            "season_number": 1,
            "episodes": SHINGEKI_SEASON_1_EPISODES + SHINGEKI_SPECIALS,
        }
    ],
    "metadata_warnings": [],
}


def run():
    failures = []

    result = build_review_state("video_tv_show", dict(SHINGEKI_METADATA))

    # Must produce no blockers for clean Shingeki data
    blockers = result.get("blocking_review_items", [])
    if blockers:
        failures.append(
            f"FAIL: unexpected blockers for clean Shingeki data: "
            f"{[b['type'] for b in blockers]}"
        )
    else:
        print("PASS: no blockers for clean Shingeki data")

    # review_mode must be guided_episode_review
    if result.get("review_mode") != "guided_episode_review":
        failures.append(
            f"FAIL: review_mode={result.get('review_mode')!r}, expected 'guided_episode_review'"
        )
    else:
        print("PASS: review_mode=guided_episode_review")

    # review_type must be tv_show
    if result.get("review_type") != "tv_show":
        failures.append(
            f"FAIL: review_type={result.get('review_type')!r}, expected 'tv_show'"
        )
    else:
        print("PASS: review_type=tv_show")

    # Excluded episode must not cause blocker
    metadata_with_excluded = dict(SHINGEKI_METADATA)
    metadata_with_excluded["seasons"] = [
        {
            "season_number": 1,
            "episodes": [
                {**ep, "include": False}
                if ep["source_file"] == "S01E01.mkv"
                else ep
                for ep in SHINGEKI_SEASON_1_EPISODES
            ],
        }
    ]
    result_excluded = build_review_state("video_tv_show", metadata_with_excluded)
    excluded_blockers = [
        b for b in result_excluded.get("blocking_review_items", [])
        if b.get("file_name") == "S01E01.mkv"
    ]
    if excluded_blockers:
        failures.append("FAIL: excluded episode produced a blocker")
    else:
        print("PASS: excluded episode does not produce a blocker")

    # Missing episode number must produce blocker
    metadata_with_missing = dict(SHINGEKI_METADATA)
    metadata_with_missing["seasons"] = [
        {
            "season_number": 1,
            "episodes": [
                {
                    "source_file": "unknown.mkv",
                    "season_number": 1,
                    "episode_number": None,
                    "include": True,
                    "is_special": False,
                    "preserve_source_filename": False,
                }
            ],
        }
    ]
    result_missing = build_review_state("video_tv_show", metadata_with_missing)
    missing_blockers = [
        b for b in result_missing.get("blocking_review_items", [])
        if b.get("type") == "missing_episode_number"
    ]
    if not missing_blockers:
        failures.append("FAIL: missing episode number did not produce a blocker")
    else:
        print("PASS: missing episode number correctly produces a blocker")

    if failures:
        print("\nFAIL — TV regression failures:")
        for f in failures:
            print(f"  x {f}")
        sys.exit(1)
    else:
        print("\nPASS — TV review contract regression check passed")


if __name__ == "__main__":
    run()
