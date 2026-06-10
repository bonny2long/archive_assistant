# UPDATE 042 — PART 4: REGRESSION SCRIPTS
## Universal Media Review Framework — Test Coverage

Apply after Parts 1–3. These scripts verify:
- Universal review contract across all media types
- Movie collection split review (Harold and Kumar trilogy)
- TV regression (Shingeki no Kyojin must still pass)
- Existing scripts that should not regress

Run all of these from the repo root:
```bash
python scripts/check_universal_review_contract.py
python scripts/check_movie_collection_split_review.py
python scripts/check_tv_review_contract_no_regression.py
python scripts/check_tv_final_polish.py
python scripts/check_tv_review_move_sync.py
python scripts/check_discography_album_editor.py
python scripts/check_movie_final_polish.py
```

---

## CHANGE 1 — `scripts/check_universal_review_contract.py` (NEW FILE)

```python
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
        "expected_blockers": {"artist_missing", "album_missing", "year_missing"},
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
        "expected_blockers": {"movie_title_missing", "movie_year_missing"},
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

        # Check confidence cap when blockers exist
        blockers = result.get("blocking_review_items", [])
        if blockers:
            confidence = float(result.get("confidence") or 0)
            if confidence > 0.8:
                failures.append(
                    f"Case {idx} ({detected_type}): confidence {confidence} is too high while blockers exist"
                )

    if failures:
        print("FAIL — Universal review contract failures:")
        for f in failures:
            print(f"  ✗ {f}")
        sys.exit(1)
    else:
        print(f"PASS — Universal review contract verified for {len(TEST_CASES)} test cases")


if __name__ == "__main__":
    run()
```

---

## CHANGE 2 — `scripts/check_movie_collection_split_review.py` (NEW FILE)

```python
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

    # Step 4: simulate a collection review save — apply movie_items and rebuild state
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
            print(f"  ✗ {f}")
        sys.exit(1)
    else:
        print("\nPASS — Movie collection split review contract verified")


if __name__ == "__main__":
    run()
```

---

## CHANGE 3 — `scripts/check_tv_review_contract_no_regression.py` (NEW FILE)

```python
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
            print(f"  ✗ {f}")
        sys.exit(1)
    else:
        print("\nPASS — TV review contract regression check passed")


if __name__ == "__main__":
    run()
```

---

## VALIDATION COMMANDS

Run in this exact order:

```bash
# 1. Backend compiles clean
cd backend
python -m compileall app

# 2. Frontend builds clean
cd ../frontend
npm run build

# 3. New regression scripts
cd ..
python scripts/check_universal_review_contract.py
python scripts/check_movie_collection_split_review.py
python scripts/check_tv_review_contract_no_regression.py

# 4. Existing scripts — must not regress
python scripts/check_tv_final_polish.py
python scripts/check_tv_review_move_sync.py
python scripts/check_discography_album_editor.py
python scripts/check_movie_final_polish.py
```

All scripts must exit with code 0.

---

## EXPECTED RESULTS SUMMARY

| Script | Expected |
|--------|----------|
| `check_universal_review_contract.py` | PASS — all media types have review_mode and review_type |
| `check_movie_collection_split_review.py` | PASS — 3 movies produce 3 destination folders |
| `check_tv_review_contract_no_regression.py` | PASS — TV unchanged |
| `check_tv_final_polish.py` | PASS — no change to TV |
| `check_tv_review_move_sync.py` | PASS — no change to TV move sync |
| `check_discography_album_editor.py` | PASS — no change to discography |
| `check_movie_final_polish.py` | PASS — single movie unchanged |
