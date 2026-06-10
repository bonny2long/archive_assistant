"""Movie final polish regression check.

Tests all movie parsing, metadata, and review state rules
from ARCHIVE_ASSISTANT_UPDATE_040_MOVIES_FINAL_POLISH.md.
Does not require database or test files.
"""
import re
import sys
from pathlib import Path

# Add backend to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

from app.services.video_metadata import (
    parse_movie_name,
    safe_movie_path_part,
    is_movie_artwork,
    is_subtitle_file,
    is_ignored_video_sidecar,
    useful_movie_name,
)
from app.services.review_state import build_review_state

PASS = "PASS"
FAIL = "FAIL"

failures = 0


def check(description: str, condition: bool) -> None:
    global failures
    status = PASS if condition else FAIL
    if not condition:
        failures += 1
    print(f"  [{status}] {description}")


def main() -> int:
    print("\n=== Section 5.1: parse_movie_name test cases ===\n")

    # Test case: Black Panther folder
    parsed = parse_movie_name("Black Panther (2018) [BluRay] [1080p] [YTS.AM]")
    check("Black Panther folder: title", parsed["title"] == "Black Panther")
    check("Black Panther folder: year", parsed["year"] == "2018")
    check("Black Panther folder: no edition", parsed["edition"] is None)

    # Test case: Black Panther file
    parsed = parse_movie_name("Black.Panther.2018.1080p.BluRay.x264-[YTS.AM].mp4")
    check("Black Panther file: title", parsed["title"] == "Black Panther")
    check("Black Panther file: year", parsed["year"] == "2018")
    check("Black Panther file: no edition", parsed["edition"] is None)
    check(
        "Black Panther file: release tags",
        set(parsed["release_tags_removed"]) == {"1080p", "BluRay", "x264", "YTS.AM"},
    )

    # Test case: Mortal Kombat II file
    parsed = parse_movie_name(
        "Mortal.Kombat.II.2026.1080p.WEBRip.AAC5.1.10bits.x265-Rapta.mkv"
    )
    check("Mortal Kombat II: title", parsed["title"] == "Mortal Kombat II")
    check("Mortal Kombat II: year", parsed["year"] == "2026")
    check(
        "Mortal Kombat II: release tags",
        set(parsed["release_tags_removed"]) == {"1080p", "WEBRip", "x265"},
    )
    # Edition contains tech noise (AAC5.1.10bits-Rapta); scanner filters it via digit check
    check(
        "Mortal Kombat II: edition has tech noise (filtered by scanner)",
        parsed["edition"] is not None
        and bool(re.search(r"\d", parsed["edition"])),
    )

    # Test case: Blade Runner (1982) Final Cut folder
    parsed = parse_movie_name("Blade Runner (1982) Final Cut")
    check("Blade Runner Final Cut folder: title", parsed["title"] == "Blade Runner")
    check("Blade Runner Final Cut folder: year", parsed["year"] == "1982")
    check(
        "Blade Runner Final Cut folder: edition",
        parsed["edition"] is not None,
    )

    # Test case: Blade Runner Final Cut file
    parsed = parse_movie_name("Blade.Runner.1982.Final.Cut.1080p.mkv")
    check("Blade Runner Final Cut file: title", parsed["title"] == "Blade Runner")
    check("Blade Runner Final Cut file: year", parsed["year"] == "1982")
    check(
        "Blade Runner Final Cut file: edition",
        parsed["edition"] is not None,
    )

    # Test case: Blade Runner Theatrical Cut file
    parsed = parse_movie_name("Blade.Runner.1982.Theatrical.Cut.1080p.mkv")
    check(
        "Blade Runner Theatrical Cut file: title",
        parsed["title"] == "Blade Runner",
    )
    check(
        "Blade Runner Theatrical Cut file: edition",
        parsed["edition"] is not None,
    )

    # Test case: Unknown movie (no year)
    parsed = parse_movie_name("Unknown.Good.Movie.1080p.mkv")
    check("Unknown movie: title", parsed["title"] == "Unknown Good Movie")
    check("Unknown movie: no year", parsed["year"] is None)
    check("Unknown movie: no edition (no year match)", parsed["edition"] is None)
    check(
        "Unknown movie: useful_movie_name",
        useful_movie_name(parsed),
    )

    # Test case: Movie with artwork and subtitle folder
    parsed = parse_movie_name("Example Movie (2020)")
    check("Example Movie folder: title", parsed["title"] == "Example Movie")
    check("Example Movie folder: year", parsed["year"] == "2020")
    check("Example Movie folder: no edition", parsed["edition"] is None)

    print("\n=== Section 5.1: utility functions ===\n")

    check(
        "is_movie_artwork: poster.jpg",
        is_movie_artwork(Path("poster.jpg")),
    )
    check(
        "is_movie_artwork: folder.jpg",
        is_movie_artwork(Path("folder.jpg")),
    )
    check(
        "is_movie_artwork: cover.png",
        is_movie_artwork(Path("cover.png")),
    )
    check(
        "is_movie_artwork: fanart.jpg",
        is_movie_artwork(Path("fanart.jpg")),
    )
    check(
        "is_movie_artwork: not artwork (.mkv)",
        not is_movie_artwork(Path("movie.mkv")),
    )
    check("is_subtitle_file: .srt", is_subtitle_file(Path("movie.en.srt")))
    check("is_subtitle_file: .ass", is_subtitle_file(Path("movie.ass")))
    check("is_subtitle_file: .vtt", is_subtitle_file(Path("movie.vtt")))
    check("is_subtitle_file: .sub", is_subtitle_file(Path("movie.sub")))
    check(
        "is_ignored_video_sidecar: .nfo",
        is_ignored_video_sidecar(Path("movie.nfo")),
    )
    check(
        "is_ignored_video_sidecar: .txt",
        is_ignored_video_sidecar(Path("somefile.txt")),
    )
    check(
        "is_ignored_video_sidecar: .log",
        is_ignored_video_sidecar(Path("extract.log")),
    )
    check(
        "is_ignored_video_sidecar: .sfv",
        is_ignored_video_sidecar(Path("checksums.sfv")),
    )
    check(
        "safe_movie_path_part: normal name",
        safe_movie_path_part("2018 - Black Panther"),
    )
    check(
        "safe_movie_path_part: strips illegal chars",
        safe_movie_path_part("Movie: Title") == "Movie_ Title",
    )
    check(
        "safe_movie_path_part: with edition brackets",
        safe_movie_path_part("1982 - Blade Runner [Final Cut]"),
    )

    print("\n=== Section 5.3: Review state tests ===\n")

    # Missing title -> blocking
    meta = build_review_state("video_movie", {
        "title": "",
        "year": "2020",
        "video_file_count": 1,
        "video_files": ["test.mkv"],
        "metadata_warnings": [],
    })
    check(
        "Missing title -> blocking",
        any(item["type"] == "movie_title_missing" for item in meta["blocking_review_items"]),
    )

    # Missing year -> blocking
    meta = build_review_state("video_movie", {
        "title": "Test Movie",
        "year": "",
        "video_file_count": 1,
        "video_files": ["test.mkv"],
        "metadata_warnings": ["movie_year_missing"],
    })
    check(
        "Missing year -> blocking",
        any(item["type"] == "movie_year_missing" for item in meta["blocking_review_items"]),
    )

    # Multiple clear editions -> non-blocking warning
    meta = build_review_state("video_movie", {
        "title": "Blade Runner",
        "year": "1982",
        "video_file_count": 2,
        "video_files": [
            "Blade.Runner.1982.Final.Cut.1080p.mkv",
            "Blade.Runner.1982.Theatrical.Cut.1080p.mkv",
        ],
        "metadata_warnings": [],
    })
    check(
        "Multiple editions -> non-blocking warning",
        any(
            item["type"] == "multiple_movie_editions"
            for item in meta["non_blocking_review_items"]
        ),
    )
    check(
        "Multiple editions -> NOT blocking",
        not any(
            item["type"] == "multiple_movie_candidates"
            for item in meta["blocking_review_items"]
        ),
    )

    # Multiple ambiguous videos -> blocking
    meta = build_review_state("video_movie", {
        "title": "Mixed",
        "year": "2020",
        "video_file_count": 2,
        "video_files": ["MovieA.mkv", "MovieB.mkv"],
        "metadata_warnings": [],
    })
    check(
        "Multiple ambiguous -> blocking",
        any(
            item["type"] == "multiple_movie_candidates"
            for item in meta["blocking_review_items"]
        ),
    )

    # Missing artwork -> not blocking (no check exists, which is correct)
    meta = build_review_state("video_movie", {
        "title": "Test",
        "year": "2020",
        "video_file_count": 1,
        "video_files": ["test.mkv"],
        "artwork_count": 0,
        "metadata_warnings": [],
    })
    check(
        "No artwork -> not blocking",
        not meta["blocking_review_items"],
    )

    # Destination exists -> blocking (via warning in BLOCKING_WARNING_TYPES)
    meta = build_review_state("video_movie", {
        "title": "Black Panther",
        "year": "2018",
        "video_file_count": 1,
        "video_files": ["Black.Panther.2018.1080p.BluRay.x264-[YTS.AM].mp4"],
        "metadata_warnings": ["movie_destination_exists"],
    })
    check(
        "Destination exists -> blocking",
        any(
            item["type"] == "movie_destination_exists"
            for item in meta["blocking_review_items"]
        ),
    )

    print(f"\n{'=' * 40}")
    print(f"Total failures: {failures}")
    print(f"{'=' * 40}\n")

    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
