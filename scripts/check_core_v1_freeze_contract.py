"""Static checks for v1 manifest/index and TV visual integration."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    mover = (ROOT / "backend/app/services/mover.py").read_text(encoding="utf-8")
    config = (ROOT / "backend/app/core/config.py").read_text(encoding="utf-8")
    manifest = (
        ROOT / "backend/app/services/library_manifest.py"
    ).read_text(encoding="utf-8")
    styles = (ROOT / "frontend/src/style.css").read_text(encoding="utf-8")

    for filename in {
        "movie.json",
        "tv-show.json",
        "music-album.json",
        "discography.json",
        "book.json",
        "audiobook.json",
    }:
        assert f'"{filename}"' in mover, f"Missing manifest integration: {filename}"

    for setting in {
        "music_metadata_dir",
        "movies_metadata_dir",
        "tv_metadata_dir",
        "books_metadata_dir",
        "audiobooks_metadata_dir",
    }:
        assert setting in config, f"Missing metadata index setting: {setting}"
        assert f"settings.{setting}" in mover, f"Missing index use: {setting}"

    assert "def write_library_manifest(" in manifest
    assert "def append_library_index_entry(" in manifest
    assert '"library-index.json"' in manifest
    assert "except Exception as exc:" in mover
    assert "Failed to write library manifest" in mover
    assert "Failed to update library index" in mover

    assert ".tv-repair-card--special .tv-repair-card__header" in styles
    assert "color: var(--accent-blue);" in styles

    print("PASS - Core v1 manifest, index, and TV visual contracts are present")


if __name__ == "__main__":
    main()
