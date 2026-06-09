import re
from pathlib import Path


VIDEO_EXTENSIONS = {
    ".mkv",
    ".mp4",
    ".m4v",
    ".mov",
    ".avi",
    ".webm",
    ".ts",
    ".m2ts",
}
SUBTITLE_EXTENSIONS = {".srt", ".ass", ".ssa", ".vtt", ".sub"}
MOVIE_ARTWORK_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}
VIDEO_SIDECAR_EXTENSIONS = {".nfo", ".txt", ".log", ".sfv", ".md5", ".url"}
YEAR_PATTERN = re.compile(r"(?<!\d)(19\d{2}|20\d{2})(?!\d)")
EPISODE_PATTERN = re.compile(
    r"\b(?:s\d{1,2}e\d{1,3}|season[ ._-]*\d+|episode[ ._-]*\d+)\b",
    re.IGNORECASE,
)
RELEASE_TAG_PATTERN = re.compile(
    r"(?<![a-z0-9])(?:2160p|1080p|720p|4k|bluray|web[ ._-]?dl|webrip|"
    r"hdrip|dvdrip|x264|x265|hevc|aac|dts|yts(?:[ ._-]?am)?|rarbg|"
    r"amzn|nf|hmax)(?![a-z0-9])",
    re.IGNORECASE,
)
GENERIC_MOVIE_NAMES = {
    "movie",
    "movies",
    "video",
    "videos",
    "download",
    "downloads",
    "new folder",
}


def is_video_file(path: Path) -> bool:
    return path.suffix.lower() in VIDEO_EXTENSIONS


def is_subtitle_file(path: Path) -> bool:
    return path.suffix.lower() in SUBTITLE_EXTENSIONS


def is_movie_artwork(path: Path) -> bool:
    return path.suffix.lower() in MOVIE_ARTWORK_EXTENSIONS


def is_ignored_video_sidecar(path: Path) -> bool:
    return path.suffix.lower() in VIDEO_SIDECAR_EXTENSIONS


def looks_like_tv(value: str) -> bool:
    return bool(EPISODE_PATTERN.search(value))


def safe_movie_path_part(value: str) -> str:
    safe = "".join(
        character if character not in '<>:"/\\|?*' else "_"
        for character in value
    ).strip(" .")
    return safe or "Unknown Movie"


def _release_tags(value: str) -> list[str]:
    tags = []
    for match in RELEASE_TAG_PATTERN.finditer(value):
        tag = match.group(0).replace("_", "-")
        tag = re.sub(r"\s+", " ", tag).strip(" .-_[]()")
        if tag and tag.casefold() not in {item.casefold() for item in tags}:
            tags.append(tag)
    return tags


def parse_movie_name(value: str) -> dict:
    name = Path(value).name
    raw = Path(name).stem if Path(name).suffix.lower() in VIDEO_EXTENSIONS else name
    year_matches = list(YEAR_PATTERN.finditer(raw))
    year_match = year_matches[-1] if year_matches else None
    year = year_match.group(1) if year_match else None
    title_source = raw[:year_match.start()] if year_match else raw
    release_tags = _release_tags(raw)
    title_source = RELEASE_TAG_PATTERN.sub(" ", title_source)
    title = re.sub(r"[._]+", " ", title_source)
    title = re.sub(r"\s*[-]+\s*", " ", title)
    title = re.sub(r"\s+", " ", title).strip(" -._()[]")
    return {
        "title": title or "Unknown Movie",
        "year": year,
        "raw_name": raw,
        "release_tags_removed": release_tags,
    }


def useful_movie_name(parsed: dict) -> bool:
    title = str(parsed.get("title") or "").strip()
    return (
        len(title) >= 3
        and title.casefold() not in GENERIC_MOVIE_NAMES
        and title.casefold() != "unknown movie"
    )
