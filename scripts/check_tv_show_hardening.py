"""Check TV subtitles, artwork, sidecars, and multi-season metadata."""

from __future__ import annotations

import sys
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace


PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = PROJECT_ROOT / "backend"
sys.path.insert(0, str(BACKEND_ROOT))

from app.services.mover import (  # noqa: E402
    _tv_artwork_destination,
    _tv_episode_destination,
    _tv_subtitle_destination,
)
from app.services.scanner import (  # noqa: E402
    _tv_artwork_metadata,
    _tv_batch_data,
)


def touch(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.touch()
    return path


def main() -> int:
    with TemporaryDirectory(dir=r"C:\tmp") as temp:
        temp_root = Path(temp)
        single = temp_root / "Rick and Morty - Season 6 (2022)"
        episode = touch(single / "Rick and Morty - S06E01 - Solaricks.mkv")
        touch(single / "Rick and Morty - S06E02 - Rick A Mort Well Lived.mkv")
        subtitle = touch(
            single / "Rick and Morty - S06E01 - Solaricks.en.srt"
        )
        poster = touch(single / "poster.jpg")
        season_art = touch(single / "season.jpg")
        touch(single / "tvshow.nfo")

        data = _tv_batch_data(single)
        assert data is not None
        metadata = data["metadata"]
        assert metadata["show_title"] == "Rick and Morty"
        assert metadata["season_count"] == 1
        assert metadata["episode_count"] == 2
        assert metadata["subtitle_count"] == 1
        assert metadata["artwork_count"] == 2
        assert metadata["ignored_sidecar_count"] == 1
        assert metadata["subtitles"][0]["episode_code"] == "S06E01"
        assert metadata["subtitles"][0]["language_suffix"] == ".en"

        show_art = _tv_artwork_metadata(poster, single, 6)
        season_art_metadata = _tv_artwork_metadata(
            season_art,
            single,
            6,
        )
        assert show_art["artwork_scope"] == "show"
        assert season_art_metadata == {
            "relative_source": "season.jpg",
            "artwork_scope": "season",
            "season_number": 6,
        }

        destination = temp_root / "TV" / "Library" / "Rick and Morty"
        episode_file = SimpleNamespace(
            file_name=episode.name,
            metadata_json=metadata["seasons"][0]["episodes"][0],
        )
        subtitle_file = SimpleNamespace(
            file_name=subtitle.name,
            metadata_json=metadata["subtitles"][0],
        )
        season_art_file = SimpleNamespace(
            file_name=season_art.name,
            file_path=str(season_art),
            metadata_json=season_art_metadata,
        )
        batch = SimpleNamespace(source_path=str(single))
        assert _tv_episode_destination(
            destination,
            episode_file,
        ).name == "S06E01 - Solaricks.mkv"
        assert _tv_subtitle_destination(
            destination,
            subtitle_file,
        ).name == "S06E01 - Solaricks.en.srt"
        assert _tv_artwork_destination(
            batch,
            destination,
            season_art_file,
        ) == destination / "Season 06" / "season.jpg"

        multi = temp_root / "Rick and Morty"
        touch(
            multi
            / "Season 06"
            / "Rick and Morty - S06E01 - Solaricks.mkv"
        )
        touch(
            multi
            / "Season 07"
            / "Rick and Morty - S07E01 - How Poopy Got His Poop Back.mkv"
        )
        multi_data = _tv_batch_data(multi)
        assert multi_data is not None
        assert multi_data["metadata"]["season_count"] == 2
        assert [
            season["season_number"]
            for season in multi_data["metadata"]["seasons"]
        ] == [6, 7]

    print("TV hardening checks passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
