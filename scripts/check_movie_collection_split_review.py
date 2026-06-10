#!/usr/bin/env python3
"""
check_movie_collection_split_review.py

Verifies that a folder containing multiple unrelated movie files
(e.g. Harold and Kumar trilogy) is flagged correctly, produces
the right review_type, and that after a collection review save
each movie has its own destination preview.
"""
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

from app.services.review_state import build_review_state
from app.services.review_items import build_review_items_for_movie_collection


# ── Simulate what the scanner produces for a 3-movie folder ──────────────────

TRILOGY_METADATA = {
    "title": "Harold and Kumar Go to White Castle",
    "year": "2004",
    "video_file_count": 3,
    "video_files": [
        "Harold and Kumar Go to White Castle 2004 UNRATED 1080p BluRay HEVC x265 5.1 BONE.mkv",
        "Harold & Kumar Escape from Guantanamo Bay 2008 UNRATED 1080p BluRay HEVC x265 5.1 BONE.mkv",
        "A Very Harold & Kumar Christmas 2011 3D UNRATED 1080p BluRay HEVC x265 5.1 BONE.mkv",
    ],
    "metadata_warnings": [],
    "confidence": 1.0,
}


class FakeIngestFile:
    def __init__(self, file_name):
        self.file_name = file_name
        self.file_path = f"/fake/_INGEST/trilogy/{file_name}"
        self.detected_role = "video_file"


TRILOGY_FILES = [FakeIngestFile(f) for f in TRILOGY_METADATA["video_files"]]


def run():
    failures = []

    # Step 1: build_review_state on raw scanner output should produce multiple_movie_candidates
    result = build_review_state("video_movie", dict(TRILOGY_METADATA))
    blocker_types = {item["type"] for item in result.get("blocking_review_items", [])}

    if "multiple_movie_candidates" not in blocker_types:
        failures.append(
            "Step 1 FAIL: expected 'multiple_movie_candidates' blocker for 3-movie folder. "
            f"Got: {blocker_types}"
        )
    else:
        print("Step 1 PASS: multiple_movie_candidates blocker present")

    # Step 2: verify confidence is capped below 0.8 while blocker exists
    confidence = float(result.get("confidence") or 0)
    if confidence > 0.8:
        failures.append(
            f"Step 2 FAIL: confidence={confidence} too high while multiple_movie_candidates exists"
        )
    else:
        print(f"Step 2 PASS: confidence capped at {confidence}")

    # Step 3: build_review_items_for_movie_collection with no prior movie_items
    # should produce one item per video file
    items = build_review_items_for_movie_collection(TRILOGY_METADATA, TRILOGY_FILES)
    if len(items) != 3:
        failures.append(f"Step 3 FAIL: expected 3 review items, got {len(items)}")
    else:
        print(f"Step 3 PASS: {len(items)} review items produced")

    # Step 4: simulate a collection review save -- apply movie_items and rebuild state
    reviewed_metadata = dict(TRILOGY_METADATA)
    reviewed_metadata["movie_items"] = [
        {
            "source_file": "Harold and Kumar Go to White Castle 2004 UNRATED 1080p BluRay HEVC x265 5.1 BONE.mkv",
            "include": True,
            "title": "Harold and Kumar Go to White Castle",
            "year": "2004",
            "edition": "UNRATED",
            "destination_preview": "Movies/Library/2004 - Harold and Kumar Go to White Castle [UNRATED]",
        },
        {
            "source_file": "Harold & Kumar Escape from Guantanamo Bay 2008 UNRATED 1080p BluRay HEVC x265 5.1 BONE.mkv",
            "include": True,
            "title": "Harold & Kumar Escape from Guantanamo Bay",
            "year": "2008",
            "edition": "UNRATED",
            "destination_preview": "Movies/Library/2008 - Harold _ Kumar Escape from Guantanamo Bay [UNRATED]",
        },
        {
            "source_file": "A Very Harold & Kumar Christmas 2011 3D UNRATED 1080p BluRay HEVC x265 5.1 BONE.mkv",
            "include": True,
            "title": "A Very Harold & Kumar Christmas",
            "year": "2011",
            "edition": "UNRATED 3D",
            "destination_preview": "Movies/Library/2011 - A Very Harold _ Kumar Christmas [UNRATED 3D]",
        },
    ]
    reviewed_metadata["review_type"] = "movie_collection"
    reviewed_metadata["metadata_warnings"] = []

    reviewed_result = build_review_state("video_movie", reviewed_metadata)
    reviewed_blockers = reviewed_result.get("blocking_review_items", [])

    if reviewed_blockers:
        failures.append(
            f"Step 4 FAIL: after review save, unexpected blockers remain: "
            f"{[b['type'] for b in reviewed_blockers]}"
        )
    else:
        print("Step 4 PASS: no blockers after complete collection review")

    # Step 5: verify review_type and review_mode set correctly
    if reviewed_result.get("review_type") != "movie":
        failures.append(
            f"Step 5 FAIL: review_type={reviewed_result.get('review_type')!r}, expected 'movie'"
        )
    else:
        print("Step 5 PASS: review_type=movie")

    if reviewed_result.get("review_mode") != "item_list":
        failures.append(
            f"Step 5b FAIL: review_mode={reviewed_result.get('review_mode')!r}, expected 'item_list'"
        )
    else:
        print("Step 5b PASS: review_mode=item_list for movie collection")

    # Step 6: verify that three separate destination folders would be created (not one)
    destinations = [
        item["destination_preview"]
        for item in reviewed_metadata["movie_items"]
        if item.get("include")
    ]
    if len(set(destinations)) != 3:
        failures.append(
            f"Step 6 FAIL: expected 3 distinct destination folders, got {len(set(destinations))}: {destinations}"
        )
    else:
        print(f"Step 6 PASS: {len(set(destinations))} distinct destination folders")

    if failures:
        print("\nFAIL — Movie collection review failures:")
        for f in failures:
            print(f"  x {f}")
        sys.exit(1)
    else:
        print("\nPASS — Movie collection split review contract verified")


if __name__ == "__main__":
    run()
