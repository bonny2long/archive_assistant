"""Bounded manifest-shape checks for v2.066 movies."""

import json
import tempfile
from pathlib import Path
from types import SimpleNamespace

from app.core.config import settings
from app.services.move_manifest import (
    ARCHIVE_ASSISTANT_VERSION,
    _accepted_unknowns,
    _confirmed_metadata,
    _lookup_later,
    _summary,
    write_move_manifest,
)


def check_collection_manifest_location() -> None:
    original_data_root = settings.data_root
    original_movies_metadata_dir = settings.movies_metadata_dir
    root = Path(tempfile.mkdtemp(
        prefix="archive-v2-066b-movie-manifest-",
        dir=r"C:\tmp",
    ))
    try:
        settings.data_root = root
        settings.movies_metadata_dir = root / "Movies" / "Metadata"
        source = root / "_INGEST" / "Harold and Kumar Trilogy"
        destinations = [
            root / "Movies" / "Library"
            / "2004 - Harold and Kumar Go to White Castle"
            / "Harold and Kumar Go to White Castle 2004.mkv",
            root / "Movies" / "Library"
            / "2008 - Harold and Kumar Escape from Guantanamo Bay"
            / "Harold and Kumar Escape from Guantanamo Bay 2008.mkv",
            root / "Movies" / "Library"
            / "2011 - A Very Harold And Kumar Christmas"
            / "A Very Harold And Kumar Christmas 2011.mkv",
        ]
        movie_items = [
            {
                "source_file": destination.name,
                "title": destination.parent.name.split(" - ", 1)[1],
                "year": destination.parent.name[:4],
                "format": "MKV",
                "include": True,
                "destination_preview": destination.parent.relative_to(root).as_posix(),
            }
            for destination in destinations
        ]
        batch = SimpleNamespace(
            id=66,
            source_kind="manual-drop",
            source_path=str(source),
            detected_type="video_movie",
            status="moved",
            confidence=1.0,
            suggested_destination=str(destinations[-1].parent),
            metadata_confirmed=True,
            metadata_json={
                "review_type": "movie_collection",
                "review_confirmed": True,
                "metadata_locked_for_move": True,
                "collection_title": "Harold and Kumar Trilogy",
                "movie_items": movie_items,
            },
            files=[],
        )
        actions = [
            SimpleNamespace(
                source_path=str(source / destination.name),
                destination_path=str(destination),
                status="completed",
                error_message=None,
            )
            for destination in destinations
        ]
        pointer, warnings = write_move_manifest(
            batch=batch,
            move_actions=actions,
            failed_messages=[],
        )
        assert not warnings, warnings
        assert pointer is not None
        assert pointer["json_path"].startswith(
            "Movies/Metadata/move_manifests/"
        )
        assert "Movies/Library/" not in pointer["json_path"]
        manifest = json.loads(
            (root / pointer["json_path"]).read_text(encoding="utf-8")
        )
        assert manifest["archive_assistant_version"] == "v2.066B"
        assert len(manifest["destination_roots"]) == 3
    finally:
        settings.data_root = original_data_root
        settings.movies_metadata_dir = original_movies_metadata_dir


def main() -> None:
    metadata = {
        "review_type": "movie_collection",
        "collection_title": "Example Trilogy",
        "movie_items": [
            {
                "source_file": "Example One (2020).mkv",
                "title": "Example One",
                "year": "2020",
                "format": "MKV",
                "include": True,
            },
            {
                "source_file": "Example Two.mkv",
                "title": "Example Two",
                "year": None,
                "format": "MKV",
                "include": True,
                "accepted_unknown_year": True,
                "lookup_later": True,
            },
        ],
    }
    assert ARCHIVE_ASSISTANT_VERSION == "v2.066B"
    confirmed = _confirmed_metadata("video_movie", metadata)
    assert len(confirmed["items"]) == 2
    accepted = _accepted_unknowns("video_movie", metadata)
    assert accepted["items"][0]["accepted_unknown_year"] is True
    assert _lookup_later("video_movie", metadata)[0]["scope"] == "movie"
    summary = _summary("video_movie", metadata, {
        "files_moved": [{}, {}],
        "artwork_moved": [{}],
        "subtitles_moved": [{}],
        "sidecars_ignored": [],
        "failed_moves": [],
    })
    assert summary["movie_count"] == 2
    assert summary["year_range"] == "2020"
    assert summary["files_moved_count"] == 4
    check_collection_manifest_location()
    print("v2.066B movie move manifest checks passed")


if __name__ == "__main__":
    main()
