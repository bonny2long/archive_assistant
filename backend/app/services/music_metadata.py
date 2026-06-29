import re
from collections import Counter
from pathlib import Path

from app.services.embedded_metadata_reader import (
    apply_embedded_metadata_evidence,
    read_embedded_metadata,
)
from app.services.metadata_candidates import add_candidate, make_candidate

AUDIO_EXTENSIONS = {".mp3", ".flac", ".m4a", ".aac", ".wav", ".ogg", ".opus"}
ARTWORK_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".gif"}
PREFERRED_ARTWORK_STEMS = {
    "cover",
    "folder",
    "front",
    "back",
    "album",
    "artwork",
    "albumart",
    "albumartsmall",
    "albumartlarge",
    "scan",
    "booklet",
}
UNKNOWN_VALUES = {"", "unknown", "unknown artist", "unknown album", "unknown year"}
GENERIC_MUSIC_VALUES = {
    "",
    "unknown",
    "unknown artist",
    "unknown album",
    "unknown year",
    "va",
    "v.a.",
    "various",
}
YEAR_PATTERN = re.compile(r"(?<!\d)(19\d{2}|20\d{2})(?!\d)")
BRACKETED_TEXT = re.compile(r"[\[(][^\])]*(?:mp3|flac|pmedia|lossless|web|cd|vinyl|kbps|bit|remaster|deluxe)[^\])]*[\])]", re.IGNORECASE)
TRAILING_RELEASE_NOISE = re.compile(
    r"""
    (?:[\s._-]+
        (?:
            mp3|flac|pmedia|lossless|web(?:-?dl)?|cd(?:rip)?|vinyl|
            remaster(?:ed)?|deluxe(?:\s+edition)?|expanded\s+edition|
            anniversary\s+edition|(?:16|24)\s*bit|v0|v2|\d{3,4}\s*kbps
        )
    )+$
    """,
    re.IGNORECASE | re.VERBOSE,
)
COMPILATION_ARTISTS = {"va", "v.a.", "various", "various artists", "ost", "soundtrack"}
COMPILATION_PREFIX_PATTERN = re.compile(
    r"^\s*(?P<prefix>v[._\s-]*a[._]?|various\s+artists)"
    r"\s*(?:[-_]+|\s+-\s+|\s+)\s*(?P<artist>.+)$",
    re.IGNORECASE,
)
DISCOGRAPHY_TOKENS = {
    "discography",
    "collection",
    "complete",
    "albums",
    "studio albums",
}
DISCOGRAPHY_YEAR_RANGE = re.compile(r"(?<!\d)(19\d{2}|20\d{2})\s*[-–]\s*(19\d{2}|20\d{2})(?!\d)")
DISCOGRAPHY_FORMAT_TAG = re.compile(
    r"(?i)(?:[\[(]\s*)?(flac(?:\s+songs)?|mp3|320\s*kbps|(?:16|24)\s*bit|"
    r"(?:44[.]1|48)\s*khz)(?:\s*[\])])?"
)
DECORATIVE_SYMBOLS = re.compile(r"[^\w\s&'.,()\-]+", re.UNICODE)


def is_audio_file(path: Path) -> bool:
    return path.suffix.lower() in AUDIO_EXTENSIONS


def is_artwork_file(path: Path) -> bool:
    return path.suffix.lower() in ARTWORK_EXTENSIONS


def is_preferred_artwork_file(path: Path) -> bool:
    return is_artwork_file(path) and path.stem.casefold() in PREFERRED_ARTWORK_STEMS


def is_disc_folder_name(value: str) -> bool:
    return bool(
        re.fullmatch(
            r"(?:cd|disc|disk)\s*\d+|side\s*[a-z]",
            value.strip(),
            flags=re.IGNORECASE,
        )
    )


def discography_artist_from_folder(value: str) -> str | None:
    return parse_discography_parent_folder(value)["artist"]


def parse_discography_parent_folder(folder_name: str) -> dict:
    raw = folder_name.strip()
    removed_tokens: list[str] = []

    year_match = DISCOGRAPHY_YEAR_RANGE.search(raw)
    year_range = year_match.group(0) if year_match else None
    if year_range:
        removed_tokens.append(year_range)

    format_matches = [match.group(0) for match in DISCOGRAPHY_FORMAT_TAG.finditer(raw)]
    format_hint = None
    for token in format_matches:
        normalized = token.lower()
        if "flac" in normalized:
            format_hint = "FLAC"
        elif normalized.strip("[]() ").lower() == "mp3":
            format_hint = format_hint or "MP3"
        removed_tokens.append(token)

    collection_matches = re.findall(
        r"(?i)\b(?:complete\s+)?(?:discography|collection|studio\s+albums|albums)\b",
        raw,
    )
    removed_tokens.extend(collection_matches)

    bracketed_source_tags = re.findall(r"\[[^\]]+\]", raw)
    for token in bracketed_source_tags:
        if token not in removed_tokens:
            removed_tokens.append(token)

    cleaned = raw
    for token in removed_tokens:
        cleaned = cleaned.replace(token, " ")
    decorative_tokens = [
        token.strip()
        for token in DECORATIVE_SYMBOLS.findall(cleaned)
        if token.strip()
    ]
    removed_tokens.extend(decorative_tokens)
    cleaned = DECORATIVE_SYMBOLS.sub(" ", cleaned)
    cleaned = _clean_spacing(cleaned)

    # A trailing release username is only removed after other pack markers were found.
    trailing_source = None
    if removed_tokens:
        source_match = re.search(r"(?:^|\s)([A-Za-z]*\d+[A-Za-z0-9_-]*)$", cleaned)
        if source_match:
            trailing_source = source_match.group(1)
            cleaned = cleaned[:source_match.start(1)]
            removed_tokens.append(trailing_source)

    artist = _clean_spacing(cleaned.rstrip(" -"))
    clean_collection_name = f"{artist} Discography" if artist else "Discography"
    return {
        "artist": artist or None,
        "clean_collection_name": clean_collection_name,
        "removed_tokens": list(dict.fromkeys(token.strip() for token in removed_tokens if token.strip())),
        "year_range": year_range,
        "format_hint": format_hint,
        "warnings": [] if artist else ["artist_missing"],
    }


def looks_like_discography_parent(
    parent: Path,
    child_audio_folders: list[Path],
    child_track_metadata: dict[str, list[dict]],
) -> bool:
    eligible = [
        child for child in child_audio_folders
        if not is_disc_folder_name(child.name)
    ]
    parent_key = canonical_text_key(parent.name)
    if eligible and any(token in parent_key for token in DISCOGRAPHY_TOKENS):
        return True
    if len(eligible) < 2:
        return False

    year_pattern_count = sum(
        bool(YEAR_PATTERN.search(child.name))
        for child in eligible
    )
    if year_pattern_count >= 2:
        return True

    artists = []
    for child in eligible:
        common = common_track_artist(child_track_metadata.get(str(child), []))
        if common:
            artists.append(canonical_artist_key(common))
    return len(artists) >= 2 and len(set(artists)) == 1


def _first(value, default="Unknown"):
    if value is None:
        return default
    if isinstance(value, list) and value:
        return str(value[0])
    return str(value)


def _parse_disc(value, path: Path | None = None) -> int:
    raw = _first(value, None)
    if raw:
        try:
            return int(str(raw).strip().split("/")[0].split(".")[0])
        except (TypeError, ValueError):
            pass
    if path:
        match = re.search(r"(?:CD|DISC|DISK)\s*(\d+)", path.parent.name.upper())
        if match:
            return int(match.group(1))
    return 1


def _positive_int(value, default: int | None = None) -> int | None:
    match = re.search(r"\d+", str(value or ""))
    if not match:
        return default
    parsed = int(match.group())
    return parsed if parsed > 0 else default


def music_track_numbers(
    metadata: dict | None,
    filename: str = "",
) -> tuple[int, int | None]:
    metadata = metadata or {}
    raw_disc = metadata.get("discnumber")
    raw_track = str(metadata.get("tracknumber") or "").strip()
    disc = _positive_int(raw_disc, 1) or 1
    track = None

    combined = re.match(r"^\s*(\d+)\s*-\s*(\d+)", raw_track)
    if combined:
        if raw_disc in (None, "", "Unknown"):
            disc = int(combined.group(1))
        track = int(combined.group(2))
    else:
        track = _positive_int(raw_track)

    filename_combined = re.match(r"^\s*(\d+)\s*-\s*(\d+)\b", filename)
    filename_track = re.match(r"^\s*(\d+)\b", filename)
    if filename_combined:
        if raw_disc in (None, "", "Unknown"):
            disc = int(filename_combined.group(1))
        if track is None:
            track = int(filename_combined.group(2))
    elif track is None and filename_track:
        track = int(filename_track.group(1))

    return disc, track


def music_track_sort_key(file) -> tuple[int, int, str, int]:
    metadata = getattr(file, "metadata_json", None) or {}
    filename = str(getattr(file, "file_name", "") or "")
    disc, track = music_track_numbers(metadata, filename)
    stable_id = int(getattr(file, "id", 0) or 0)
    return disc, track if track is not None else 1_000_000, filename.lower(), stable_id


def sort_music_tracks(files: list) -> list:
    return sorted(files, key=music_track_sort_key)


def normalize_key(value: str) -> str:
    return re.sub(r"\s+", " ", str(value).strip().lower())


def canonical_text_key(value: str) -> str:
    """Normalize text for duplicate comparison, not display."""
    normalized = str(value or "").lower().replace("_", " ")
    normalized = re.sub(r"['’]", "", normalized)
    normalized = re.sub(r"[^a-z0-9]+", " ", normalized)
    return re.sub(r"\s+", " ", normalized).strip()


def canonical_artist_key(value: str) -> str:
    """Normalize obvious artist aliases for destination comparison."""
    cleaned = clean_compilation_artist(str(value or ""))[0]
    normalized = cleaned.lower().replace("_", " ")
    normalized = re.sub(r"\b(?:and|x|feat(?:uring)?|ft)\.?\b", " ", normalized)
    normalized = normalized.replace("&", " ")
    return canonical_text_key(normalized)


def canonical_album_key(value: str) -> str:
    """Normalize album names for destination comparison."""
    return canonical_text_key(value)


def normalize_compilation_artist(value: str | None) -> str | None:
    if not value:
        return None
    normalized = normalize_key(value).replace("v a", "v.a.")
    if normalized in COMPILATION_ARTISTS:
        return "Various Artists"
    return value


def clean_compilation_artist(raw_artist: str) -> tuple[str, dict]:
    raw = str(raw_artist or "").strip()
    match = COMPILATION_PREFIX_PATTERN.match(raw)
    if not match:
        return raw, {}

    display = _clean_spacing(match.group("artist"))
    if not display or normalize_key(display) in UNKNOWN_VALUES:
        return raw, {}
    prefix = match.group("prefix").strip(" ._-")
    return display, {
        "raw_artist": raw,
        "display_artist": display,
        "removed_prefix": prefix.upper().replace(".", "") if prefix else "VA",
        "is_compilation": True,
    }


def compilation_artist_cleanup_from_folder(folder_name: str) -> tuple[str, dict]:
    without_noise = BRACKETED_TEXT.sub("", folder_name).strip(" .-_")
    year_match = YEAR_PATTERN.search(without_noise)
    if year_match:
        without_noise = re.sub(
            rf"(?:^|[\s._-]+)(?:\(|\[)?{re.escape(year_match.group(1))}(?:\)|\])?",
            "",
            without_noise,
            count=1,
        ).strip(" .-_")
    without_noise = TRAILING_RELEASE_NOISE.sub("", without_noise).strip(" .-_")
    parts = re.split(r"\s+-\s+|_-_", without_noise, maxsplit=1)
    if len(parts) != 2:
        return "", {}
    raw_artist = _clean_spacing(parts[0])
    return clean_compilation_artist(raw_artist)


def is_compilation_artist(value: str | None) -> bool:
    return normalize_compilation_artist(value) == "Various Artists"


def _clean_spacing(value: str) -> str:
    value = value.replace("_", " ")
    value = re.sub(r"\s+", " ", value).strip(" .-_")
    return value


def _clean_artist_text(value: str) -> str:
    value = re.sub(r"(?i)(?:_|\s)+(?:and|x|&)(?:_|\s)+", " & ", value)
    value = _clean_spacing(value)
    cleaned, _ = clean_compilation_artist(value)
    return normalize_compilation_artist(cleaned) or cleaned


def _clean_album_text(value: str) -> str:
    value = BRACKETED_TEXT.sub("", value)
    value = _clean_spacing(value)
    previous = None
    while previous != value:
        previous = value
        value = TRAILING_RELEASE_NOISE.sub("", value).strip(" .-_")
        value = _clean_spacing(value)
    return value


def parse_music_folder_name(folder_name: str) -> dict[str, str | None]:
    """Extract a conservative artist/album/year suggestion from a release folder."""
    raw = folder_name.strip()
    year_match = YEAR_PATTERN.search(raw)
    year = year_match.group(1) if year_match else None

    without_noise = BRACKETED_TEXT.sub("", raw).strip(" .-_")
    if year_match:
        without_noise = re.sub(
            rf"(?:^|[\s._-]+)(?:\(|\[)?{re.escape(year_match.group(1))}(?:\)|\])?",
            "",
            without_noise,
            count=1,
        ).strip(" .-_")
    without_noise = TRAILING_RELEASE_NOISE.sub("", without_noise).strip(" .-_")

    parts = re.split(r"\s+-\s+|_-_", without_noise, maxsplit=1)
    if len(parts) == 1 and " - " in raw:
        parts = raw.split(" - ", 1)

    artist = _clean_artist_text(parts[0]) if len(parts) == 2 else None
    album = _clean_album_text(parts[-1])

    return {
        "artist": artist or None,
        "album": album or None,
        "year": year,
    }


def common_track_artist(track_metadata: list[dict]) -> str | None:
    artists = []
    for metadata in track_metadata:
        artist = str(metadata.get("artist") or "").strip()
        if normalize_key(artist) not in UNKNOWN_VALUES:
            artists.append(artist)
    if not artists:
        return None
    counts = Counter(normalize_key(artist) for artist in artists)
    winner, count = counts.most_common(1)[0]
    threshold = max(1, (len(track_metadata) * 7 + 9) // 10)
    if count < threshold:
        return None
    return next(artist for artist in artists if normalize_key(artist) == winner)


def common_album_artist(track_metadata: list[dict]) -> str | None:
    artists = []
    for metadata in track_metadata:
        artist = str(metadata.get("albumartist") or "").strip()
        if normalize_key(artist) not in UNKNOWN_VALUES:
            artists.append(artist)
    if not artists:
        return None
    counts = Counter(canonical_artist_key(artist) for artist in artists)
    winner, count = counts.most_common(1)[0]
    threshold = max(1, (len(track_metadata) * 7 + 9) // 10)
    if count < threshold:
        return None
    return next(artist for artist in artists if canonical_artist_key(artist) == winner)


def music_folder_release_tags(folder_name: str) -> list[str]:
    tags = []
    for match in BRACKETED_TEXT.finditer(folder_name):
        tags.append(match.group(0))
    trailing = TRAILING_RELEASE_NOISE.search(folder_name)
    if trailing:
        tags.append(trailing.group(0).strip())
    return list(dict.fromkeys(tag for tag in tags if tag))


def has_mixed_track_artists(track_metadata: list[dict]) -> bool:
    artists = {
        normalize_key(str(metadata.get("artist") or ""))
        for metadata in track_metadata
        if normalize_key(str(metadata.get("artist") or "")) not in UNKNOWN_VALUES
    }
    return len(artists) > 1 and common_track_artist(track_metadata) is None


def metadata_mismatch_warnings(
    track_metadata: list[dict],
    suggested_metadata: dict,
) -> list[str]:
    warnings = []
    albums = {
        canonical_album_key(str(metadata.get("album") or ""))
        for metadata in track_metadata
        if normalize_key(str(metadata.get("album") or "")) not in UNKNOWN_VALUES
    }
    if len(albums) > 1:
        warnings.append("mixed_embedded_metadata_detected")

    suggested_album = canonical_album_key(str(suggested_metadata.get("album") or ""))
    if suggested_album and any(album != suggested_album for album in albums):
        warnings.append("track_album_mismatch_detected")

    if not suggested_metadata.get("compilation"):
        suggested_artist = canonical_artist_key(
            str(suggested_metadata.get("artist") or "")
        )
        track_artists = set()
        for metadata in track_metadata:
            album_artist = str(metadata.get("albumartist") or "")
            artist = str(metadata.get("artist") or "")
            value = (
                album_artist
                if normalize_key(album_artist) not in UNKNOWN_VALUES
                else artist
            )
            if normalize_key(value) not in UNKNOWN_VALUES:
                track_artists.add(canonical_artist_key(value))
        if suggested_artist and any(
            artist != suggested_artist for artist in track_artists
        ):
            warnings.append("track_artist_mismatch_detected")

    return warnings


def build_suggested_metadata(
    source_folder: Path,
    track_metadata: list[dict],
    detected_metadata: dict,
) -> dict:
    folder = parse_music_folder_name(source_folder.name)
    common_artist = common_track_artist(track_metadata)
    folder_artist = folder["artist"]
    sources = {}
    if folder_artist:
        artist = folder_artist
        sources["artist"] = "folder name"
    elif common_artist:
        artist = common_artist
        sources["artist"] = "common track artist"
    else:
        artist = None
    if folder["album"]:
        sources["album"] = "folder name"
    if folder["year"]:
        sources["year"] = "folder name"
    if detected_metadata.get("genre"):
        sources["genre"] = "track tags"

    suggestion = {
        "artist": artist,
        "album": folder["album"],
        "year": folder["year"],
        "genre": detected_metadata.get("genre"),
    }
    cleaned = {key: value for key, value in suggestion.items() if value}
    if sources:
        cleaned["sources"] = sources
    if is_compilation_artist(artist):
        cleaned["compilation"] = True
    return cleaned


def _usable_music_candidate(
    field: str,
    value: object,
    *,
    compilation: bool = False,
) -> bool:
    normalized = normalize_key(str(value or ""))
    if normalized in GENERIC_MUSIC_VALUES:
        return False
    if normalized == "various artists" and not compilation:
        return False
    if field == "track_title" and re.fullmatch(
        r"(?:audio\s*)?(?:cd\s*)?track\s*0*\d+",
        normalized,
    ):
        return False
    if re.match(r"^(?:www[.]|downloaded from|torrent downloaded from)", normalized):
        return False
    return True


def build_music_metadata_candidates(
    source_folder: Path,
    track_metadata: list[dict],
    *,
    compilation: bool = False,
) -> tuple[dict[str, list[dict]], list[dict]]:
    """Build local-only album and track candidates using the shared contract."""
    candidates: dict[str, list[dict]] = {}
    track_candidates: list[dict] = []
    folder = parse_music_folder_name(source_folder.name)

    def add(
        field: str,
        value: object,
        source: str,
        label: str,
        confidence: float,
        notes: list[str] | None = None,
    ) -> None:
        if not _usable_music_candidate(
            field,
            value,
            compilation=compilation,
        ):
            return
        add_candidate(
            candidates,
            make_candidate(
                field,
                value,
                source,
                label,
                confidence,
                notes,
            ),
        )

    add("album_artist", folder.get("artist"), "folder_name", "Release folder name", 0.9)
    add("album_title", folder.get("album"), "folder_name", "Release folder name", 0.9)
    add("year", folder.get("year"), "folder_name", "Release folder name", 0.9)

    parent_name = source_folder.parent.name
    if parent_name and not is_disc_folder_name(parent_name):
        parent_artist = parse_discography_parent_folder(parent_name).get("artist")
        add(
            "album_artist",
            parent_artist,
            "parent_folder_name",
            "Parent folder name",
            0.72,
        )

    embedded_fields = (
        ("album_artist", "albumartist", "audio_tag_albumartist", "Embedded album artist tag", 0.92),
        ("album_artist", "artist", "audio_tag_artist", "Embedded artist tag", 0.75),
        ("album_title", "album", "audio_tag_album", "Embedded album tag", 0.9),
        ("year", "date", "audio_tag_date", "Embedded date tag", 0.82),
        ("genre", "genre", "audio_tag_genre", "Embedded genre tag", 0.72),
    )
    for field, key, source, label, confidence in embedded_fields:
        values = [
            str(metadata.get(key) or "").strip()
            for metadata in track_metadata
            if _usable_music_candidate(
                field,
                metadata.get(key),
                compilation=compilation,
            )
        ]
        if not values:
            continue
        counts = Counter(normalize_key(value) for value in values)
        winner = counts.most_common(1)[0][0]
        display = next(value for value in values if normalize_key(value) == winner)
        add(field, display[:4] if field == "year" else display, source, label, confidence)

    for metadata in track_metadata:
        title = metadata.get("title")
        source = "audio_tag_title"
        source_label = "Embedded track title tag"
        confidence = 0.85
        if not _usable_music_candidate("track_title", title):
            title = Path(str(metadata.get("source_filename") or "")).stem
            source = "filename"
            source_label = "Audio filename"
            confidence = 0.65
        if not _usable_music_candidate("track_title", title):
            continue
        track_candidates.append({
            "field": "track_title",
            "value": str(title).strip(),
            "source": source,
            "source_label": source_label,
            "confidence": confidence,
            "confidence_label": "high" if confidence >= 0.85 else "medium",
            "applied": False,
            "ignored": False,
            "notes": [],
            "track_number": metadata.get("tracknumber"),
            "disc_number": metadata.get("discnumber"),
        })
    return candidates, track_candidates


def extract_music_metadata(path: Path) -> dict:
    embedded = read_embedded_metadata(path, media_type="music_audio")
    fields = embedded.fields
    technical = embedded.technical
    metadata = {
        "albumartist": fields.get("album_artist") or "Unknown Artist",
        "artist": fields.get("artist") or "Unknown Artist",
        "album": fields.get("album") or path.parent.name or "Unknown Album",
        "title": fields.get("title") or path.stem,
        "tracknumber": fields.get("track_number") or "1",
        "discnumber": fields.get("disc_number") or _parse_disc(None, path),
        "date": (fields.get("date") or "Unknown Year")[:10],
        "genre": fields.get("genre") or "Unknown",
        "duration_seconds": technical.get("duration_seconds", 0),
        "bitrate": technical.get("bitrate"),
        "sample_rate": technical.get("sample_rate"),
        "codec": technical.get("codec"),
        "container": technical.get("container"),
        "extension": path.suffix.lower(),
    }
    for source_name, metadata_name in {
        "original_date": "original_date",
        "total_tracks": "total_tracks",
        "total_discs": "total_discs",
        "composer": "composer",
        "album_sort": "album_sort",
        "artist_sort": "artist_sort",
        "musicbrainz_artist_id": "musicbrainz_artist_id",
        "musicbrainz_release_id": "musicbrainz_release_id",
        "musicbrainz_recording_id": "musicbrainz_recording_id",
        "acoustid": "acoustid",
        "bpm": "bpm",
        "compilation": "compilation",
    }.items():
        if fields.get(source_name) is not None:
            metadata[metadata_name] = fields[source_name]
    apply_embedded_metadata_evidence(
        metadata,
        embedded,
        field_map={
            "album_artist": "albumartist",
            "track_number": "tracknumber",
            "disc_number": "discnumber",
        },
    )
    return metadata


def album_group_key(metadata: dict) -> str:
    artist = normalize_key(metadata["albumartist"])
    album = normalize_key(metadata["album"])
    year = normalize_key(metadata["date"])
    return f"{artist}|{album}|{year}"


def evaluate_music_album_metadata(album_meta: dict) -> dict:
    warnings = []
    artist = str(album_meta.get("artist") or album_meta.get("albumartist") or "").strip()
    album = str(album_meta.get("album") or "").strip()
    year = str(album_meta.get("year") or album_meta.get("date") or "").strip()

    if normalize_key(artist) in UNKNOWN_VALUES:
        warnings.append("artist_missing")
    if normalize_key(album) in UNKNOWN_VALUES:
        warnings.append("album_missing")
    if normalize_key(year) in UNKNOWN_VALUES:
        warnings.append("year_missing")
    elif not re.fullmatch(r"(?:19|20)\d{2}", year[:4]):
        warnings.append("year_invalid")
    if normalize_key(str(album_meta.get("genre") or "")) in UNKNOWN_VALUES:
        warnings.append("genre_missing")

    raw_indicators = [
        r"320kbps", r"\bv0\b", r"\bv2\b", r"\bflac\b", r"\bweb\b",
        r"cdrip", r"lossless", r"\[.*\]", r"_",
    ]
    if any(re.search(indicator, album.lower()) for indicator in raw_indicators):
        warnings.append("raw_folder_name_detected")

    critical = {"artist_missing", "album_missing", "year_invalid"}
    if "artist_missing" in warnings and "album_missing" in warnings:
        quality, confidence = "broken", 0.3
    elif any(item in warnings for item in critical):
        quality, confidence = "weak", 0.6
    elif "year_missing" in warnings or "raw_folder_name_detected" in warnings:
        quality, confidence = "fair", 0.8
    else:
        quality, confidence = "good", 1.0

    return {
        "metadata_quality": quality,
        "metadata_warnings": warnings,
        "confidence": confidence,
    }


def suggest_music_destination(metadata: dict, flac_root: Path, mp3_root: Path) -> Path:
    artist_value = metadata.get("albumartist") or metadata.get("artist") or "Unknown Artist"
    album_value = metadata.get("album") or "Unknown Album"
    artist_display, _ = clean_compilation_artist(str(artist_value))
    artist = "".join(c if c not in '<>:"/\\|?*' else "_" for c in artist_display)
    album = "".join(c if c not in '<>:"/\\|?*' else "_" for c in str(album_value))
    year = str(metadata.get("date") or metadata.get("year") or "")[:4]
    folder = f"{year} - {album}" if year.isdigit() else album
    root = flac_root if "flac" in str(metadata.get("extension", "")).lower() else mp3_root
    return root / artist / folder


def music_track_filename(
    metadata: dict,
    extension: str,
    disc_count: int,
    source_filename: str = "",
) -> str:
    fallback_title = Path(source_filename).stem or "Unknown Track"
    title_value = str(metadata.get("title") or fallback_title)
    title = "".join(c if c not in '<>:"/\\|?*' else "_" for c in title_value)
    disc, parsed_track = music_track_numbers(metadata, source_filename)
    track = parsed_track or 1
    if disc_count > 1:
        return f"{disc}-{track:02d} - {title}{extension}"
    return f"{track:02d} - {title}{extension}"
