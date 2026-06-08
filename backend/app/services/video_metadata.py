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
VIDEO_SIDECAR_EXTENSIONS = {".nfo", ".txt", ".log", ".sfv"}
YEAR_PATTERN = re.compile(r"(?<!\d)(19\d{2}|20\d{2})(?!\d)")
EPISODE_PATTERN = re.compile(
    r"\b(?:s\d{1,2}e\d{1,3}|season[ ._-]*\d+|episode[ ._-]*\d+)\b",
    re.IGNORECASE,
)
RELEASE_TAG_PATTERN = re.compile(
    r"\b(?:2160p|1080p|720p|4k|bluray|web[ ._-]?dl|webrip|"
    r"hdrip|dvdrip|x264|x265|hevc|aac|dts|rarbg|yify)\b.*$",
    re.IGNORECASE,
)


def is_video_file(path: Path) -> bool:
    return path.suffix.lower() in VIDEO_EXTENSIONS


def is_subtitle_file(path: Path) -> bool:
    return path.suffix.lower() in SUBTITLE_EXTENSIONS


def is_movie_artwork(path: Path) -> bool:
    return path.suffix.lower() in MOVIE_ARTWORK_EXTENSIONS


def looks_like_tv(value: str) -> bool:
    return bool(EPISODE_PATTERN.search(value))


def safe_movie_path_part(value: str) -> str:
    safe = "".join(
        character if character not in '<>:"/\\|?*' else "_"
        for character in value
    ).strip(" .")
    return safe or "Unknown Movie"


def parse_movie_name(value: str) -> dict:
    raw = Path(value).stem
    year_matches = list(YEAR_PATTERN.finditer(raw))
    year_match = year_matches[-1] if year_matches else None
    year = year_match.group(1) if year_match else None
    title_source = raw[:year_match.start()] if year_match else raw
    title_source = RELEASE_TAG_PATTERN.sub("", title_source)
    title = re.sub(r"[._]+", " ", title_source)
    title = re.sub(r"\s*[-]+\s*", " ", title)
    title = re.sub(r"\s+", " ", title).strip(" -._()[]")
    return {
        "title": title or "Unknown Movie",
        "year": year,
        "raw_name": raw,
    }
