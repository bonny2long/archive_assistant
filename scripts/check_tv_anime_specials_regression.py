"""Permanent Shingeki-style TV anime specials regression check.

Creates tiny non-zero .mkv fixtures in a temp ingest root, scans only, and
asserts TV parsing/review metadata. This script does not approve or move.
"""

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
EXPECTED_TITLE = "Shingeki no Kyojin"
os.environ["DEBUG"] = "true"
sys.path.insert(0, str(BACKEND_ROOT))

from app.core.config import settings  # noqa: E402
from app.db.session import Base  # noqa: E402
from app.models.archive import IngestBatch, IngestFile  # noqa: E402
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
    path.write_bytes(b"tiny non-zero mkv fixture")


def write_numbered_episodes(source: Path) -> None:
    season_counts = {
        1: 25,
        2: 12,
        3: 22,
        4: 27,
    }
    for season_number, episode_count in season_counts.items():
        for episode_number in range(1, episode_count + 1):
            write_video(
                source
                / f"Season {season_number:02d}"
                / (
                    f"{EXPECTED_TITLE} - "
                    f"S{season_number:02d}E{episode_number:02d} - "
                    f"Episode {episode_number:02d}.mkv"
                )
            )


def write_specials(source: Path) -> None:
    oad_specials = [
        "Shingeki no Kyojin - OADE01 - Ilse's Notebook.mkv",
        "Shingeki no Kyojin - OADE02 - A Sudden Visitor.mkv",
        "Shingeki no Kyojin - OADE03 - Distress.mkv",
        "Shingeki no Kyojin - OADE04 - No Regrets Part 1.mkv",
        "Shingeki no Kyojin - OADE05 - No Regrets Part 2.mkv",
        "Shingeki no Kyojin - OADE06 - Lost Girls Wall Sina.mkv",
        "Shingeki no Kyojin - OVA 01 - Lost Girls.mkv",
        "Shingeki no Kyojin - OAV 02 - No Regrets.mkv",
    ]
    for name in oad_specials:
        write_video(source / "OADs" / name)

    write_video(
        source
        / "Season 01"
        / "Shingeki no Kyojin - S01E13.5 - Since That Day.mkv"
    )

    final_chapters = [
        (
            "Shingeki no Kyojin - The Final Season - S04P03 - "
            "THE FINAL CHAPTERS - Special 1.mkv"
        ),
        (
            "Shingeki no Kyojin - The Final Season - S04P04 - "
            "THE FINAL CHAPTERS - Special 2.mkv"
        ),
    ]
    for name in final_chapters:
        write_video(source / "The Final Season - Season 4" / name)


def blocker_types(metadata: dict) -> set[str]:
    return {
        str(item.get("type"))
        for item in metadata.get("blocking_review_items", [])
        if isinstance(item, dict)
    }


def all_item_titles(metadata: dict) -> list[str | None]:
    return [
        item.get("show_title")
        for season in metadata.get("seasons", [])
        for item in season.get("episodes", [])
    ] + [
        item.get("show_title")
        for item in metadata.get("special_episodes", [])
    ]


def main() -> int:
    root = make_temp_root("archive-tv-anime-specials-")
    original = configure(root)
    db = make_session()
    try:
        source = settings.ingest_root / "Shingeki no Kyojin [10bits x265]"
        write_numbered_episodes(source)
        write_specials(source)

        result = scan_music_ingest(db)
        tv_batches = [
            batch for batch in result.batches
            if batch.detected_type == "video_tv_show"
        ]
        assert len(tv_batches) == 1
        batch = tv_batches[0]
        metadata = batch.metadata_json or {}
        blockers = blocker_types(metadata)
        specials_by_file = {
            item.get("source_file"): item
            for item in metadata.get("special_episodes", [])
        }
        file_rows = (
            db.query(IngestFile)
            .filter(IngestFile.batch_id == batch.id)
            .order_by(IngestFile.file_name.asc())
            .all()
        )
        video_file_rows = [
            row for row in file_rows
            if row.detected_role == "tv_episode"
        ]
        quarantine_rows = (
            db.query(IngestBatch)
            .filter(IngestBatch.detected_type.in_([
                "unknown_type",
                "unsupported_file",
            ]))
            .all()
        )

        assert batch.detected_type == "video_tv_show"
        assert metadata["show_title"] == EXPECTED_TITLE
        assert metadata["episode_count"] == 86
        assert metadata["special_episode_count"] == 11
        assert metadata["video_file_count"] == 97
        assert metadata["unresolved_video_count"] == 0
        assert metadata["blocking_review_items"] == []
        assert metadata["metadata_warnings"] == []
        assert "tv_review_count_mismatch" not in blockers
        assert quarantine_rows == []
        assert len(video_file_rows) == 97
        assert all(title == EXPECTED_TITLE for title in all_item_titles(metadata))
        assert all(
            (row.metadata_json or {}).get("show_title") == EXPECTED_TITLE
            for row in video_file_rows
        )

        oad_items = [
            item for item in metadata["special_episodes"]
            if str(item.get("special_label") or "").startswith("OAD")
        ]
        assert len(oad_items) == 6
        assert all(item.get("destination_group") == "oad" for item in oad_items)

        ova_oav_items = [
            item for item in metadata["special_episodes"]
            if str(item.get("source_file") or "").startswith((
                "Shingeki no Kyojin - OVA",
                "Shingeki no Kyojin - OAV",
            ))
        ]
        assert len(ova_oav_items) == 2
        assert all(item.get("is_special") is True for item in ova_oav_items)
        assert all(
            item.get("destination_group") in {"oad", "specials", "ova"}
            for item in ova_oav_items
        )

        s01e135 = next(
            item for item in metadata["special_episodes"]
            if item.get("episode_code") == "S01E13.5"
        )
        assert s01e135["destination_group"] == "specials"
        final_1 = (
            "Shingeki no Kyojin - The Final Season - S04P03 - "
            "THE FINAL CHAPTERS - Special 1.mkv"
        )
        final_2 = (
            "Shingeki no Kyojin - The Final Season - S04P04 - "
            "THE FINAL CHAPTERS - Special 2.mkv"
        )
        assert specials_by_file[final_1]["special_label"] == "Special 1"
        assert specials_by_file[final_1]["destination_group"] == "specials"
        assert specials_by_file[final_2]["special_label"] == "Special 2"
        assert specials_by_file[final_2]["destination_group"] == "specials"

        summary = {
            "batch_id": batch.id,
            "detected_type": batch.detected_type,
            "show_title": metadata["show_title"],
            "episode_count": metadata["episode_count"],
            "special_episode_count": metadata["special_episode_count"],
            "video_file_count": metadata["video_file_count"],
            "unresolved_video_count": metadata["unresolved_video_count"],
            "blocking_review_items": metadata["blocking_review_items"],
            "metadata_warnings": metadata["metadata_warnings"],
            "hydrated_video_file_rows": len(video_file_rows),
            "quarantine_rows": len(quarantine_rows),
            "final_chapters": {
                final_1: {
                    "special_label": specials_by_file[final_1]["special_label"],
                    "destination_group": specials_by_file[final_1][
                        "destination_group"
                    ],
                },
                final_2: {
                    "special_label": specials_by_file[final_2]["special_label"],
                    "destination_group": specials_by_file[final_2][
                        "destination_group"
                    ],
                },
            },
        }
        print(json.dumps(summary, indent=2, sort_keys=True))
        print("TV anime specials regression checks passed")
        return 0
    finally:
        db.close()
        for key, value in original.items():
            setattr(settings, key, value)
        shutil.rmtree(root, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
