#!/usr/bin/env python3
"""Regression checks for release-folder name clean-up.

Real downloads carry uploader handles, bitrate numbers, emoji, and remaster
years in their folder names. These must not leak into the suggested album
title or release year, while ordinary titles stay untouched.
"""

from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "backend"))

from app.services.music_metadata import parse_music_folder_name  # noqa: E402
from app.services.name_cleanup import strip_windows_copy_suffix  # noqa: E402

CASES = [
    # (folder name, artist, album, year)
    ("Pink Floyd - The Wall (2007 Remaster) [FLAC] 88", "Pink Floyd", "The Wall", None),
    ("Daft Punk - Random Access Memories (10th Anniversary) [FLAC] 88", "Daft Punk", "Random Access Memories (10th Anniversary)", None),
    ("Led Zeppelin - Physical Presence [2026] [FLAC]-Sc4r3cr0w", "Led Zeppelin", "Physical Presence", "2026"),
    ("Mac Miller - Discography [FLAC] [PMEDIA] ⭐️", "Mac Miller", "Discography", None),
    ("Mac Miller - Discography [FLAC] [PMEDIA] ⭐️ - Copy", "Mac Miller", "Discography", None),
    ("The Beatles - Abbey Road (2019 Remaster)", "The Beatles", "Abbey Road", None),
    ("Radiohead - OK Computer [Remastered 2009] [FLAC]", "Radiohead", "OK Computer", None),
    # Ordinary names must not change.
    ("Deadmau5 - 2009 - For Lack of a Better Name", "Deadmau5", "For Lack of a Better Name", "2009"),
    ("Nas - 1994 - Illmatic", "Nas", "Illmatic", "1994"),
    ("Blink-182 - Enema of the State (1999)", "Blink-182", "Enema of the State", "1999"),
    ("Prince - 1999", "Prince", "1999", "1999"),
]

COPY_CASES = [
    ("Dune by Frank Herbert audio book - Copy", "Dune by Frank Herbert audio book"),
    ("Golden Son - Pierce Brown - Copy (2).m4b", "Golden Son - Pierce Brown.m4b"),
    ("Copycat - Copy Machine", "Copycat - Copy Machine"),
    ("Album - Copy of a Copy", "Album - Copy of a Copy"),
]


def run() -> None:
    failures: list[str] = []
    for name, artist, album, year in CASES:
        got = parse_music_folder_name(name)
        expected = {"artist": artist, "album": album, "year": year}
        if got != expected:
            failures.append(f"{name!r}: got {got}, expected {expected}")
    for value, expected in COPY_CASES:
        got = strip_windows_copy_suffix(value)
        if got != expected:
            failures.append(f"copy suffix {value!r}: got {got!r}, expected {expected!r}")
    if failures:
        print("FAIL - release folder noise")
        for failure in failures:
            print("  x", failure)
        raise SystemExit(1)
    print(f"PASS - release folder noise ({len(CASES) + len(COPY_CASES)} cases)")


if __name__ == "__main__":
    run()
