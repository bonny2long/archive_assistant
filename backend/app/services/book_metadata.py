from __future__ import annotations

from pathlib import Path
import re
import zipfile
from xml.etree import ElementTree

from app.services.metadata_candidates import (
    METADATA_ASSIST_VERSION,
    add_candidate,
    make_candidate,
    preferred_candidate_value,
)

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
SOURCE_PREFIX_RE = re.compile(
    r"^(?:"
    r"@[A-Za-z0-9_.-]+|"
    r"(?:https?://)?(?:www\.)?[A-Za-z0-9.-]+\.(?:com|org|net|io)|"
    r"ebook(?:s)?(?:[-_ ]?(?:source|scan|share))?|"
    r"pdfdrive|z[-_. ]?lib|libgen|scanner|scan(?:ned)?"
    r")\s*[-_:]\s*",
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
    text = SOURCE_PREFIX_RE.sub("", text)
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
    if re.search(r"\d", text):
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
    title_words = {
        "a", "against", "assertiveness", "conversations", "couples",
        "discipline", "effective", "empathy", "for", "guide", "happy",
        "help", "live", "parenting", "questions", "relationship", "step",
    }
    if any(word.casefold() in title_words for word in words):
        return False
    capitalized = [word for word in words if word[:1].isupper()]
    return 2 <= len(words) <= 4 and len(capitalized) == len(words)


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
        elif (
            _looks_like_author(parts[0])
            and len(parts) == 2
            and not parts[0].startswith("@")
        ):
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


def _xml_text(element: ElementTree.Element | None) -> str | None:
    if element is None or element.text is None:
        return None
    value = element.text.strip()
    return value or None


def extract_epub_metadata(path: Path) -> dict:
    if path.suffix.casefold() != ".epub":
        return {}
    try:
        with zipfile.ZipFile(path) as archive:
            container = ElementTree.fromstring(
                archive.read("META-INF/container.xml")
            )
            rootfile = container.find(
                ".//{urn:oasis:names:tc:opendocument:xmlns:container}rootfile"
            )
            if rootfile is None:
                return {}
            opf_path = rootfile.attrib.get("full-path")
            if not opf_path:
                return {}
            package = ElementTree.fromstring(archive.read(opf_path))
            metadata = package.find(
                ".//{http://www.idpf.org/2007/opf}metadata"
            )
            if metadata is None:
                return {}
            values = {
                "title": _xml_text(metadata.find(
                    "{http://purl.org/dc/elements/1.1/}title"
                )),
                "author": _xml_text(metadata.find(
                    "{http://purl.org/dc/elements/1.1/}creator"
                )),
                "date": _xml_text(metadata.find(
                    "{http://purl.org/dc/elements/1.1/}date"
                )),
                "language": _xml_text(metadata.find(
                    "{http://purl.org/dc/elements/1.1/}language"
                )),
            }
            for meta in metadata.findall(
                "{http://www.idpf.org/2007/opf}meta"
            ):
                name = str(meta.attrib.get("name") or "").casefold()
                content = str(meta.attrib.get("content") or "").strip()
                if name == "calibre:series" and content:
                    values["series"] = content
                elif name == "calibre:series_index" and content:
                    values["series_index"] = content
            return {key: value for key, value in values.items() if value}
    except (OSError, KeyError, zipfile.BadZipFile, ElementTree.ParseError):
        return {}


def extract_pdf_metadata(path: Path) -> dict:
    if path.suffix.casefold() != ".pdf":
        return {}
    try:
        from pypdf import PdfReader
    except ImportError:
        return {}
    try:
        metadata = PdfReader(str(path)).metadata
    except Exception:
        return {}
    if not metadata:
        return {}
    date_value = str(
        getattr(metadata, "creation_date", None)
        or metadata.get("/CreationDate")
        or ""
    )
    year_match = YEAR_RE.search(date_value)
    values = {
        "title": getattr(metadata, "title", None) or metadata.get("/Title"),
        "author": getattr(metadata, "author", None) or metadata.get("/Author"),
        "year": year_match.group(1) if year_match else None,
    }
    return {
        key: str(value).strip()
        for key, value in values.items()
        if value and str(value).strip()
    }


def build_book_metadata_candidates(
    source: Path,
    primary: Path,
    artwork: list[Path],
) -> tuple[dict[str, list[dict]], list[dict]]:
    candidates: dict[str, list[dict]] = {}
    source_guess = parse_book_name(
        source.name if source.is_dir() else primary.name
    )
    file_guess = parse_book_name(primary.name)
    fields = ("title", "author", "year", "series", "series_index")
    if source.is_dir():
        for field in fields:
            source_value = source_guess.get(field)
            if str(source_value or "").casefold() not in UNKNOWN_BOOK_VALUES:
                add_candidate(candidates, make_candidate(
                    field,
                    source_value,
                    "folder_name",
                    "Folder name",
                    0.72,
                ))

    for field in fields:
        file_value = file_guess.get(field)
        if str(file_value or "").casefold() not in UNKNOWN_BOOK_VALUES:
            add_candidate(candidates, make_candidate(
                field,
                file_value,
                "filename",
                "Filename",
                0.68,
            ))

    embedded = (
        extract_epub_metadata(primary)
        if primary.suffix.casefold() == ".epub"
        else extract_pdf_metadata(primary)
    )
    source_key = (
        "epub_opf"
        if primary.suffix.casefold() == ".epub"
        else "pdf_document_info"
    )
    source_label = (
        "EPUB package metadata"
        if primary.suffix.casefold() == ".epub"
        else "PDF document metadata"
    )
    for field in ("title", "author", "year", "series", "series_index"):
        value = embedded.get(field)
        if field == "year" and not value:
            raw_date = str(embedded.get("date") or "")
            match = YEAR_RE.search(raw_date)
            value = match.group(1) if match else None
        add_candidate(candidates, make_candidate(
            field,
            value,
            f"{source_key}_{field}",
            source_label,
            0.92 if field in {"title", "author"} else 0.84,
        ))

    artwork_candidates = [
        candidate
        for path in artwork
        if (
            candidate := make_candidate(
                "artwork",
                str(path.relative_to(source)) if source.is_dir() else path.name,
                "book_sidecar_artwork",
                "Book artwork file",
                0.9,
            )
        )
    ]
    return candidates, artwork_candidates


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
    metadata_candidates, artwork_candidates = build_book_metadata_candidates(
        source,
        primary,
        files["artwork"],
    )
    author = preferred_candidate_value(
        metadata_candidates,
        "author",
        author if author.casefold() not in UNKNOWN_BOOK_VALUES else "Unknown Author",
    )
    title = preferred_candidate_value(
        metadata_candidates,
        "title",
        title if title.casefold() not in UNKNOWN_BOOK_VALUES else "Unknown Title",
    )
    year = preferred_candidate_value(metadata_candidates, "year", year)
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
        "metadata_assist_version": METADATA_ASSIST_VERSION,
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
        "metadata_candidates": metadata_candidates,
        "artwork_candidates": artwork_candidates,
    }
