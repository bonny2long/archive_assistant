import re
from collections import Counter
from pathlib import Path

# pyrefly: ignore [missing-import]
from mutagen import File as MutagenFile

AUDIO_EXTENSIONS = {".mp3", ".flac", ".m4a", ".aac", ".wav", ".ogg", ".opus"}
UNKNOWN_VALUES = {"", "unknown", "unknown artist", "unknown album", "unknown year"}
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


def is_audio_file(path: Path) -> bool:
    return path.suffix.lower() in AUDIO_EXTENSIONS


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
    normalized = str(value or "").lower().replace("_", " ")
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


def is_compilation_artist(value: str | None) -> bool:
    return normalize_compilation_artist(value) == "Various Artists"


def _clean_spacing(value: str) -> str:
    value = value.replace("_", " ")
    value = re.sub(r"\s+", " ", value).strip(" .-_")
    return value


def _clean_artist_text(value: str) -> str:
    value = re.sub(r"(?i)(?:_|\s)+(?:and|x|&)(?:_|\s)+", " & ", value)
    value = _clean_spacing(value)
    return normalize_compilation_artist(value) or value


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
        ).strip(" .-_()[]")
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


def extract_music_metadata(path: Path) -> dict:
    audio = MutagenFile(path, easy=True)
    folder_artist = "Unknown Artist"
    folder_album = path.parent.name or "Unknown Album"
    folder_year = "Unknown Year"
    duration = round(audio.info.length, 2) if audio and hasattr(audio, "info") else 0

    return {
        "albumartist": _first(audio.get("albumartist"), folder_artist) if audio else folder_artist,
        "artist": _first(audio.get("artist"), folder_artist) if audio else folder_artist,
        "album": _first(audio.get("album"), folder_album) if audio else folder_album,
        "title": _first(audio.get("title"), path.stem) if audio else path.stem,
        "tracknumber": _first(audio.get("tracknumber"), "1") if audio else "1",
        "discnumber": _parse_disc(audio.get("discnumber") if audio else None, path),
        "date": _first(audio.get("date"), folder_year) if audio else folder_year,
        "genre": _first(audio.get("genre"), "Unknown") if audio else "Unknown",
        "duration_seconds": duration,
        "extension": path.suffix.lower(),
    }


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
    artist = "".join(c if c not in '<>:"/\\|?*' else "_" for c in str(artist_value))
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
