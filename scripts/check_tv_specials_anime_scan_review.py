"""Scan/review check for anime TV specials without approving or moving."""

from __future__ import annotations

import json
import os
import shutil
import sys
import time
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker


PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = PROJECT_ROOT / "backend"
TEMP_ROOTS = [Path(r"C:\tmp"), PROJECT_ROOT / ".tmp"]
os.environ["DEBUG"] = "true"
sys.path.insert(0, str(BACKEND_ROOT))

from app.core.config import settings  # noqa: E402
from app.db.session import Base  # noqa: E402
from app.models.archive import IngestFile  # noqa: E402
from app.services.scanner import scan_music_ingest  # noqa: E402


def make_temp_root(prefix: str) -> Path:
    for tmp_root in TEMP_ROOTS:
        try:
            tmp_root.mkdir(parents=True, exist_ok=True)
        except PermissionError:
            continue
        for attempt in range(100):
            candidate = (
                tmp_root
                / f"{prefix}{os.getpid()}-{time.monotonic_ns()}-{attempt}"
            )
            try:
                candidate.mkdir()
                return candidate
            except FileExistsError:
                continue
            except PermissionError:
                break
    raise RuntimeError("Could not create temp folder")


def configure(root: Path) -> dict:
    original = {
        "data_root": settings.data_root,
        "ingest_root": settings.ingest_root,
        "reports_dir": settings.reports_dir,
        "tv_dir": settings.tv_dir,
        "tv_metadata_dir": settings.tv_metadata_dir,
    }
    settings.data_root = root / "data"
    settings.ingest_root = settings.data_root / "_INGEST"
    settings.reports_dir = settings.data_root / "_REPORTS" / "ingest-reports"
    settings.tv_dir = settings.data_root / "TV" / "Library"
    settings.tv_metadata_dir = settings.data_root / "TV" / "Metadata"
    return original


def make_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    return sessionmaker(bind=engine)()


def write_video(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"non-zero test video fixture")


def blocker_types(metadata: dict) -> set[str]:
    return {
        str(item.get("type"))
        for item in metadata.get("blocking_review_items", [])
        if isinstance(item, dict)
    }


def main() -> int:
    root = make_temp_root("archive-tv-specials-review-")
    original = configure(root)
    db = make_session()
    try:
        source = settings.ingest_root / "Shingeki no Kyojin"
        write_video(
            source
            / "Season 04"
            / "Shingeki no Kyojin - S04E01 - The Other Side of the Sea.mkv"
        )
        write_video(
            source
            / "Season 04"
            / "Shingeki no Kyojin - S04E02 - Midnight Train.mkv"
        )
        write_video(
            source
            / "Specials"
            / (
                "Shingeki no Kyojin - The Final Season - S04P03 - "
                "THE FINAL CHAPTERS - Special 1.mkv"
            )
        )
        write_video(
            source
            / "Specials"
            / (
                "Shingeki no Kyojin - The Final Season - S04P04 - "
                "THE FINAL CHAPTERS - Special 2.mkv"
            )
        )
        write_video(source / "Specials" / "Shingeki no Kyojin - S01E13.5.mkv")
        write_video(
            source
            / "Specials"
            / "Shingeki no Kyojin - OAD 01 - Ilse's Notebook.mkv"
        )
        write_video(
            source
            / "Specials"
            / "Shingeki no Kyojin - OVA 02 - Lost Girls.mkv"
        )
        write_video(
            source
            / "Specials"
            / "Shingeki no Kyojin - OAV 03 - No Regrets.mkv"
        )

        result = scan_music_ingest(db)
        batches = [
            batch for batch in result.batches
            if batch.detected_type == "video_tv_show"
        ]
        assert len(batches) == 1
        batch = batches[0]
        metadata = batch.metadata_json or {}
        special_labels = {
            item.get("source_file"): {
                "special_label": item.get("special_label"),
                "destination_group": item.get("destination_group"),
            }
            for item in metadata.get("special_episodes", [])
        }
        blockers = blocker_types(metadata)

        assert metadata["show_title"] == "Shingeki no Kyojin"
        assert metadata["episode_count"] == 2
        assert metadata["special_episode_count"] == 6
        assert metadata["video_file_count"] == (
            metadata["episode_count"] + metadata["special_episode_count"]
        )
        assert metadata["unresolved_video_count"] == 0
        assert len(metadata["special_episodes"]) == 6
        assert blockers == set()
        assert "tv_review_count_mismatch" not in blockers
        item_titles = [
            item.get("show_title")
            for season in metadata.get("seasons", [])
            for item in season.get("episodes", [])
        ] + [
            item.get("show_title")
            for item in metadata.get("special_episodes", [])
        ]
        file_rows = (
            db.query(IngestFile)
            .filter(IngestFile.batch_id == batch.id)
            .order_by(IngestFile.file_name.asc())
            .all()
        )
        file_titles = [
            (row.metadata_json or {}).get("show_title")
            for row in file_rows
            if row.detected_role == "tv_episode"
        ]
        assert item_titles
        assert all(title == "Shingeki no Kyojin" for title in item_titles)
        assert len(file_titles) == metadata["video_file_count"]
        assert all(title == "Shingeki no Kyojin" for title in file_titles)
        assert special_labels[
            "Shingeki no Kyojin - The Final Season - S04P03 - "
            "THE FINAL CHAPTERS - Special 1.mkv"
        ] == {
            "special_label": "Special 1",
            "destination_group": "specials",
        }
        assert special_labels[
            "Shingeki no Kyojin - The Final Season - S04P04 - "
            "THE FINAL CHAPTERS - Special 2.mkv"
        ] == {
            "special_label": "Special 2",
            "destination_group": "specials",
        }
        assert special_labels["Shingeki no Kyojin - S01E13.5.mkv"] == {
            "special_label": "S01E13.5",
            "destination_group": "specials",
        }
        assert special_labels[
            "Shingeki no Kyojin - OAD 01 - Ilse's Notebook.mkv"
        ] == {
            "special_label": "OAD01",
            "destination_group": "oad",
        }
        assert special_labels[
            "Shingeki no Kyojin - OVA 02 - Lost Girls.mkv"
        ] == {
            "special_label": "OVA02",
            "destination_group": "ova",
        }
        assert special_labels[
            "Shingeki no Kyojin - OAV 03 - No Regrets.mkv"
        ] == {
            "special_label": "OVA03",
            "destination_group": "ova",
        }

        print(json.dumps(metadata, indent=2, sort_keys=True))
        print("TV specials anime scan/review checks passed")
        return 0
    finally:
        db.close()
        for key, value in original.items():
            setattr(settings, key, value)
        shutil.rmtree(root, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
