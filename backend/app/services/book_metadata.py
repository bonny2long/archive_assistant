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
BOOK_SERIES_PREFIX_RE = re.compile(
    r"^(?P<series>.+?)\s+(?P<index>\d+(?:\.\d+)?)\s*-\s*(?P<title>.+)$",
    re.I,
)
LEADING_INDEX_RE = re.compile(
    r"^(?P<index>\d+(?:\.\d+)?)\s*-\s*(?P<rest>.+)$",
    re.I,
)
YEAR_RE = re.compile(r"(?:\(|\[|\b)((?:19|20)\d{2})(?:\)|\]|\b)")
AUTHOR_HINT_RE = re.compile(
    r"\b(?:by|author)\s+(?P<author>[A-Z][A-Za-z0-9 .,&'\u2019\-]+)$",
    re.I,
)
KNOWN_AUTHORISH_RE = re.compile(
    r"\b(?:Herbert|Anderson|Allen|Clear|King|Tolkien|Martin|Asimov|Butler|Le Guin)\b",
    re.I,
)


def is_book_file(path: Path) -> bool:
    return path.is_file() and path.suffix.casefold() in BOOK_EXTENSIONS


def is_book_artwork(path: Path) -> bool:
    if path.suffix.casefold() not in BOOK_ARTWORK_EXTENSIONS:
        return False
    if path.stem.casefold() in BOOK_ARTWORK_NAMES:
        return True
    return any(
        part.casefold() in {"cover", "covers", "artwork", "images"}
        for part in path.parts
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
    text = re.sub(r"_+", " ", text)
    return re.sub(r"\s+", " ", text).strip(" -_.")


def _clean_person_name(value: str) -> str:
    text = re.sub(r"\s+", " ", value.strip(" -_."))
    return text or "Unknown Author"


def _clean_book_title(value: str) -> str:
    text = re.sub(r"\s+", " ", value.strip(" -_."))
    return text or "Unknown Title"


def _looks_like_author(value: str) -> bool:
    text = value.strip()
    if not text:
        return False
    if re.search(r"\b[A-Z]\.?\s*[A-Z][a-z]+", text):
        return True
    if (
        re.search(r"\b(?:et al|and|&)\b", text, flags=re.I)
        and len(text.split()) <= 8
    ):
        return True
    if KNOWN_AUTHORISH_RE.search(text):
        return True
    words = re.findall(r"[A-Za-z][A-Za-z.'\u2019\-]*", text)
    capitalized = [word for word in words if word[:1].isupper()]
    return 1 <= len(words) <= 4 and len(capitalized) == len(words)


def _extract_year(text: str) -> tuple[str, str | None]:
    match = YEAR_RE.search(text)
    if not match:
        return text.strip(" -_."), None
    year = match.group(1)
    cleaned = (text[:match.start()] + text[match.end():]).strip(" -_.")
    return re.sub(r"\s+", " ", cleaned), year


def parse_book_name(value: str) -> dict:
    """Parse conservative book metadata from a filename or folder name."""
    candidate = Path(value)
    raw = (
        candidate.stem
        if candidate.suffix.casefold() in BOOK_EXTENSIONS
        else value
    )
    text = _strip_release_noise(raw)
    text, year = _extract_year(text)
    series = None
    series_index = None

    leading = LEADING_INDEX_RE.match(text)
    if leading:
        series_index = leading.group("index")
        rest = leading.group("rest").strip()
        parts = [part.strip() for part in rest.split(" - ") if part.strip()]
        if len(parts) >= 2 and _looks_like_author(parts[-1]):
            return {
                "author": _clean_person_name(parts[-1]),
                "title": _clean_book_title(" - ".join(parts[:-1])),
                "year": year,
                "raw_name": raw,
                "series": series,
                "series_index": series_index,
            }
        return {
            "author": "Unknown Author",
            "title": _clean_book_title(rest),
            "year": year,
            "raw_name": raw,
            "series": series,
            "series_index": series_index,
        }

    series_match = BOOK_SERIES_PREFIX_RE.match(text)
    if series_match:
        return {
            "author": "Unknown Author",
            "title": _clean_book_title(series_match.group("title")),
            "year": year,
            "raw_name": raw,
            "series": _clean_book_title(series_match.group("series")),
            "series_index": series_match.group("index"),
        }

    by_match = AUTHOR_HINT_RE.search(text)
    if by_match:
        return {
            "author": _clean_person_name(by_match.group("author")),
            "title": _clean_book_title(text[:by_match.start()]),
            "year": year,
            "raw_name": raw,
            "series": series,
            "series_index": series_index,
        }

    parts = [part.strip() for part in text.split(" - ") if part.strip()]
    if len(parts) >= 2:
        right = parts[-1]
        left = " - ".join(parts[:-1])
        if _looks_like_author(right):
            author, title = right, left
        elif _looks_like_author(parts[0]) and len(parts) == 2:
            author, title = parts[0], parts[1]
        else:
            author, title = "Unknown Author", text
    else:
        author, title = "Unknown Author", text
    return {
        "author": _clean_person_name(author),
        "title": _clean_book_title(title),
        "year": year,
        "raw_name": raw,
        "series": series,
        "series_index": series_index,
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


def build_book_item_destination(
    *,
    books_root: Path,
    item: dict,
    collection_title: str | None = None,
    keep_collection_together: bool = False,
) -> Path:
    fmt = str(
        item.get("format") or item.get("book_format") or "EPUB"
    ).upper()
    title = safe_book_path_part(str(item.get("title") or "Unknown Title"))
    author = safe_book_path_part(str(item.get("author") or "Unknown Author"))
    year = str(item.get("year") or "").strip()
    year_title = safe_book_path_part(
        f"{year or 'Unknown Year'} - {title}"
    )
    if keep_collection_together:
        collection = safe_book_path_part(
            collection_title or "Unknown Collection"
        )
        return books_root / fmt / "Collections" / collection / year_title
    return books_root / fmt / author / year_title


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
        "artwork_files": [
            str(path.relative_to(source)) if source.is_dir() else path.name
            for path in files["artwork"]
        ],
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
