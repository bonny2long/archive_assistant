#!/usr/bin/env python3
"""Regression checks for multi-disc naming.

Real releases arrive tagged "Dune Disc 1" (audiobook, no disc tag) or
"The Wall (1)" with disc tag 1 in folder "CD 1" (music). Grouping on those
raw names split one release into one batch per disc. These checks pin the
rule that removes a trailing disc marker only on clear evidence.
"""

from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "backend"))

from app.models.archive import IngestBatch, IngestFile  # noqa: E402
from app.services import universal_ingestion as ui  # noqa: E402
from app.services.disc_markers import is_disc_folder_name, split_disc_suffix  # noqa: E402

SPLIT_CASES = [
    # (value, disc_tag, folder, expected)
    ("Dune Disc 1", None, "Dune Disc 1", ("Dune", 1)),
    ("Dune Disc 16", None, None, ("Dune", 16)),
    ("Dune Dics 4 Disc 4", None, "Dune Disc 4", ("Dune Dics 4", 4)),
    ("Random Access Memories (Disc 2)", None, None, ("Random Access Memories", 2)),
    ("Album - CD2", None, None, ("Album", 2)),
    ("Album [CD 3]", None, None, ("Album", 3)),
    ("The Wall (1)", "1", "CD 1", ("The Wall", 1)),
    ("The Wall (2)", "2/2", "CD 2", ("The Wall", 2)),
    # Bare "(N)" without agreeing tag AND folder evidence stays untouched.
    ("The Wall (1)", "2", "CD 1", ("The Wall (1)", None)),
    ("The Wall (1)", "1", "The Wall", ("The Wall (1)", None)),
    ("The Wall (1)", None, None, ("The Wall (1)", None)),
    ("Chapter (12)", None, "Book", ("Chapter (12)", None)),
    # Names that merely contain disc-like words or numbers stay untouched.
    ("Mac Miller - Discography", None, None, ("Mac Miller - Discography", None)),
    ("Disco 2000", None, None, ("Disco 2000", None)),
    ("Blink-182", None, None, ("Blink-182", None)),
    ("1999", None, None, ("1999", None)),
    ("CD 1", None, None, ("CD 1", None)),
]

FOLDER_CASES = [
    ("CD 1", True),
    ("Disc 02", True),
    ("Dune Disc 1", True),
    ("Album (Disc 2)", True),
    ("Mac Miller - Discography [FLAC]", False),
    ("Pink Floyd - The Wall (2007 Remaster) [FLAC] 88", False),
    ("Season 1", False),
]


def _dune_like_batch(*, author_typos: int, title_typo_disc: int | None, majority: bool = True) -> IngestBatch:
    """Mirror the real Dune download: 'Dune Disc N' folders, album tags
    'Dune Disc N', no disc tags, track numbers restarting on every disc."""
    root = "C:/ready/Dune by Frank Herbert (dramatized audio) audio book"
    batch = IngestBatch(
        id=1,
        source_path=root,
        detected_type="audiobook",
        status="pending_review",
        metadata_json={"author": "Frank Herbert", "title": "Dune"},
    )
    files = []
    discs = range(1, 5)
    for disc in discs:
        for track in range(1, 4):
            author = "Frank Herbert"
            if author_typos and disc == 2 and track <= author_typos:
                author = "Frank Herber"
            if not majority and disc >= 2:
                author = "Someone Else"
            album = f"Dune Disc {disc}"
            if title_typo_disc == disc:
                album = f"Dune Dics {disc} Disc {disc}"
            files.append(IngestFile(
                file_path=f"{root}/Dune Disc {disc}/{track:02d} {track}.mp3",
                file_name=f"{track:02d} {track}.mp3",
                extension=".mp3",
                size_bytes=1,
                detected_role="audiobook_audio",
                metadata_json={"album": album, "artist": author, "tracknumber": str(track)},
            ))
    batch.files = files
    return batch


def run() -> None:
    failures: list[str] = []

    # Real-world shape: one mistyped disc title and one mistyped author tag.
    ctx = ui._single_book_audiobook_context(
        batch := _dune_like_batch(author_typos=1, title_typo_disc=4),
        ui.classify_batch_files(batch),
    )
    if not ctx:
        failures.append("multi-disc audiobook with one stray title and author tag should be one book")
    else:
        if ctx.get("disc_count") != 4:
            failures.append(f"disc numbers should come from disc folders, got {ctx.get('disc_count')}")
        if ctx.get("author_outliers") != ["frank-herber"] or ctx.get("title_outliers") != ["dune-dics-4"]:
            failures.append(f"outliers must stay visible, got {ctx.get('author_outliers')} {ctx.get('title_outliers')}")
    # A genuine second author on most files must NOT be forced into one book.
    batch = _dune_like_batch(author_typos=0, title_typo_disc=None, majority=False)
    if ui._single_book_audiobook_context(batch, ui.classify_batch_files(batch)):
        failures.append("files mostly by a different author must not collapse into one book")

    for value, disc_tag, folder, expected in SPLIT_CASES:
        got = split_disc_suffix(value, disc_tag=disc_tag, folder_name=folder)
        if got != expected:
            failures.append(f"split_disc_suffix({value!r}, {disc_tag!r}, {folder!r}) = {got!r}, expected {expected!r}")
    for name, expected in FOLDER_CASES:
        if is_disc_folder_name(name) != expected:
            failures.append(f"is_disc_folder_name({name!r}) should be {expected}")
    if failures:
        print("FAIL - multi-disc disc markers")
        for failure in failures:
            print("  x", failure)
        raise SystemExit(1)
    print(f"PASS - multi-disc disc markers ({len(SPLIT_CASES) + len(FOLDER_CASES)} cases)")


if __name__ == "__main__":
    run()
