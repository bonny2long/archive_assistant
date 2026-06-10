from collections import defaultdict
from app.schemas.archive import TvEpisodeReviewPatch


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
) -> dict:
    metadata = dict(metadata or {})

    patch_by_key: dict[tuple[str, str], TvEpisodeReviewPatch] = {}
    for patch in patches:
        key = (
            str(patch.source_file or "").casefold(),
            str(patch.relative_source or "").casefold(),
        )
        patch_by_key[key] = patch

    # ── Apply patches to normal episodes (seasons[n].episodes) ──
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

    # ── Apply patches to special episodes ──
    special_episodes = list(metadata.get("special_episodes", []))
    for i, special in enumerate(special_episodes):
        key = _episode_key(special)
        patch = patch_by_key.get(key)
        if patch:
            special_episodes[i] = _apply_patch_to_episode(dict(special), patch)

    # ── Apply patches to unresolved video files ──
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

    # Re-bucket episodes by season_number (patches may have changed it)
    seasons_by_number: dict = defaultdict(list)
    for episode in all_episodes:
        season_number = episode.get("season_number")
        if season_number is None:
            dest_group = episode.get("destination_group")
            if dest_group in {"specials", "oad", "extras"}:
                season_number = 0  # group under specials bucket
        seasons_by_number[season_number].append(episode)

    rebuilt_seasons = []
    for season_number, episodes in sorted(
        seasons_by_number.items(),
        key=lambda pair: (pair[0] is None, pair[0] or 9999),
    ):
        if season_number is None:
            # Unresolved — keep so review_state can still block it
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
    # Total video count = normal + specials (unresolved excluded from count)
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

    return metadata
