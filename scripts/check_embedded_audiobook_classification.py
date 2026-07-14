"""Regression checks for embedded audiobook evidence at intake."""

from __future__ import annotations

import sys
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import patch

PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = PROJECT_ROOT / "backend"
sys.path.insert(0, str(BACKEND_ROOT))

from app.services import audiobook_metadata, scanner


def _embedded(genre: str) -> SimpleNamespace:
    return SimpleNamespace(read_ok=True, fields={"genre": genre})


def main() -> int:
    with TemporaryDirectory(dir=PROJECT_ROOT) as temp:
        root = Path(temp) / "The Example Series - Example Author"
        genres = {
            "Book One": "Audio Book",
            "Book Two": "Audiobook - Science Fiction",
            "Book Three": "Spoken Word",
        }
        audio_files: list[Path] = []
        for folder_name in genres:
            folder = root / folder_name
            folder.mkdir(parents=True)
            for index in range(1, 4):
                audio_file = folder / f"Chapter {index:02d}.mp3"
                audio_file.write_bytes(b"test audio")
                audio_files.append(audio_file)
        covers = root / "Collected Artwork"
        covers.mkdir()
        cover = covers / "Book One cover.jpg"
        cover.write_bytes(b"test artwork")

        def audiobook_reader(path: Path, media_type: str | None = None) -> SimpleNamespace:
            book_folder = Path(path).parent.name
            return _embedded(genres[book_folder])

        with patch.object(
            audiobook_metadata,
            "read_embedded_metadata",
            side_effect=audiobook_reader,
        ):
            assert audiobook_metadata.has_embedded_audiobook_signal(
                root,
                audio_files,
            )

        with patch.object(
            audiobook_metadata,
            "read_embedded_metadata",
            return_value=_embedded("Rock"),
        ):
            assert not audiobook_metadata.has_embedded_audiobook_signal(
                root,
                audio_files,
            )

        with patch.object(
            audiobook_metadata,
            "read_embedded_metadata",
            side_effect=audiobook_reader,
        ):
            assert scanner.classify_ingest_item(root) == "audiobook"

        music_root = Path(temp) / "Example Artist - Discography"
        for year, album in ((2000, "Album One"), (2002, "Album Two")):
            album_folder = music_root / f"{year} - {album}"
            album_folder.mkdir(parents=True)
            for index in range(1, 4):
                (album_folder / f"{index:02d} - Song {index}.mp3").write_bytes(
                    b"test music"
                )
        with patch.object(
            audiobook_metadata,
            "read_embedded_metadata",
            return_value=_embedded("Rock"),
        ):
            assert scanner.classify_ingest_item(music_root) == "music_discography"

        collected = audiobook_metadata.collect_audiobook_files(root)
        assert len(collected["audio"]) == 9
        assert collected["artwork"] == [cover]

    print(
        "PASS: embedded audiobook genres outrank discography routing "
        "and artwork remains support evidence"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
