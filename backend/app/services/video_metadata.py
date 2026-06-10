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
SUBTITLE_EXTENSIONS = {".srt", ".ass", ".ssa", ".vtt", ".sub", ".idx"}
MOVIE_ARTWORK_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}
VIDEO_SIDECAR_EXTENSIONS = {
    ".nfo",
    ".txt",
    ".log",
    ".sfv",
    ".md5",
    ".url",
    ".m3u",
    ".nzb",
}
YEAR_PATTERN = re.compile(r"(?<!\d)(19\d{2}|20\d{2})(?!\d)")
EPISODE_PATTERN = re.compile(
    r"(?<![a-z0-9])(?:s\d{1,2}[ ._-]*e\d{1,3}|"
    r"\d{1,2}x\d{1,3}|season[ ._-]*\d+|episode[ ._-]*\d+)(?![a-z0-9])",
    re.IGNORECASE,
)
TV_CODE_PATTERN = re.compile(
    r"(?<![a-z0-9])s(?P<season>\d{1,2})[ ._-]*e(?P<episode>\d{1,3})(?![a-z0-9])",
    re.IGNORECASE,
)
TV_X_PATTERN = re.compile(
    r"(?<![a-z0-9])(?P<season>\d{1,2})x(?P<episode>\d{1,3})(?![a-z0-9])",
    re.IGNORECASE,
)
SEASON_PATTERN = re.compile(
    r"(?<![a-z0-9])season[ ._-]*(?P<season>\d{1,2})(?![a-z0-9])",
    re.IGNORECASE,
)
TV_FOLDER_SEASON_PATTERN = re.compile(
    r"(?<![a-z0-9])(?:season|series|s)[ ._-]*(?P<season>\d{1,2})(?![a-z0-9])",
    re.IGNORECASE,
)
EPISODE_ONLY_PATTERN = re.compile(
    r"(?<![a-z0-9])episode[ ._-]*(?P<episode>\d{1,3})(?![a-z0-9])",
    re.IGNORECASE,
)
RELEASE_TAG_PATTERN = re.compile(
    r"(?<![a-z0-9])(?:2160p|1080p|720p|4k|bluray|web[ ._-]?dl|webrip|"
    r"hdrip|dvdrip|x264|x265|hevc|aac|dts|yts(?:[ ._-]?am)?|rarbg|"
    r"amzn|nf|hmax)(?![a-z0-9])",
    re.IGNORECASE,
)
TV_OAD_PATTERN = re.compile(
    r"(?<![a-z0-9])(?P<type>oad|ova)[ ._-]*(?:e|ep)?(?P<number>\d{1,3})(?![a-z0-9])",
    re.IGNORECASE,
)
TV_SPECIAL_PATTERN = re.compile(
    r"(?<![a-z0-9])(?:sp|special)[ ._-]*(?P<number>\d{1,3})(?![a-z0-9])",
    re.IGNORECASE,
)
TV_PART_PATTERN = re.compile(
    r"(?<![a-z0-9])s(?P<season>\d{1,2})[ ._-]*p(?P<part>\d{1,3})(?![a-z0-9])",
    re.IGNORECASE,
)
TV_FRACTIONAL_EPISODE_PATTERN = re.compile(
    r"(?<![a-z0-9])s(?P<season>\d{1,2})[ ._-]*e(?P<episode>\d{1,3})[ ._-]*"
    r"\.(?P<fraction>\d{1,3})(?![a-z0-9])",
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


def looks_like_tv_episode(value: str) -> bool:
    return bool(
        TV_CODE_PATTERN.search(value)
        or TV_X_PATTERN.search(value)
        or EPISODE_ONLY_PATTERN.search(value)
    )


def folder_looks_like_tv_show(root: Path, video_files: list[Path]) -> bool:
    if not video_files:
        return False

    parsed = [parse_tv_episode_name(path.name) for path in video_files]
    parsed_count = sum(
        item.get("season_number") is not None
        and item.get("episode_number") is not None
        for item in parsed
    )
    if parsed_count and parsed_count / len(video_files) >= 0.6:
        return True

    season_folders = [root.name]
    season_folders.extend(
        parent.name
        for video_file in video_files
        for parent in video_file.parents
        if parent == root or root in parent.parents
    )
    has_season_folder = any(
        TV_FOLDER_SEASON_PATTERN.search(name)
        for name in season_folders
    )
    if len(video_files) >= 2 and has_season_folder:
        return True
    return parsed_count >= 1 and has_season_folder


def parse_tv_folder_name(value: str) -> dict:
    raw = Path(value).name
    year_matches = list(YEAR_PATTERN.finditer(raw))
    year = year_matches[-1].group(1) if year_matches else None
    season_match = TV_FOLDER_SEASON_PATTERN.search(raw)
    season_number = (
        int(season_match.group("season"))
        if season_match
        else None
    )
    title = YEAR_PATTERN.sub(" ", raw)
    title = TV_FOLDER_SEASON_PATTERN.sub(" ", title)
    title = re.sub(r"[._]+", " ", title)
    title = re.sub(r"\s*[-]+\s*", " ", title)
    title = re.sub(r"\s+", " ", title).strip(" -._()[]")
    return {
        "show_title": title or None,
        "season_number": season_number,
        "year": year,
    }


def safe_movie_path_part(value: str) -> str:
    safe = "".join(
        character if character not in '<>:"/\\|?*' else "_"
        for character in value
    ).strip(" .")
    return safe or "Unknown Movie"


def safe_tv_path_part(value: str) -> str:
    safe = "".join(
        character if character not in '<>:"/\\|?*' else "_"
        for character in value
    ).strip(" .")
    return safe or "Unknown TV Show"


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


def _extract_titles(raw: str, token_start: int, token_end: int) -> tuple[str | None, str | None]:
    show_source = raw[:token_start]
    title_source = raw[token_end:]
    show_title = re.sub(r"[._]+", " ", show_source)
    show_title = re.sub(r"\s*[-]+\s*$", "", show_title)
    show_title = re.sub(r"\s+", " ", show_title).strip(" -._()[]")
    episode_title = RELEASE_TAG_PATTERN.sub(" ", title_source)
    episode_title = re.sub(r"^[ ._-]+", "", episode_title)
    episode_title = re.sub(r"[._]+", " ", episode_title)
    episode_title = re.sub(r"\s+", " ", episode_title).strip(" -._()[]")
    return (show_title or None), (episode_title or None)


def _year_from_raw(raw: str) -> str | None:
    year_matches = list(YEAR_PATTERN.finditer(raw))
    return year_matches[-1].group(1) if year_matches else None


def parse_tv_episode_name(value: str) -> dict:
    name = Path(value).name
    raw = Path(name).stem if Path(name).suffix.lower() in (
        VIDEO_EXTENSIONS | SUBTITLE_EXTENSIONS
    ) else name
    year = _year_from_raw(raw)

    result: dict = {
        "show_title": None,
        "season_number": None,
        "episode_number": None,
        "episode_code": None,
        "episode_title": None,
        "raw_name": raw,
        "year": year,
        "confidence": 0.4,
        "is_special": False,
        "destination_group": None,
        "special_label": None,
    }

    # 1. Fractional episode (SxxExx.x) — must be checked before regular SxxExx
    fractional_match = TV_FRACTIONAL_EPISODE_PATTERN.search(raw)
    if fractional_match:
        season = int(fractional_match.group("season"))
        episode = int(fractional_match.group("episode"))
        fraction = fractional_match.group("fraction")
        special_label = f"S{season:02d}E{episode:02d}.{fraction}"
        show_title, episode_title = _extract_titles(
            raw, fractional_match.start(), fractional_match.end()
        )
        result.update({
            "season_number": season,
            "episode_number": episode,
            "episode_code": special_label,
            "episode_title": episode_title,
            "show_title": show_title,
            "year": year,
            "confidence": 0.8,
            "is_special": True,
            "destination_group": "specials",
            "special_label": special_label,
        })
        return result

    # 2. OAD/OVA pattern
    oad_match = TV_OAD_PATTERN.search(raw)
    if oad_match:
        oad_type = oad_match.group("type").lower()
        number = int(oad_match.group("number"))
        dest_group = "oad" if oad_type == "oad" else "ova"
        special_label = f"{oad_type.upper()}E{number:02d}"
        show_title, episode_title = _extract_titles(
            raw, oad_match.start(), oad_match.end()
        )
        result.update({
            "season_number": None,
            "episode_number": None,
            "episode_code": special_label,
            "episode_title": episode_title,
            "show_title": show_title,
            "year": year,
            "confidence": 0.8,
            "is_special": True,
            "destination_group": dest_group,
            "special_label": special_label,
        })
        return result

    # 3. Special/SP pattern
    special_match = TV_SPECIAL_PATTERN.search(raw)
    if special_match:
        number = int(special_match.group("number"))
        special_label = f"SP{number:02d}"
        show_title, episode_title = _extract_titles(
            raw, special_match.start(), special_match.end()
        )
        result.update({
            "season_number": None,
            "episode_number": None,
            "episode_code": special_label,
            "episode_title": episode_title,
            "show_title": show_title,
            "year": year,
            "confidence": 0.8,
            "is_special": True,
            "destination_group": "specials",
            "special_label": special_label,
        })
        return result

    # 4. Standard SxxExx or Xxx pattern
    match = TV_CODE_PATTERN.search(raw) or TV_X_PATTERN.search(raw)

    # 5. Part pattern (SxxPxx)
    part_match = TV_PART_PATTERN.search(raw) if not match else None

    season_match = SEASON_PATTERN.search(raw)
    episode_match = EPISODE_ONLY_PATTERN.search(raw)

    season_number = int(match.group("season")) if match else (
        int(part_match.group("season")) if part_match else (
            int(season_match.group("season")) if season_match else None
        )
    )
    episode_number = int(match.group("episode")) if match else (
        int(part_match.group("part")) if part_match else (
            int(episode_match.group("episode")) if episode_match else None
        )
    )

    if part_match:
        special_label = f"S{season_number:02d}P{part_match.group('part')}"
        show_title, episode_title = _extract_titles(
            raw, part_match.start(), part_match.end()
        )
        result.update({
            "season_number": season_number,
            "episode_number": episode_number,
            "episode_code": f"S{season_number:02d}E{episode_number:02d}",
            "episode_title": episode_title,
            "show_title": show_title,
            "year": year,
            "confidence": 0.8,
            "is_special": True,
            "destination_group": "specials",
            "special_label": special_label,
        })
        return result

    token_match = match or episode_match
    if token_match:
        show_title, episode_title = _extract_titles(
            raw, token_match.start(), token_match.end()
        )
    else:
        show_title = None
        episode_title = None

    episode_code = (
        f"S{season_number:02d}E{episode_number:02d}"
        if season_number is not None and episode_number is not None
        else None
    )
    result.update({
        "show_title": show_title,
        "season_number": season_number,
        "episode_number": episode_number,
        "episode_code": episode_code,
        "episode_title": episode_title,
        "year": year,
        "confidence": 0.8 if episode_code else 0.4,
    })
    return result


def tv_subtitle_language_suffix(
    subtitle: Path,
    episode: Path | None = None,
) -> str:
    subtitle_stem = subtitle.stem
    if episode is not None:
        episode_stem = episode.stem
        if subtitle_stem.casefold().startswith(episode_stem.casefold()):
            suffix = subtitle_stem[len(episode_stem):].strip(" ._-")
            return f".{suffix}" if suffix else ""

    parsed = parse_tv_episode_name(subtitle.name)
    episode_title = str(parsed.get("episode_title") or "").strip(" ._-")
    if re.fullmatch(r"[a-z]{2,3}(?:[._-][a-z]{2,3})?", episode_title, re.I):
        return f".{episode_title.replace('_', '.').replace('-', '.')}"
    return ""


def tv_artwork_scope(path: Path, root: Path) -> dict:
    relative = path.relative_to(root)
    season_number = None
    for part in reversed(relative.parent.parts):
        folder = parse_tv_folder_name(part)
        if folder.get("season_number") is not None:
            season_number = int(folder["season_number"])
            break

    stem = path.stem.casefold()
    season_match = TV_FOLDER_SEASON_PATTERN.search(path.stem)
    if season_match:
        season_number = int(season_match.group("season"))
    is_season_artwork = (
        season_number is not None
        or stem == "season"
        or stem.startswith("season")
    )
    return {
        "relative_source": str(relative),
        "artwork_scope": "season" if is_season_artwork else "show",
        "season_number": season_number,
    }
