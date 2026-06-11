from pathlib import Path
import sys
from tempfile import TemporaryDirectory

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "backend"))

from app.services.audiobook_metadata import (
    audiobook_destination,
    build_audiobook_metadata,
    looks_like_audiobook_source,
    parse_audiobook_name,
)


def main() -> None:
    parsed = parse_audiobook_name(
        "Dune - Frank Herbert (1965) Audiobook"
    )
    assert parsed["author"] == "Frank Herbert", parsed
    assert parsed["title"] == "Dune", parsed
    assert parsed["year"] == "1965", parsed

    loose = parse_audiobook_name("Dune by Frank Herbert (1965).m4b")
    assert loose["author"] == "Frank Herbert", loose
    assert loose["title"] == "Dune", loose
    assert loose["year"] == "1965", loose

    with TemporaryDirectory(dir=r"C:\tmp") as temp:
        root = Path(temp) / "Dune - Frank Herbert (1965) Audiobook"
        root.mkdir()
        (root / "01 - Chapter 1.mp3").write_bytes(b"chapter-one")
        (root / "02 - Chapter 2.mp3").write_bytes(b"chapter-two")
        (root / "cover.jpg").write_bytes(b"cover")
        assert looks_like_audiobook_source(root)
        metadata = build_audiobook_metadata(
            root,
            Path(temp) / "Audiobooks" / "Library",
        )
        assert metadata["author"] == "Frank Herbert", metadata
        assert metadata["title"] == "Dune", metadata
        assert metadata["year"] == "1965", metadata
        assert metadata["audiobook_file_count"] == 2, metadata
        assert metadata["artwork_count"] == 1, metadata

    expected = Path(
        "Audiobooks/Library/Frank Herbert/1965 - Dune"
    )
    assert audiobook_destination(
        audiobooks_root=Path("Audiobooks/Library"),
        author="Frank Herbert",
        title="Dune",
        year="1965",
    ) == expected
    print("audiobooks foundation checks passed")


if __name__ == "__main__":
    main()
