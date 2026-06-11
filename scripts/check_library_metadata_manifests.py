import json
import os
import sys
import tempfile
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = PROJECT_ROOT / "backend"
os.environ["DEBUG"] = "true"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.services.library_manifest import (  # noqa: E402
    _relative_library_path,
    append_library_index_entry,
    write_library_manifest,
)


CASES = [
    (
        "audiobook",
        Path("Audiobooks/Library/Author/2020 - Title"),
        "audiobook.json",
        Path("Audiobooks/Metadata"),
        "batch-1-audiobook-move-log.json",
    ),
    (
        "book",
        Path("Books/PDF/Author/2020 - Title"),
        "book.json",
        Path("Books/Metadata"),
        "batch-2-book-move-log.json",
    ),
    (
        "movie",
        Path("Movies/Library/2020 - Title"),
        "movie.json",
        Path("Movies/Metadata"),
        "batch-3-movie-move-log.json",
    ),
    (
        "music_discography",
        Path("Music/Discographies/Artist"),
        "discography.json",
        Path("Music/Metadata"),
        "discography-move-log.json",
    ),
    (
        "tv_show",
        Path("TV/Library/Show"),
        "tv-show.json",
        Path("TV/Metadata"),
        "batch-5-tv-move-log.json",
    ),
]


def _assert_mover_integrations() -> None:
    source = (
        PROJECT_ROOT / "backend/app/services/mover.py"
    ).read_text(encoding="utf-8")
    for filename in {
        "movie.json",
        "tv-show.json",
        "music-album.json",
        "discography.json",
        "book.json",
        "audiobook.json",
    }:
        assert f'"{filename}"' in source, f"Missing mover integration for {filename}"


def main() -> None:
    temp_root = Path("C:/tmp")
    temp_root.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(
        prefix="archive-manifest-check-",
        dir=temp_root,
    ) as temp:
        root = Path(temp) / "data"
        for batch_id, case in enumerate(CASES, start=1):
            media_kind, relative_destination, filename, index_relative, log_name = case
            destination = root / relative_destination
            metadata_dir = destination / "metadata"
            metadata_dir.mkdir(parents=True)
            move_log = metadata_dir / log_name
            move_log.write_text('{"status": "completed"}', encoding="utf-8")

            manifest_path = write_library_manifest(
                destination,
                filename,
                {
                    "media_kind": media_kind,
                    "title": "Title",
                    "batch_id": batch_id,
                },
            )
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            assert manifest["library_path"] == relative_destination.as_posix()
            assert not Path(manifest["library_path"]).is_absolute()
            assert ":" not in manifest["library_path"]
            assert move_log.exists(), f"Move log was removed for {media_kind}"

            index_dir = root / index_relative
            entry = {
                "media_kind": media_kind,
                "title": "Title",
                "library_path": _relative_library_path(destination),
                "batch_id": batch_id,
            }
            append_library_index_entry(index_dir, entry)
            append_library_index_entry(index_dir, entry)
            index_path = index_dir / "library-index.json"
            index = json.loads(index_path.read_text(encoding="utf-8"))
            assert len(index) == 1, f"Index entry was not replaced for {media_kind}"
            assert index[0]["library_path"] == relative_destination.as_posix()

        _assert_mover_integrations()

    print("Library metadata manifest checks passed.")


if __name__ == "__main__":
    main()
