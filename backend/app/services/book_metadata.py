from __future__ import annotations

from pathlib import Path
import re

BOOK_EXTENSIONS = {".epub", ".pdf"}
BOOK_SIDECAR_EXTENSIONS = {".opf", ".nfo", ".json", ".xml", ".txt"}
BOOK_ARTWORK_NAMES = {
    "cover", "folder", "front", "book-cover", "book_cover", "thumbnail",
}
BOOK_ARTWORK_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}
UNKNOWN_BOOK_VALUES = {"", "unknown", "unknown author", "unknown title", "unkn"}


def is_book_file(path: Path) -> bool:
    return path.is_file() and path.suffix.casefold() in BOOK_EXTENSIONS


def is_book_artwork(path: Path) -> bool:
    return (
        path.is_file()
        and path.suffix.casefold() in BOOK_ARTWORK_EXTENSIONS
        and path.stem.casefold() in BOOK_ARTWORK_NAMES
    )


def is_book_sidecar(path: Path) -> bool:
    return path.is_file() and path.suffix.casefold() in BOOK_SIDECAR_EXTENSIONS


def book_format_for(path: Path) -> str:
    return {".epub": "EPUB", ".pdf": "PDF"}.get(
        path.suffix.casefold(),
        path.suffix.lstrip(".").upper() or "BOOK",
    )


def safe_book_path_part(value: str) -> str:
    cleaned = "".join(c if c not in '<>:"/\\|?*' else "_" for c in value)
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" .")
    return cleaned or "Unknown"


def _strip_release_noise(value: str) -> str:
    text = re.sub(
        r"\[(?:epub|pdf|ebook|retail|scan|ocr|azw3|mobi)\]",
        " ",
        value,
        flags=re.I,
    )
    text = re.sub(r"\b(?:epub|pdf|ebook|retail|scan|ocr)\b", " ", text, flags=re.I)
    text = re.sub(r"[_\.]+", " ", text)
    return re.sub(r"\s+", " ", text).strip(" -_.")


def parse_book_name(value: str) -> dict:
    raw = Path(value).stem if Path(value).suffix else value
    text = _strip_release_noise(raw)
    year = None
    match = re.search(r"(?:\(|\[|\b)((?:19|20)\d{2})(?:\)|\]|\b)", text)
    if match:
        year = match.group(1)
        text = (text[:match.start()] + text[match.end():]).strip(" -_.")
    author = None
    title = text.strip()
    if " - " in text:
        left, right = [part.strip() for part in text.split(" - ", 1)]
        if left and right:
            author, title = left, right
    return {
        "author": author or "Unknown Author",
        "title": title or "Unknown Title",
        "year": year,
        "raw_name": raw,
    }


def choose_primary_book_file(book_files: list[Path]) -> Path:
    epubs = [path for path in book_files if path.suffix.casefold() == ".epub"]
    return sorted(epubs or book_files, key=lambda path: path.name.casefold())[0]


def collect_book_files(root: Path) -> dict[str, list[Path]]:
    candidates = [root] if root.is_file() else [
        path for path in root.rglob("*") if path.is_file()
    ]
    books = sorted(path for path in candidates if is_book_file(path))
    artwork = sorted(path for path in candidates if is_book_artwork(path))
    sidecars = sorted(path for path in candidates if is_book_sidecar(path))
    recognized = {path.resolve() for path in [*books, *artwork, *sidecars]}
    other = sorted(path for path in candidates if path.resolve() not in recognized)
    return {"books": books, "artwork": artwork, "sidecars": sidecars, "other": other}


def book_destination(
    format_name: str,
    author: str,
    title: str,
    year: str | None,
    books_dir: Path,
) -> Path:
    return (
        books_dir
        / safe_book_path_part(format_name.upper())
        / safe_book_path_part(author)
        / safe_book_path_part(f"{year or 'Unknown Year'} - {title}")
    )


def build_single_book_metadata(source: Path, books_dir: Path) -> dict:
    files = collect_book_files(source)
    primary = choose_primary_book_file(files["books"])
    source_parsed = parse_book_name(source.name if source.is_dir() else primary.name)
    file_parsed = parse_book_name(primary.name)
    author = source_parsed["author"]
    title = source_parsed["title"]
    if author == "Unknown Author":
        author = file_parsed["author"]
    if title == "Unknown Title":
        title = file_parsed["title"]
    year = source_parsed.get("year") or file_parsed.get("year")
    fmt = book_format_for(primary)
    destination = book_destination(fmt, author, title, year, books_dir)
    warnings = []
    if author.casefold() in UNKNOWN_BOOK_VALUES:
        warnings.append("book_author_missing")
    if title.casefold() in UNKNOWN_BOOK_VALUES:
        warnings.append("book_title_missing")
    if not year:
        warnings.append("book_year_missing")
    if files["other"]:
        warnings.append("book_ignored_sidecars_present")
    return {
        "media_kind": "book",
        "review_type": "book",
        "review_mode": "single_item",
        "author": author,
        "title": title,
        "year": year,
        "format": fmt,
        "book_format": fmt,
        "book_file_count": len(files["books"]),
        "book_files": [path.name for path in files["books"]],
        "primary_book_file": primary.name,
        "artwork_count": len(files["artwork"]),
        "artwork_files": [path.name for path in files["artwork"]],
        "ignored_sidecar_count": len(files["sidecars"]) + len(files["other"]),
        "ignored_sidecar_files": [
            str(path.relative_to(source)) if source.is_dir() else path.name
            for path in [*files["sidecars"], *files["other"]]
        ],
        "original_release_name": source.name,
        "suggested_destination_preview": str(destination),
        "metadata_quality": (
            "good"
            if author != "Unknown Author" and title != "Unknown Title"
            else "weak"
        ),
        "metadata_warnings": warnings,
        "confidence": (
            0.85
            if author != "Unknown Author" and title != "Unknown Title"
            else 0.65
        ),
    }
