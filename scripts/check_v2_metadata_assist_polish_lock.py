"""Bounded regression proof for the v2.060 metadata assist polish lock."""

from __future__ import annotations

import os
import sys
from pathlib import Path
from types import SimpleNamespace


ROOT = Path(__file__).resolve().parents[1]
os.environ["DEBUG"] = "true"
sys.path.insert(0, str(ROOT / "backend"))

from app.services import audiobook_metadata, book_metadata  # noqa: E402
from app.services.metadata_candidates import (  # noqa: E402
    METADATA_ASSIST_VERSION,
    make_candidate,
    normalize_metadata_text,
    preferred_candidate_value,
)
from app.services.pdf_metadata_reader import read_pdf_metadata  # noqa: E402
from app.services.title_display import destination_title  # noqa: E402


class FakePdfInfo(dict):
    @property
    def title(self):
        return self.get("/Title")

    @property
    def author(self):
        return self.get("/Author")

    @property
    def creation_date(self):
        return self.get("/CreationDate")


def install_fake_pypdf(metadata: dict, xmp=None) -> object | None:
    previous = sys.modules.get("pypdf")

    class FakePdfReader:
        def __init__(self, path: str):
            self.metadata = FakePdfInfo(metadata)
            self.xmp_metadata = xmp

    sys.modules["pypdf"] = SimpleNamespace(PdfReader=FakePdfReader)
    return previous


def install_broken_xmp_pypdf(metadata: dict) -> object | None:
    previous = sys.modules.get("pypdf")

    class FakePdfReader:
        def __init__(self, path: str):
            self.metadata = FakePdfInfo(metadata)

        @property
        def xmp_metadata(self):
            raise ValueError("invalid XMP XML")

    sys.modules["pypdf"] = SimpleNamespace(PdfReader=FakePdfReader)
    return previous


def restore_pypdf(previous: object | None) -> None:
    if previous is None:
        sys.modules.pop("pypdf", None)
    else:
        sys.modules["pypdf"] = previous


def main() -> None:
    assert METADATA_ASSIST_VERSION == "v2.060"
    assert normalize_metadata_text("Jim  Cobb") == "Jim Cobb"

    parsed = book_metadata.parse_book_name(
        "@SoftSkills101 - Atomic Habits.pdf"
    )
    assert parsed["title"] == "Atomic Habits", parsed
    assert parsed["author"] == "Unknown Author", parsed

    previous_pypdf = install_fake_pypdf({
        "/Title": "@SoftSkills101",
        "/Author": "Microsoft Word",
        "/CreationDate": "D:20180101000000",
        "/Creator": "Adobe Acrobat",
        "/Producer": "Calibre",
    })
    try:
        bad_pdf, errors = read_pdf_metadata(
            Path("@SoftSkills101 - Atomic Habits.pdf"),
            source_labels=["@SoftSkills101"],
        )
    finally:
        restore_pypdf(previous_pypdf)
    assert bad_pdf == {"year": "2018"}, bad_pdf
    assert errors == ["pdf_metadata_generic_ignored"]

    previous_pypdf = install_fake_pypdf({
        "/Title": "Atomic Habits",
        "/Author": "James Clear",
        "/CreationDate": "D:20180101000000",
    })
    try:
        good_pdf, errors = read_pdf_metadata(Path("Atomic Habits.pdf"))
    finally:
        restore_pypdf(previous_pypdf)
    assert good_pdf == {
        "title": "Atomic Habits",
        "author": "James Clear",
        "year": "2018",
    }
    assert errors == []

    previous_pypdf = install_broken_xmp_pypdf({
        "/Title": "Readable Document Info",
        "/Author": "Valid Author",
        "/CreationDate": "D:20200101000000",
    })
    try:
        broken_xmp_pdf, errors = read_pdf_metadata(
            Path("broken-xmp.pdf")
        )
    finally:
        restore_pypdf(previous_pypdf)
    assert broken_xmp_pdf == {
        "title": "Readable Document Info",
        "author": "Valid Author",
        "year": "2020",
    }
    assert errors == ["pdf_xmp_invalid:ValueError"]

    long_title = (
        "Prepper's Survival Medicine Handbook: A Lifesaving Collection of "
        "Emergency Procedures from U.S. Army Field Manuals"
    )
    assert destination_title(long_title) == (
        "Prepper's Survival Medicine Handbook"
    )

    original_collect_books = book_metadata.collect_book_files
    original_read_pdf = book_metadata.read_pdf_metadata
    book_metadata.collect_book_files = lambda source: {
        "books": [Path("@SoftSkills101 - Atomic Habits.pdf")],
        "artwork": [],
        "sidecars": [],
        "other": [],
    }
    book_metadata.read_pdf_metadata = lambda path, source_labels=None: (
        {},
        [],
    )
    try:
        built_book = book_metadata.build_single_book_metadata(
            Path("@SoftSkills101 - Atomic Habits.pdf"),
            Path("Books"),
        )
    finally:
        book_metadata.collect_book_files = original_collect_books
        book_metadata.read_pdf_metadata = original_read_pdf
    assert built_book["title"] == "Atomic Habits"
    assert built_book["author"] == "Unknown Author"
    assert built_book["metadata_assist_version"] == "v2.060"
    runtime = built_book["candidate_runtime"]
    assert runtime["candidate_filter_active"] is True
    assert runtime["source_labels_removed"] >= 1
    assert runtime["pdf_metadata_attempted"] is True
    assert runtime["epub_metadata_attempted"] is False
    assert runtime["metadata_reader_errors"] == []

    epub_author = make_candidate(
        "author",
        "Frank Herbert",
        "epub_opf_author",
        "EPUB package metadata",
        0.92,
    )
    filename_fragment = make_candidate(
        "author",
        "A Proje",
        "filename",
        "Filename",
        0.68,
    )
    assert epub_author is not None and filename_fragment is not None
    assert preferred_candidate_value(
        {"author": [filename_fragment, epub_author]},
        "author",
        "Unknown Author",
        min_confidence="high",
        require_not_filename_guess=True,
    ) == "Frank Herbert"

    generic_album = "Unknown Album (11/19/2011 3:04:25 PM)"
    original_collect_audio = audiobook_metadata.collect_audiobook_files
    original_extract_audio = audiobook_metadata.extract_audio_metadata
    audiobook_metadata.collect_audiobook_files = lambda source: {
        "audio": [Path("Star Wars The Old Republic Revan/Disc 1/01 Track 1.mp3")],
        "artwork": [],
        "sidecars": [],
        "other": [],
    }
    audiobook_metadata.extract_audio_metadata = lambda path: {
        "title": generic_album,
        "chapter_title": "Track 1",
    }
    try:
        built_audio = audiobook_metadata.build_audiobook_metadata(
            Path("Star Wars The Old Republic Revan"),
            Path("Audiobooks"),
        )
    finally:
        audiobook_metadata.collect_audiobook_files = original_collect_audio
        audiobook_metadata.extract_audio_metadata = original_extract_audio
    assert built_audio["title"] == "Star Wars The Old Republic Revan"
    assert built_audio["author"] == "Unknown Author"
    assert built_audio["format"] == "MP3"
    assert built_audio["metadata_assist_version"] == "v2.060"
    assert built_audio["candidate_runtime"]["candidate_filter_active"] is True
    assert built_audio["candidate_runtime"]["generic_audio_tags_hidden"] >= 1

    collection_ui = (
        ROOT / "frontend/src/components/BookCollectionEditor.tsx"
    ).read_text(encoding="utf-8")
    for label in (
        "Show PDF-only repair",
        "Show EPUB-only repair",
        "Apply author to visible repair items",
        "Apply year to visible repair items",
        "Exclude visible repair items",
        "Restore excluded visible items",
        "PDF metadata limited",
        "pypdf is not installed",
        "embedded metadata looked generic and was ignored",
        "no reliable embedded author/year found",
        "This excludes items from this batch review only. It does not delete files.",
    ):
        assert label in collection_ui, label

    detail_ui = (
        ROOT / "frontend/src/components/BatchDetail.tsx"
    ).read_text(encoding="utf-8")
    for label in (
        "Destination mode:",
        "Each included book will route to its own destination.",
        "Previewing first item:",
    ):
        assert label in detail_ui, label

    audiobook_ui = (
        ROOT / "frontend/src/components/AudiobookMetadataEditor.tsx"
    ).read_text(encoding="utf-8")
    for label in ("Manual author", "Manual narrator", "Manual year"):
        assert label in audiobook_ui, label

    print("v2.060 metadata assist polish lock checks passed")


if __name__ == "__main__":
    main()
