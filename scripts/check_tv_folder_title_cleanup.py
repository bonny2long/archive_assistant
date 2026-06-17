"""Check TV folder title cleanup for generic restored episode names."""

from __future__ import annotations

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
from app.services.scanner import scan_music_ingest  # noqa: E402
from app.services.video_metadata import parse_tv_folder_name  # noqa: E402


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


def main() -> int:
    parsed = parse_tv_folder_name("Severance Season 1 Mp4 1080p")
    assert parsed["show_title"] == "Severance"

    root = make_temp_root("archive-tv-title-cleanup-")
    original = configure(root)
    db = make_session()
    try:
        source = settings.ingest_root / "Severance Season 1 Mp4 1080p"
        season = source / "Season 01"
        season.mkdir(parents=True, exist_ok=True)
        (source / "Read Me.txt").write_text("release note", encoding="utf-8")
        for episode in range(1, 10):
            (season / f"S01E{episode:02d}.mp4").write_bytes(b"episode")

        result = scan_music_ingest(db)
        batches = result.batches
        tv_batches = [
            batch for batch in batches
            if batch.detected_type == "video_tv_show"
        ]
        quarantine_batches = [
            batch for batch in batches
            if batch.detected_type in {"unknown_type", "unsupported_file"}
        ]

        assert len(tv_batches) == 1
        assert quarantine_batches == []

        batch = tv_batches[0]
        metadata = batch.metadata_json or {}
        assert metadata["show_title"] == "Severance"
        assert Path(batch.suggested_destination) == (
            settings.tv_dir / "Severance"
        )
        assert metadata["episode_count"] == 9
        assert metadata["video_file_count"] == 9
        assert metadata["season_count"] == 1
        assert metadata["special_episode_count"] == 0
        assert "tv_episode_titles_missing" in metadata["metadata_warnings"]
        assert not any(
            item.get("code") == "tv_episode_titles_missing"
            for item in metadata.get("blocking_review_items", [])
        )
        assert metadata["ignored_sidecar_count"] == 1
        assert metadata["ignored_sidecar_files"] == ["Read Me.txt"]

    finally:
        db.close()
        for key, value in original.items():
            setattr(settings, key, value)
        shutil.rmtree(root, ignore_errors=True)

    print("TV folder title cleanup checks passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
