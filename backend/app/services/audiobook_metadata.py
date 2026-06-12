from __future__ import annotations

from pathlib import Path
import re

from app.services.metadata_candidates import (
    METADATA_ASSIST_VERSION,
    add_candidate,
    is_generic_track_value,
    make_candidate,
    preferred_candidate_value,
)

AUDIOBOOK_EXTENSIONS = {
    ".mp3", ".m4b", ".m4a", ".aac", ".flac", ".wav", ".ogg", ".opus",
}
AUDIOBOOK_SIDECAR_EXTENSIONS = {
    ".cue", ".m3u", ".m3u8", ".nfo", ".json", ".xml", ".txt", ".log",
}
AUDIOBOOK_ARTWORK_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}
AUDIOBOOK_HINT_RE = re.compile(
    r"\b(audio\s*book|audiobook|unabridged|abridged|audible|"
    r"narrated|narrator|read\s+by)\b",
    re.I,
)
CHAPTER_HINT_RE = re.compile(
    r"\b(chapter|chap|ch\.?|part|pt\.?|disc|disk|cd)\s*0*\d+\b",
    re.I,
)
YEAR_RE = re.compile(r"(?:\(|\[|\b)((?:19|20)\d{2})(?:\)|\]|\b)")
BY_AUTHOR_RE = re.compile(
    r"\bby\s+(?P<author>[A-Z][A-Za-z0-9 .,&'\u2019\-]+)$",
    re.I,
)
READ_BY_RE = re.compile(
    r"\b(?:read|narrated)\s+by\s+"
    r"(?P<narrator>[A-Z][A-Za-z0-9 .,&'\u2019\-]+)$",
    re.I,
)
UNKNOWN_AUDIOBOOK_VALUES = {
    "", "unknown", "unknown author", "unknown title", "unkn",
}


def is_audiobook_audio_file(path: Path) -> bool:
    return path.is_file() and path.suffix.casefold() in AUDIOBOOK_EXTENSIONS


def is_audiobook_artwork(path: Path) -> bool:
    return path.suffix.casefold() in AUDIOBOOK_ARTWORK_EXTENSIONS


def is_audiobook_sidecar(path: Path) -> bool:
    return path.is_file() and path.suffix.casefold() in AUDIOBOOK_SIDECAR_EXTENSIONS


def audiobook_format_for(paths: list[Path]) -> str:
    extensions = {path.suffix.casefold() for path in paths}
    if ".m4b" in extensions:
        return "M4B"
    if len(extensions) == 1:
        return next(iter(extensions)).lstrip(".").upper()
    return "Mixed"


def safe_audiobook_path_part(value: str) -> str:
    cleaned = "".join(c if c not in '<>:"/\\|?*' else "_" for c in value)
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" .")
    return cleaned or "Unknown"


def _strip_audio_noise(value: str) -> str:
    text = re.sub(
        r"\[(?:audiobook|audio\s*book|unabridged|abridged|audible|"
        r"mp3|m4b|m4a|flac)\]",
        " ",
        value,
        flags=re.I,
    )
    text = re.sub(
        r"\b(?:audiobook|audio\s*book|unabridged|abridged|audible|"
        r"mp3|m4b|m4a|flac)\b",
        " ",
        text,
        flags=re.I,
    )
    return re.sub(r"\s+", " ", text).strip(" -_.")


def _extract_year(text: str) -> tuple[str, str | None]:
    match = YEAR_RE.search(text)
    if not match:
        return text.strip(" -_."), None
    year = match.group(1)
    cleaned = (text[:match.start()] + text[match.end():]).strip(" -_.")
    return re.sub(r"\s+", " ", cleaned), year


def parse_audiobook_name(value: str) -> dict:
    candidate = Path(value)
    raw = (
        candidate.stem
        if candidate.suffix.casefold() in AUDIOBOOK_EXTENSIONS
        else value
    )
    text = _strip_audio_noise(raw)
    narrator = None
    read_by = READ_BY_RE.search(text)
    if read_by:
        narrator = read_by.group("narrator").strip()
        text = text[:read_by.start()].strip(" -_.")
    text, year = _extract_year(text)

    by_match = BY_AUTHOR_RE.search(text)
    if by_match:
        author = by_match.group("author").strip()
        title = text[:by_match.start()].strip(" -_.") or "Unknown Title"
    else:
        parts = [part.strip() for part in text.split(" - ") if part.strip()]
        if len(parts) >= 2:
            author = parts[-1]
            title = " - ".join(parts[:-1])
        else:
            author = "Unknown Author"
            title = text or "Unknown Title"
    return {
        "author": author or "Unknown Author",
        "title": title or "Unknown Title",
        "year": year,
        "narrator": narrator,
        "series": None,
        "series_index": None,
        "raw_name": raw,
    }


def _is_generic_track_name(path: Path) -> bool:
    stem = path.stem.strip().casefold()
    return bool(re.match(
        r"^(?:\d{1,3}\s*[-_. ]*)?(?:track|audio|chapter)?\s*\d{1,3}$",
        stem,
    )) or bool(re.match(r"^\d{1,3}\s+track\s+\d{1,3}$", stem))


def _disc_like_folder_count(root: Path) -> int:
    if root.is_file():
        return 0
    return sum(
        1
        for child in root.iterdir()
        if child.is_dir()
        and re.search(
            r"\b(?:disc|disk|cd)\s*0*\d+\b",
            child.name.casefold().strip(),
        )
    )


def has_explicit_audiobook_signal(path: Path) -> bool:
    candidates = [path] if path.is_file() else [
        candidate for candidate in path.rglob("*") if candidate.is_file()
    ]
    audio_files = [
        candidate for candidate in candidates
        if is_audiobook_audio_file(candidate)
    ]
    return bool(
        audio_files
        and (
            any(
                candidate.suffix.casefold() == ".m4b"
                for candidate in audio_files
            )
            or AUDIOBOOK_HINT_RE.search(path.name)
        )
    )


def looks_like_generic_multidisc_audiobook_source(path: Path) -> bool:
    candidates = [path] if path.is_file() else [
        candidate for candidate in path.rglob("*") if candidate.is_file()
    ]
    audio_files = [
        candidate for candidate in candidates
        if is_audiobook_audio_file(candidate)
    ]
    disc_count = _disc_like_folder_count(path)
    if len(audio_files) < 60 and disc_count < 4:
        return False
    generic_count = sum(
        1 for candidate in audio_files if _is_generic_track_name(candidate)
    )
    generic_ratio = generic_count / max(1, len(audio_files))
    if generic_ratio < 0.60:
        return False
    if disc_count >= 4:
        return True
    return len(audio_files) >= 80 and generic_ratio >= 0.75


def looks_like_audiobook_source(path: Path) -> bool:
    candidates = [path] if path.is_file() else [
        candidate for candidate in path.rglob("*") if candidate.is_file()
    ]
    audio_files = [
        candidate for candidate in candidates
        if is_audiobook_audio_file(candidate)
    ]
    if not audio_files:
        return False
    if has_explicit_audiobook_signal(path):
        return True
    chapterish = [
        candidate
        for candidate in audio_files
        if CHAPTER_HINT_RE.search(candidate.stem)
    ]
    explicit_chapters = [
        candidate
        for candidate in chapterish
        if re.search(r"\b(chapter|chap|ch\.?|part|pt\.?)\s*0*\d+\b",
                     candidate.stem, flags=re.I)
    ]
    if len(audio_files) >= 2 and len(explicit_chapters) >= max(
        2, len(audio_files) // 2
    ):
        return True
    if looks_like_generic_multidisc_audiobook_source(path):
        return True
    parsed = parse_audiobook_name(path.name)
    return (
        len(audio_files) >= 3
        and len(chapterish) >= max(2, len(audio_files) // 2)
        and parsed["author"] != "Unknown Author"
    )


def collect_audiobook_files(root: Path) -> dict[str, list[Path]]:
    candidates = [root] if root.is_file() else [
        path for path in root.rglob("*") if path.is_file()
    ]
    audio = sorted(path for path in candidates if is_audiobook_audio_file(path))
    artwork = sorted(path for path in candidates if is_audiobook_artwork(path))
    sidecars = sorted(path for path in candidates if is_audiobook_sidecar(path))
    recognized = {path.resolve() for path in [*audio, *artwork, *sidecars]}
    other = sorted(path for path in candidates if path.resolve() not in recognized)
    return {
        "audio": audio,
        "artwork": artwork,
        "sidecars": sidecars,
        "other": other,
    }


MULTI_BOOK_INDEX_RE = re.compile(
    r"^(?P<title>.+?)\s*\(Book\s+(?P<index>\d+(?:\.\d+)?)\)",
    re.I,
)


def detect_audiobook_collection(source: Path, audio: list[Path]) -> dict:
    parsed: list[tuple[str, str]] = []
    for path in audio:
        cleaned = _strip_audio_noise(path.stem)
        match = MULTI_BOOK_INDEX_RE.match(cleaned)
        if match:
            parsed.append((match.group("index"), match.group("title").strip()))
    if len(parsed) < 2:
        return {
            "audiobook_collection_type": None,
            "contained_books": [],
        }

    tokenized = [title.split() for _, title in parsed]
    common_length = 0
    for tokens in zip(*tokenized):
        if len({token.casefold() for token in tokens}) != 1:
            break
        common_length += 1
    source_tokens = re.sub(
        r"\b(?:trilogy|collection|series|set)\b",
        "",
        source.stem,
        flags=re.I,
    ).split()
    if source_tokens:
        common_length = min(common_length, len(source_tokens))

    contained = []
    for index, title in parsed:
        title_tokens = title.split()
        item_title = " ".join(title_tokens[common_length:]).strip() or title
        contained.append({
            "series_index": index,
            "title": item_title,
        })
    contained.sort(key=lambda item: float(item["series_index"]))
    return {
        "audiobook_collection_type": (
            "multi_book_trilogy" if len(contained) == 3 else "multi_book_set"
        ),
        "contained_books": contained,
    }


def _first_tag_value(tags, keys: tuple[str, ...]) -> str | None:
    for key in keys:
        value = tags.get(key) if tags is not None else None
        if not value:
            continue
        if isinstance(value, (list, tuple)):
            value = value[0] if value else None
        if value is not None:
            text = str(value).strip()
            if text:
                return text
    return None


def extract_audio_metadata(path: Path) -> dict:
    try:
        from mutagen import File as MutagenFile
    except ImportError:
        return {}
    try:
        media = MutagenFile(str(path), easy=True)
    except Exception:
        return {}
    if media is None or media.tags is None:
        return {}
    tags = media.tags
    date = _first_tag_value(tags, ("date", "year", "originaldate"))
    year_match = YEAR_RE.search(date or "")
    return {
        key: value
        for key, value in {
            "title": _first_tag_value(tags, ("album",)),
            "author": _first_tag_value(
                tags,
                ("albumartist", "artist", "author"),
            ),
            "year": year_match.group(1) if year_match else None,
            "narrator": _first_tag_value(
                tags,
                ("narrator", "performer", "composer"),
            ),
            "chapter_title": _first_tag_value(tags, ("title",)),
            "track_number": _first_tag_value(tags, ("tracknumber",)),
            "disc_number": _first_tag_value(tags, ("discnumber",)),
        }.items()
        if value
    }


def build_audiobook_metadata_candidates(
    source: Path,
    audio: list[Path],
    artwork: list[Path],
) -> tuple[dict[str, list[dict]], list[dict], list[dict]]:
    candidates: dict[str, list[dict]] = {}
    source_is_container = (
        source.is_dir()
        or source.suffix.casefold() not in AUDIOBOOK_EXTENSIONS
    )
    source_guess = parse_audiobook_name(
        source.name if source_is_container else audio[0].name
    )
    file_guess = parse_audiobook_name(audio[0].name)
    for field in (
        "author", "title", "year", "narrator", "series", "series_index",
    ):
        source_value = source_guess.get(field)
        file_value = file_guess.get(field)
        if str(source_value or "").casefold() not in UNKNOWN_AUDIOBOOK_VALUES:
            add_candidate(candidates, make_candidate(
                field,
                source_value,
                "folder_name" if source_is_container else "filename",
                "Folder name" if source_is_container else "Filename",
                0.72,
            ))
        if str(file_value or "").casefold() not in UNKNOWN_AUDIOBOOK_VALUES:
            add_candidate(candidates, make_candidate(
                field,
                file_value,
                "filename",
                "Filename",
                0.68,
            ))

    chapter_candidates: list[dict] = []
    generic_audio_tag_count = 0
    detected_discs: set[int] = set()
    for path in audio:
        embedded = extract_audio_metadata(path)
        for field in ("author", "title", "year", "narrator"):
            candidate = make_candidate(
                field,
                embedded.get(field),
                f"audio_tag_{field}",
                "Embedded audio tags",
                0.88 if field in {"author", "title"} else 0.78,
            )
            if field == "title" and candidate and candidate.get("ignored"):
                generic_audio_tag_count += 1
            add_candidate(candidates, candidate)
        chapter_title = embedded.get("chapter_title")
        folder_disc = next(
            (
                int(match.group(1))
                for part in path.parts
                if (
                    match := re.search(
                        r"\b(?:disc|disk|cd)\s*0*(\d+)\b",
                        part,
                        flags=re.I,
                    )
                )
            ),
            None,
        )
        raw_disc = embedded.get("disc_number")
        disc_match = re.match(r"\s*(\d+)", str(raw_disc or ""))
        disc_number = (
            int(disc_match.group(1))
            if disc_match
            else folder_disc
        )
        if disc_number is not None:
            detected_discs.add(disc_number)
        if chapter_title and is_generic_track_value(chapter_title):
            generic_audio_tag_count += 1
        if chapter_title and not is_generic_track_value(chapter_title):
            chapter_candidates.append({
                "source_file": (
                    str(path.relative_to(source))
                    if source_is_container
                    else path.name
                ),
                "track_number": embedded.get("track_number"),
                "disc_number": disc_number,
                "current_name": path.name,
                "suggested_title": chapter_title,
                "source": "audio_tag_title",
                "source_label": "Embedded audio title",
                "confidence": 0.8,
                "confidence_label": "medium",
            })

    artwork_candidates = [
        candidate
        for path in artwork
        if (
            candidate := make_candidate(
                "artwork",
                str(path.relative_to(source))
                if source_is_container
                else path.name,
                "audiobook_sidecar_artwork",
                "Audiobook artwork file",
                0.9,
            )
        )
    ]
    summary = {
        "generic_audio_tag_count": generic_audio_tag_count,
        "detected_disc_count": len(detected_discs),
        "candidate_warning_count": sum(
            bool(candidate.get("ignored") or candidate.get("notes"))
            for values in candidates.values()
            for candidate in values
        ),
    }
    return candidates, chapter_candidates, artwork_candidates, summary


def audiobook_destination(
    *,
    audiobooks_root: Path,
    author: str,
    title: str,
    year: str | None,
) -> Path:
    return (
        audiobooks_root
        / safe_audiobook_path_part(author)
        / safe_audiobook_path_part(f"{year or 'Unknown Year'} - {title}")
    )


def build_audiobook_metadata(source: Path, audiobooks_root: Path) -> dict:
    files = collect_audiobook_files(source)
    audio = files["audio"]
    primary = sorted(audio, key=lambda path: path.name.casefold())[0]
    source_guess = parse_audiobook_name(
        source.name if source.is_dir() else primary.name
    )
    file_guess = parse_audiobook_name(primary.name)
    author = (
        source_guess["author"]
        if source_guess["author"] != "Unknown Author"
        else file_guess["author"]
    )
    title = (
        source_guess["title"]
        if source_guess["title"] != "Unknown Title"
        else file_guess["title"]
    )
    year = source_guess.get("year") or file_guess.get("year")
    narrator = source_guess.get("narrator") or file_guess.get("narrator")
    (
        metadata_candidates,
        chapter_candidates,
        artwork_candidates,
        candidate_summary,
    ) = build_audiobook_metadata_candidates(
        source,
        audio,
        files["artwork"],
    )
    author = preferred_candidate_value(
        metadata_candidates,
        "author",
        author if author.casefold() not in UNKNOWN_AUDIOBOOK_VALUES else "Unknown Author",
    )
    title = preferred_candidate_value(
        metadata_candidates,
        "title",
        title if title.casefold() not in UNKNOWN_AUDIOBOOK_VALUES else "Unknown Title",
    )
    year = preferred_candidate_value(metadata_candidates, "year", year)
    narrator = preferred_candidate_value(
        metadata_candidates,
        "narrator",
        narrator,
    )
    fmt = audiobook_format_for(audio)
    collection_preview = detect_audiobook_collection(source, audio)
    destination = audiobook_destination(
        audiobooks_root=audiobooks_root,
        author=author,
        title=title,
        year=year,
    )
    warnings = []
    if author.strip().casefold() in UNKNOWN_AUDIOBOOK_VALUES:
        warnings.append("audiobook_author_missing")
    if title.strip().casefold() in UNKNOWN_AUDIOBOOK_VALUES:
        warnings.append("audiobook_title_missing")
    if not year:
        warnings.append("audiobook_year_missing")
    if not narrator:
        warnings.append("audiobook_narrator_missing")
    if files["other"]:
        warnings.append("audiobook_ignored_sidecars_present")
    return {
        "media_kind": "audiobook",
        "metadata_assist_version": METADATA_ASSIST_VERSION,
        "candidate_runtime": {
            "metadata_assist_version": METADATA_ASSIST_VERSION,
            "candidate_filter_active": True,
            "generic_audio_tags_hidden": candidate_summary[
                "generic_audio_tag_count"
            ],
            "bad_author_splits_blocked": 0,
            "source_labels_removed": 0,
            "pdf_metadata_attempted": False,
            "epub_metadata_attempted": False,
            "metadata_reader_errors": [],
            "pdf_garbage_candidates_blocked": 0,
            "author_names_canonicalized": 0,
        },
        "review_type": "audiobook",
        "review_mode": "single_item",
        "author": author,
        "title": title,
        "year": year,
        "narrator": narrator,
        "series": source_guess.get("series") or file_guess.get("series"),
        "series_index": (
            source_guess.get("series_index")
            or file_guess.get("series_index")
        ),
        "format": fmt,
        "audiobook_file_count": len(audio),
        "chapter_count": len(audio),
        "audio_files": [
            str(path.relative_to(source)) if source.is_dir() else path.name
            for path in audio
        ],
        "primary_audio_file": primary.name,
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
        "chapter_candidates": chapter_candidates,
        "artwork_candidates": artwork_candidates,
        **collection_preview,
        **candidate_summary,
    }
