import re
from collections import Counter
from pathlib import Path

# pyrefly: ignore [missing-import]
from mutagen import File as MutagenFile

AUDIO_EXTENSIONS = {".mp3", ".flac", ".m4a", ".aac", ".wav", ".ogg", ".opus"}
UNKNOWN_VALUES = {"", "unknown", "unknown artist", "unknown album", "unknown year"}
RELEASE_NOISE = re.compile(
    r"""
    \s*
    (?:
        \[[^\]]*\] |
        \b(?:mp3|flac|lossless|web(?:-?dl)?|cd(?:rip)?|vinyl|remaster(?:ed)?|deluxe)\b |
        \b(?:v0|v2|\d{3,4}\s*kbps)\b
    ).*$
    """,
    re.IGNORECASE | re.VERBOSE,
)


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


def normalize_key(value: str) -> str:
    return re.sub(r"\s+", " ", str(value).strip().lower())


def _clean_release_text(value: str) -> str:
    value = value.replace("_and_", " & ").replace("_&_ ", " & ")
    value = value.replace("_", " ")
    value = re.sub(r"\s+", " ", value).strip(" .-_")
    return value


def parse_music_folder_name(folder_name: str) -> dict[str, str | None]:
    """Extract a conservative artist/album/year suggestion from a release folder."""
    raw = folder_name.strip()
    year_match = re.search(r"(?<!\d)(19\d{2}|20\d{2})(?!\d)", raw)
    year = year_match.group(1) if year_match else None

    without_noise = RELEASE_NOISE.sub("", raw).strip(" .-_")
    if year_match:
        without_noise = re.sub(
            rf"[\s._-]*(?:\(|\[)?{re.escape(year_match.group(1))}(?:\)|\])?",
            "",
            without_noise,
            count=1,
        ).strip(" .-_")

    parts = re.split(r"\s+-\s+|_-_", without_noise, maxsplit=1)
    if len(parts) == 1 and " - " in raw:
        parts = raw.split(" - ", 1)

    artist = _clean_release_text(parts[0]) if len(parts) == 2 else None
    album = _clean_release_text(parts[-1])
    album = re.sub(r"\s+(?:mp3|flac)$", "", album, flags=re.IGNORECASE).strip()

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
    if count < max(2, (len(track_metadata) + 1) // 2):
        return None
    return next(artist for artist in artists if normalize_key(artist) == winner)


def _artist_tokens(value: str | None) -> set[str]:
    if not value:
        return set()
    return set(re.findall(r"[a-z0-9]+", value.lower().replace("'", ""))) - {"and"}


def build_suggested_metadata(
    source_folder: Path,
    track_metadata: list[dict],
    detected_metadata: dict,
) -> dict:
    folder = parse_music_folder_name(source_folder.name)
    common_artist = common_track_artist(track_metadata)
    folder_artist = folder["artist"]
    if folder_artist and common_artist and _artist_tokens(folder_artist) == _artist_tokens(common_artist):
        artist = folder_artist
    else:
        artist = common_artist or folder_artist
    suggestion = {
        "artist": artist,
        "album": folder["album"],
        "year": folder["year"],
        "genre": detected_metadata.get("genre"),
    }
    return {key: value for key, value in suggestion.items() if value}


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


def music_track_filename(metadata: dict, extension: str, disc_count: int) -> str:
    title = "".join(c if c not in '<>:"/\\|?*' else "_" for c in metadata["title"])
    track = int(str(metadata.get("tracknumber", "1")).split("/")[0])
    disc = int(metadata.get("discnumber", 1))
    if disc_count > 1:
        return f"{disc}-{track:02d} - {title}{extension}"
    return f"{track:02d} - {title}{extension}"
