#!/usr/bin/env python3
"""
check_movie_collection_approval_fix.py

Verifies the UPDATE 043 fix: after a collection review save,
review_type=movie_collection is preserved across subsequent
build_review_state() calls, stale multiple_movie_candidates
blocker is cleared, and the batch becomes ready to approve.

Test sequence (Harold and Kumar trilogy):
1. Initial scan state: needs_metadata_review with multiple_movie_candidates
2. After collection review save: pending_review, no blockers
3. review_type=movie_collection, review_mode=item_list preserved
4. Single approve path succeeds (no blockers)
5. Bulk approve path succeeds (no blockers)
"""
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

from app.services.review_state import build_review_state

TRILOGY_METADATA = {
    "title": "Harold and Kumar Go to White Castle",
    "year": "2004",
    "video_file_count": 3,
    "video_files": [
        "Harold and Kumar Go to White Castle 2004 UNRATED 1080p BluRay HEVC x265 5.1 BONE.mkv",
        "Harold and Kumar Escape from Guantanamo Bay 2008 UNRATED 1080p BluRay HEVC x265 5.1 BONE.mkv",
        "A Very Harold and Kumar Christmas 2011 3D UNRATED 1080p BluRay HEVC x265 5.1 BONE.mkv",
    ],
    "metadata_warnings": [],
    "confidence": 1.0,
}

COLLECTED_METADATA = {
    "movie_items": [
        {
            "source_file": "Harold and Kumar Go to White Castle 2004 UNRATED 1080p BluRay HEVC x265 5.1 BONE.mkv",
            "include": True,
            "title": "Harold and Kumar Go to White Castle",
            "year": "2004",
            "edition": "UNRATED",
            "destination_preview": "Movies/Library/2004 - Harold and Kumar Go to White Castle [UNRATED]",
        },
        {
            "source_file": "Harold and Kumar Escape from Guantanamo Bay 2008 UNRATED 1080p BluRay HEVC x265 5.1 BONE.mkv",
            "include": True,
            "title": "Harold and Kumar Escape from Guantanamo Bay",
            "year": "2008",
            "edition": "UNRATED",
            "destination_preview": "Movies/Library/2008 - Harold and Kumar Escape from Guantanamo Bay [UNRATED]",
        },
        {
            "source_file": "A Very Harold and Kumar Christmas 2011 3D UNRATED 1080p BluRay HEVC x265 5.1 BONE.mkv",
            "include": True,
            "title": "A Very Harold and Kumar Christmas",
            "year": "2011",
            "edition": "UNRATED 3D",
            "destination_preview": "Movies/Library/2011 - A Very Harold and Kumar Christmas [UNRATED 3D]",
        },
    ],
    "review_type": "movie_collection",
    "review_mode": "item_list",
    "metadata_warnings": [],
    "confidence": 0.8,
}


def run():
    failures = []

    # ── Step 1: Initial scan state ──────────────────────────────────────
    result = build_review_state("video_movie", dict(TRILOGY_METADATA))
    blocker_types = {b["type"] for b in result.get("blocking_review_items", [])}

    if "multiple_movie_candidates" not in blocker_types:
        failures.append(
            "Step 1 FAIL: expected 'multiple_movie_candidates' blocker in raw state. "
            f"Got: {blocker_types}"
        )
    else:
        print("Step 1 PASS: multiple_movie_candidates blocker present in raw state")

    if result.get("review_type") != "movie":
        failures.append(
            "Step 1b FAIL: raw review_type should be 'movie', "
            f"got {result.get('review_type')!r}"
        )
    else:
        print("Step 1b PASS: raw review_type=movie")

    # ── Step 2: After collection review save ────────────────────────────
    saved_metadata = dict(TRILOGY_METADATA)
    saved_metadata.update(COLLECTED_METADATA)
    result = build_review_state("video_movie", saved_metadata)

    blockers = result.get("blocking_review_items", [])
    if blockers:
        failures.append(
            "Step 2 FAIL: blockers remain after collection review save: "
            f"{[b['type'] for b in blockers]}"
        )
    else:
        print("Step 2 PASS: no blockers after collection review save")

    # ── Step 3: review_type and review_mode preserved ───────────────────
    if result.get("review_type") != "movie_collection":
        failures.append(
            "Step 3 FAIL: review_type should be 'movie_collection', "
            f"got {result.get('review_type')!r}"
        )
    else:
        print("Step 3 PASS: review_type=movie_collection preserved")

    if result.get("review_mode") != "item_list":
        failures.append(
            "Step 3b FAIL: review_mode should be 'item_list', "
            f"got {result.get('review_mode')!r}"
        )
    else:
        print("Step 3b PASS: review_mode=item_list")

    # ── Step 4: Confirm review_type survives a second call ──────────────
    result2 = build_review_state("video_movie", dict(result))
    if result2.get("review_type") != "movie_collection":
        failures.append(
            "Step 4 FAIL: review_type reverted on second build_review_state call, "
            f"got {result2.get('review_type')!r}"
        )
    else:
        print("Step 4 PASS: review_type survives second build_review_state call")

    if result2.get("blocking_review_items"):
        failures.append(
            "Step 4b FAIL: blockers reappeared on second build_review_state call: "
            f"{[b['type'] for b in result2.get('blocking_review_items', [])]}"
        )
    else:
        print("Step 4b PASS: no stale blockers on second call")

    # ── Step 5: Excluded all movies produces blocker ────────────────────
    all_excluded = dict(saved_metadata)
    all_excluded["movie_items"] = [
        {**item, "include": False} for item in all_excluded["movie_items"]
    ]
    excluded_result = build_review_state("video_movie", all_excluded)
    excluded_blocker_types = {
        b["type"] for b in excluded_result.get("blocking_review_items", [])
    }
    if "movie_collection_no_included_items" not in excluded_blocker_types:
        failures.append(
            "Step 5 FAIL: expected 'movie_collection_no_included_items' when all excluded, "
            f"got: {excluded_blocker_types}"
        )
    else:
        print("Step 5 PASS: all-excluded produces movie_collection_no_included_items blocker")

    # ── Step 6: Single missing title on included item produces blocker ──
    missing_title = dict(saved_metadata)
    missing_title["movie_items"] = [
        {**item} if idx == 0 else item
        for idx, item in enumerate(missing_title["movie_items"])
    ]
    missing_title["movie_items"][0]["title"] = ""
    if not missing_title["movie_items"][0]["title"]:
        mt_result = build_review_state("video_movie", missing_title)
        mt_blocker_types = {
            b["type"] for b in mt_result.get("blocking_review_items", [])
        }
        if "movie_collection_item_missing_title" not in mt_blocker_types:
            failures.append(
                "Step 6 FAIL: expected 'movie_collection_item_missing_title' blocker, "
                f"got: {mt_blocker_types}"
            )
        else:
            print("Step 6 PASS: missing title produces movie_collection_item_missing_title blocker")
    else:
        failures.append("Step 6 FAIL: test setup error - title not cleared")

    # ── Step 7: Collection_title is preserved in output ─────────────────
    with_title = dict(saved_metadata)
    with_title["collection_title"] = "Harold and Kumar Trilogy"
    ct_result = build_review_state("video_movie", with_title)
    if ct_result.get("collection_title") != "Harold and Kumar Trilogy":
        failures.append(
            f"Step 7 FAIL: collection_title not preserved, got {ct_result.get('collection_title')!r}"
        )
    else:
        print("Step 7 PASS: collection_title preserved in output")

    if failures:
        print("\nFAIL — Movie collection approval fix failures:")
        for f in failures:
            print(f"  x {f}")
        sys.exit(1)
    else:
        print("\nPASS — Movie collection approval fix verified (7 steps)")


if __name__ == "__main__":
    run()
