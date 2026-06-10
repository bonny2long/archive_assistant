from collections import defaultdict
from app.schemas.archive import TvEpisodeReviewPatch


def _normalize_identity(value: str) -> str:
    return value.replace("/", "\\").casefold().strip()


def tv_episode_identity(
    source_file: str | None,
    relative_source: str | None,
) -> tuple[str, str]:
    return (
        _normalize_identity(str(source_file or "")),
        _normalize_identity(str(relative_source or "")),
    )


def ingest_file_identity(ingest_file) -> tuple[str, str]:
    meta = ingest_file.metadata_json or {}
    return tv_episode_identity(
        meta.get("source_file") or ingest_file.file_name,
        meta.get("relative_source"),
    )


def build_ingest_file_lookup(ingest_files: list) -> dict[tuple[str, str], object]:
    lookup: dict[tuple[str, str], object] = {}
    source_only_counts: dict[tuple[str, str], int] = {}
    for item in ingest_files:
        meta = item.metadata_json or {}
        source_file = str(meta.get("source_file") or item.file_name or "")
        relative_source = str(meta.get("relative_source") or "")
        key = tv_episode_identity(source_file, relative_source)
        lookup[key] = item
        source_key = tv_episode_identity(source_file, None)
        source_only_counts[source_key] = source_only_counts.get(source_key, 0) + 1
    for item in ingest_files:
        meta = item.metadata_json or {}
        source_file = str(meta.get("source_file") or item.file_name or "")
        source_key = tv_episode_identity(source_file, None)
        if source_only_counts.get(source_key, 0) == 1:
            lookup[source_key] = item
    return lookup


def sync_tv_episode_metadata_to_ingest_files(
    ingest_files: list,
    reviewed_episodes: list[dict],
) -> list[str]:
    lookup = build_ingest_file_lookup(ingest_files)
    unmatched: list[str] = []
    for episode in reviewed_episodes:
        key = tv_episode_identity(
            episode.get("source_file"), episode.get("relative_source")
        )
        ingest_file = lookup.get(key)
        if ingest_file is None:
            fallback = tv_episode_identity(episode.get("source_file"), None)
            ingest_file = lookup.get(fallback)
        if ingest_file is None:
            unmatched.append(
                str(episode.get("relative_source") or episode.get("source_file") or "unknown")
            )
            continue
        existing = dict(ingest_file.metadata_json or {})
        existing.update({
            "show_title": episode.get("show_title"),
            "season_number": episode.get("season_number"),
            "episode_number": episode.get("episode_number"),
            "episode_code": episode.get("episode_code"),
            "episode_title": episode.get("episode_title"),
            "raw_name": episode.get("raw_name"),
            "source_file": episode.get("source_file"),
            "relative_source": episode.get("relative_source"),
            "include": episode.get("include", True),
            "preserve_source_filename": episode.get("preserve_source_filename", False),
            "is_special": episode.get("is_special", False),
            "destination_group": episode.get("destination_group"),
            "special_label": episode.get("special_label"),
            "reviewed": episode.get("reviewed", False),
            "confidence": episode.get("confidence"),
            "subtitle_count": episode.get("subtitle_count", 0),
        })
        ingest_file.metadata_json = existing
    return unmatched


def _episode_key(episode: dict) -> tuple[str, str]:
    return (
        str(episode.get("source_file") or "").casefold(),
        str(episode.get("relative_source") or "").casefold(),
    )


def _apply_patch_to_episode(episode: dict, patch) -> dict:
    episode["include"] = bool(patch.include)
    episode["preserve_source_filename"] = bool(patch.preserve_source_filename)
    episode["is_special"] = bool(patch.is_special)
    episode["destination_group"] = patch.destination_group

    if patch.season_number is not None:
        episode["season_number"] = int(patch.season_number)

    if patch.episode_number is not None:
        episode["episode_number"] = int(patch.episode_number)

    if patch.episode_title is not None:
        episode["episode_title"] = patch.episode_title.strip() or None

    if patch.special_label is not None:
        episode["special_label"] = patch.special_label.strip() or None

    episode["episode_code"] = _rebuild_episode_code(
        episode.get("season_number"),
        episode.get("episode_number"),
        episode.get("is_special", False),
        episode.get("special_label"),
    )
    episode["reviewed"] = True
    episode["confidence"] = max(float(episode.get("confidence") or 0), 0.95)
    return episode


def _rebuild_episode_code(
    season_number,
    episode_number,
    is_special: bool = False,
    special_label: str | None = None,
) -> str | None:
    if is_special:
        label = (special_label or "").strip()
        return label or None
    if season_number is None or episode_number is None:
        return None
    return f"S{int(season_number):02d}E{int(episode_number):02d}"


def apply_tv_episode_review_patches(
    metadata: dict,
    ingest_files: list,
    patches: list[TvEpisodeReviewPatch],
) -> tuple[dict, list[dict]]:
    metadata = dict(metadata or {})

    patch_by_key: dict[tuple[str, str], TvEpisodeReviewPatch] = {}
    for patch in patches:
        key = (
            str(patch.source_file or "").casefold(),
            str(patch.relative_source or "").casefold(),
        )
        patch_by_key[key] = patch

    all_episodes: list[dict] = []
    for season in metadata.get("seasons", []):
        season = dict(season)
        for episode in season.get("episodes", []):
            episode = dict(episode)
            key = _episode_key(episode)
            patch = patch_by_key.get(key)

            if patch:
                episode = _apply_patch_to_episode(episode, patch)

            if episode.get("include", True):
                all_episodes.append(episode)

    special_episodes = list(metadata.get("special_episodes", []))
    for i, special in enumerate(special_episodes):
        key = _episode_key(special)
        patch = patch_by_key.get(key)
        if patch:
            special_episodes[i] = _apply_patch_to_episode(dict(special), patch)

    unresolved = list(metadata.get("unresolved_video_files", []))
    for i, item in enumerate(unresolved):
        key = _episode_key(item)
        patch = patch_by_key.get(key)
        if patch:
            item = dict(item)
            item["include"] = bool(patch.include)
            item["reviewed"] = True
            if patch.destination_group is not None:
                item["destination_group"] = patch.destination_group
            unresolved[i] = item

    seasons_by_number: dict = defaultdict(list)
    for episode in all_episodes:
        season_number = episode.get("season_number")
        if season_number is None:
            dest_group = episode.get("destination_group")
            if dest_group in {"specials", "oad", "extras"}:
                season_number = 0
        seasons_by_number[season_number].append(episode)

    rebuilt_seasons = []
    for season_number, episodes in sorted(
        seasons_by_number.items(),
        key=lambda pair: (pair[0] is None, pair[0] or 9999),
    ):
        if season_number is None:
            rebuilt_seasons.append({
                "season_number": None,
                "episode_count": len(episodes),
                "episodes": episodes,
            })
        else:
            rebuilt_seasons.append({
                "season_number": int(season_number),
                "episode_count": len(episodes),
                "episodes": sorted(
                    episodes,
                    key=lambda e: (
                        int(e.get("season_number") or 999),
                        int(e.get("episode_number") or 9999),
                        str(e.get("special_label") or ""),
                        str(e.get("source_file") or ""),
                    ),
                ),
            })

    metadata["seasons"] = rebuilt_seasons
    metadata["season_count"] = len(
        [s for s in rebuilt_seasons if s.get("season_number") is not None]
    )
    metadata["episode_count"] = sum(s.get("episode_count", 0) for s in rebuilt_seasons)
    metadata["video_file_count"] = (
        metadata["episode_count"]
        + sum(1 for s in special_episodes if s.get("include", True))
    )
    metadata["special_episodes"] = special_episodes
    metadata["special_episode_count"] = len(special_episodes)
    metadata["unresolved_video_files"] = [
        u for u in unresolved if u.get("include", True)
    ]
    metadata["unresolved_video_count"] = len(metadata["unresolved_video_files"])

    reviewed_episodes = list(all_episodes)
    for s in special_episodes:
        if s.get("include", True):
            reviewed_episodes.append(dict(s))

    return metadata, reviewed_episodes
