from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "backend"))

from app.services.book_metadata import (
    build_book_item_destination,
    is_book_artwork,
    parse_book_name,
)


def assert_subset(actual: dict, expected: dict, source: str) -> None:
    for key, value in expected.items():
        if actual.get(key) != value:
            raise AssertionError(
                f"{source}: expected {key}={value!r}, "
                f"got {actual.get(key)!r}. Full: {actual!r}"
            )


def main() -> None:
    cases = [
        (
            "1 - Dune - Frank Herbert (1965).epub",
            {
                "author": "Frank Herbert",
                "title": "Dune",
                "year": "1965",
                "series_index": "1",
            },
        ),
        (
            "2 - Dune Messiah - Frank Herbert (1969).epub",
            {
                "author": "Frank Herbert",
                "title": "Dune Messiah",
                "year": "1969",
                "series_index": "2",
            },
        ),
        (
            "Tales of Dune (Short stories) - Brian Herbert and Kevin J. Anderson.epub",
            {
                "author": "Brian Herbert and Kevin J. Anderson",
                "title": "Tales of Dune (Short stories)",
            },
        ),
        (
            "The Road to Dune (Companion book) - Frank Herbert et al.epub",
            {
                "author": "Frank Herbert et al",
                "title": "The Road to Dune (Companion book)",
            },
        ),
        (
            "Dreamer of Dune- The Biography of Frank Herbert by Brian Herbert.epub",
            {
                "author": "Brian Herbert",
                "title": "Dreamer of Dune- The Biography of Frank Herbert",
            },
        ),
        (
            "Prelude to Dune 1 - House Atreides.epub",
            {
                "author": "Unknown Author",
                "title": "House Atreides",
                "series": "Prelude to Dune",
                "series_index": "1",
            },
        ),
        (
            "Octavia Butler - Parable of the Sower (1993).epub",
            {
                "author": "Octavia Butler",
                "title": "Parable of the Sower",
                "year": "1993",
            },
        ),
    ]
    for source, expected in cases:
        assert_subset(parse_book_name(source), expected, source)

    assert is_book_artwork(Path("Covers/Dune.jpg"))
    assert is_book_artwork(Path("cover.jpg"))
    assert not is_book_artwork(Path("notes.txt"))

    item = {
        "format": "EPUB",
        "author": "Frank Herbert",
        "title": "Dune",
        "year": "1965",
    }
    assert build_book_item_destination(
        books_root=Path("Books"),
        item=item,
    ) == Path("Books/EPUB/Frank Herbert/1965 - Dune")
    assert build_book_item_destination(
        books_root=Path("Books"),
        item=item,
        collection_title="Dune Series",
        keep_collection_together=True,
    ) == Path("Books/EPUB/Collections/Dune Series/1965 - Dune")
    print("books parse and collection review checks passed")


if __name__ == "__main__":
    main()
