"""Bounded, isolated checks for v2.066 move manifests."""

from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace


ROOT = Path(__file__).resolve().parents[1]
os.environ["DEBUG"] = "true"
sys.path.insert(0, str(ROOT / "backend"))

from app.core.config import settings  # noqa: E402
from app.services.move_manifest import write_move_manifest  # noqa: E402


def file(path: Path, role: str, size: int = 100) -> SimpleNamespace:
    return SimpleNamespace(
        file_path=str(path),
        file_name=path.name,
        extension=path.suffix,
        size_bytes=size,
        detected_role=role,
    )


def action(
    source: Path,
    destination: Path,
    *,
    status: str = "completed",
    error: str | None = None,
) -> SimpleNamespace:
    return SimpleNamespace(
        source_path=str(source),
        destination_path=str(destination),
        status=status,
        error_message=error,
    )


def configure(root: Path) -> None:
    settings.data_root = root
    settings.books_dir = root / "Books"
    settings.books_metadata_dir = root / "Books" / "Metadata"
    settings.audiobooks_dir = root / "Audiobooks" / "Library"
    settings.audiobooks_metadata_dir = root / "Audiobooks" / "Metadata"


def check_audiobook(root: Path) -> None:
    source = root / "_INGEST" / "Revan"
    destination = (
        root / "Audiobooks" / "Library" / "Unknown Author"
        / "Unknown Year - Star Wars The Old Republic Revan"
    )
    audio_source = source / "Disc 1" / "01 Track 1.mp3"
    artwork_source = source / "Star Wars The Old Republic Revan.jpg"
    audio_destination = destination / "Disc 1" / "01 Track 1.mp3"
    artwork_destination = destination / artwork_source.name
    batch = SimpleNamespace(
        id=5,
        source_kind="manual-drop",
        source_path=str(source),
        detected_type="audiobook",
        status="moved",
        confidence=1.0,
        suggested_destination=str(destination),
        metadata_confirmed=True,
        metadata_json={
            "review_type": "audiobook",
            "review_confirmed": True,
            "metadata_locked_for_move": True,
            "author": "Unknown Author",
            "title": "Star Wars The Old Republic Revan",
            "year": None,
            "narrator": None,
            "series": None,
            "series_index": None,
            "format": "MP3",
            "audiobook_file_count": 1,
            "accepted_unknown_author": True,
            "accepted_unknown_year": False,
            "accepted_unknown_narrator": False,
            "lookup_later": False,
        },
        files=[
            file(audio_source, "audiobook_audio", 12391540),
            file(artwork_source, "audiobook_artwork", 250000),
        ],
    )
    pointer, warnings = write_move_manifest(
        batch=batch,
        move_actions=[
            action(audio_source, audio_destination),
            action(artwork_source, artwork_destination),
        ],
        failed_messages=[],
    )
    assert not warnings, warnings
    assert pointer
    json_path = root / pointer["json_path"]
    markdown_path = root / str(pointer["markdown_path"])
    assert json_path.exists()
    assert markdown_path.exists()
    manifest = json.loads(json_path.read_text(encoding="utf-8"))
    assert manifest["archive_assistant_version"] == "v2.066B"
    assert manifest["detected_type"] == "audiobook"
    assert len(manifest["files_moved"]) == 1
    assert len(manifest["artwork_moved"]) == 1
    assert manifest["accepted_unknowns"]["author"] is True
    assert not manifest["failed_moves"]
    assert "C:\\" not in markdown_path.read_text(encoding="utf-8")


def check_book_collection(root: Path) -> None:
    source = root / "_INGEST" / "Self Help"
    epub_source = source / "Attraction Explained.epub"
    pdf_source = source / "1-2-3 Magic.pdf"
    cover_source = source / "Covers" / "Attraction Explained.jpg"
    epub_destination = (
        root / "Books" / "EPUB" / "Collections" / "Self Help"
        / "2016 - Attraction Explained" / epub_source.name
    )
    pdf_destination = (
        root / "Books" / "PDF" / "Collections" / "Self Help"
        / "Unknown Year - 1-2-3 Magic" / pdf_source.name
    )
    cover_destination = epub_destination.parent / cover_source.name
    batch = SimpleNamespace(
        id=100,
        source_kind="manual-drop",
        source_path=str(source),
        detected_type="book",
        status="moved",
        confidence=1.0,
        suggested_destination=None,
        metadata_confirmed=True,
        metadata_json={
            "review_type": "book_collection",
            "review_confirmed": True,
            "metadata_locked_for_move": True,
            "collection_title": "Self Help",
            "keep_collection_together": True,
            "collection_destination_root": (
                "Books/EPUB/Collections/Self Help"
            ),
            "ignored_sidecar_files": ["Read Me.txt", "metadata.opf"],
            "book_items": [
                {
                    "source_file": epub_source.name,
                    "include": True,
                    "title": "Attraction Explained",
                    "author": "Unknown Author",
                    "year": "2016",
                    "format": "EPUB",
                    "destination_preview": (
                        "Books/EPUB/Collections/Self Help/"
                        "2016 - Attraction Explained"
                    ),
                    "accepted_unknown_author": True,
                    "accepted_unknown_year": False,
                    "lookup_later": False,
                },
                {
                    "source_file": pdf_source.name,
                    "include": True,
                    "title": "1-2-3 Magic",
                    "author": "Thomas W. Phelan",
                    "year": None,
                    "format": "PDF",
                    "destination_preview": (
                        "Books/PDF/Collections/Self Help/"
                        "Unknown Year - 1-2-3 Magic"
                    ),
                    "accepted_unknown_author": False,
                    "accepted_unknown_year": False,
                    "lookup_later": True,
                },
            ],
        },
        files=[
            file(epub_source, "book_primary"),
            file(pdf_source, "book_primary"),
            file(cover_source, "book_artwork"),
        ],
    )
    pointer, warnings = write_move_manifest(
        batch=batch,
        move_actions=[
            action(epub_source, epub_destination),
            action(pdf_source, pdf_destination),
            action(cover_source, cover_destination),
        ],
        failed_messages=[],
    )
    assert not warnings, warnings
    assert pointer
    assert pointer["json_path"].startswith(
        "Books/Metadata/move_manifests/"
    )
    manifest = json.loads(
        (root / pointer["json_path"]).read_text(encoding="utf-8")
    )
    assert len(manifest["confirmed_metadata"]["items"]) == 2
    assert manifest["confirmed_metadata"]["keep_collection_together"] is True
    assert len(manifest["accepted_unknowns"]["items"]) == 2
    assert len(manifest["sidecars_ignored"]) == 2
    assert len(manifest["destination_roots"]) == 2


def check_failed_collision(root: Path) -> None:
    source = root / "_INGEST" / "Collision" / "example.epub"
    destination = root / "Books" / "EPUB" / "Example" / source.name
    batch = SimpleNamespace(
        id=201,
        source_kind="manual-drop",
        source_path=str(source.parent),
        detected_type="book",
        status="move_failed",
        confidence=1.0,
        suggested_destination=str(destination.parent),
        metadata_confirmed=True,
        metadata_json={
            "review_type": "book",
            "review_confirmed": True,
            "metadata_locked_for_move": False,
            "title": "Example",
            "author": "Example Author",
            "year": "2020",
            "format": "EPUB",
        },
        files=[file(source, "book_primary")],
    )
    pointer, warnings = write_move_manifest(
        batch=batch,
        move_actions=[],
        failed_messages=[
            f"Destination file conflict: {destination}"
        ],
    )
    assert not warnings, warnings
    assert pointer
    assert pointer["json_path"].startswith(
        "Books/Metadata/move_manifests/"
    )
    manifest = json.loads(
        (root / pointer["json_path"]).read_text(encoding="utf-8")
    )
    assert manifest["status_after_move"] == "move_failed"
    assert len(manifest["failed_moves"]) == 1
    assert not manifest["files_moved"]


def main() -> None:
    original = {
        "data_root": settings.data_root,
        "books_dir": settings.books_dir,
        "books_metadata_dir": settings.books_metadata_dir,
        "audiobooks_dir": settings.audiobooks_dir,
        "audiobooks_metadata_dir": settings.audiobooks_metadata_dir,
    }
    try:
        temporary = tempfile.mkdtemp(
            prefix="archive-v2-064-manifest-",
            dir=r"C:\tmp",
        )
        # Windows cleanup of nested manifest folders has hung in this
        # environment. Leave this small isolated fixture for manual cleanup.
        root = Path(temporary)
        configure(root)
        check_audiobook(root)
        check_book_collection(root)
        check_failed_collision(root)
    finally:
        for key, value in original.items():
            setattr(settings, key, value)

    print("v2.066 move manifest checks passed")


if __name__ == "__main__":
    main()
