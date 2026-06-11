#!/usr/bin/env python3
"""Regression checks for precise stale quarantine repair."""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = PROJECT_ROOT / "backend"
sys.path.insert(0, str(BACKEND_ROOT))

from app.db.session import Base
from app.models.archive import IngestBatch
from app.services import scanner


def _touch(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"x")


def _batch(path: Path, detected_type: str = "unknown_type") -> IngestBatch:
    return IngestBatch(
        source_path=str(path),
        detected_type=detected_type,
        status="needs_quarantine_review",
        confidence=0.0,
        metadata_json={"name": path.name},
    )


def run() -> None:
    failures: list[str] = []
    temp_root = Path(r"C:\tmp")
    temp_root.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(
        prefix="archive-stale-quarantine-",
        dir=temp_root,
    ) as temporary:
        root = Path(temporary)
        music = root / "Kendrick Lamar - Mr Morale"
        tv = root / "Shingeki no Kyojin [10bits x265]"
        movie = root / "Black Panther (2018) [BluRay]"
        empty = root / "Already Moved Empty Folder"
        missing = root / "Missing Source"
        active_unknown = root / "Keep Unknown Folder"

        _touch(music / "01 - Track.mp3")
        _touch(tv / "Season 01" / "S01E01.mkv")
        _touch(movie / "Black.Panther.2018.mkv")
        empty.mkdir(parents=True)
        active_unknown.mkdir(parents=True)
        _touch(active_unknown / "notes.pdf")

        engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(engine)
        session = sessionmaker(bind=engine)()
        rows = [
            _batch(music),
            _batch(tv),
            _batch(movie),
            _batch(empty),
            _batch(missing),
            _batch(active_unknown),
            IngestBatch(
                source_path=str(music),
                detected_type="music_album",
                status="pending_review",
                confidence=0.8,
                metadata_json={"album": "Mr Morale"},
            ),
        ]
        session.add_all(rows)
        session.commit()

        classifications = {
            music: "music_album",
            tv: "video_tv_show",
            movie: "video_movie",
            empty: "unknown_type",
            active_unknown: "unknown_type",
        }

        original_tv = scanner._create_tv_batch
        original_movie = scanner._create_movie_batch
        scanner._create_tv_batch = lambda db, source: None
        scanner._create_movie_batch = lambda db, source: None
        try:
            scanner.repair_stale_media_batches(session, classifications)
        finally:
            scanner._create_tv_batch = original_tv
            scanner._create_movie_batch = original_movie

        quarantine_rows = {
            Path(row.source_path).name: row
            for row in session.query(IngestBatch).all()
            if row.detected_type in scanner.QUARANTINE_TYPES
        }
        for name in [
            music.name,
            tv.name,
            movie.name,
            empty.name,
            missing.name,
        ]:
            row = quarantine_rows[name]
            if row.status != "merged":
                failures.append(
                    f"Expected stale quarantine row {name!r} to merge; "
                    f"got {row.status!r}"
                )
            if not (row.metadata_json or {}).get("stale_quarantine_merged"):
                failures.append(f"Missing stale merge metadata for {name!r}")

        if quarantine_rows[active_unknown.name].status == "merged":
            failures.append("Existing unknown folder with real files was hidden")

        recognized = (
            session.query(IngestBatch)
            .filter(IngestBatch.detected_type == "music_album")
            .one()
        )
        if recognized.status != "pending_review":
            failures.append("Recognized music row was incorrectly merged")

        if scanner._is_empty_source_leftover(music):
            failures.append("Music folder was incorrectly considered empty")
        if not scanner._has_supported_audio_or_video(music):
            failures.append("MP3 folder was not recognized as supported media")
        if scanner._is_empty_source_leftover(tv):
            failures.append("TV folder was incorrectly considered empty")
        if not scanner._has_supported_audio_or_video(tv):
            failures.append("MKV folder was not recognized as supported media")
        if not scanner._is_empty_source_leftover(empty):
            failures.append("Zero-file source folder was not considered empty")

        session.close()
        engine.dispose()

    if failures:
        print("FAIL - stale quarantine repair regression")
        for failure in failures:
            print("  x", failure)
        raise SystemExit(1)

    print("PASS - stale quarantine repair is precise")


if __name__ == "__main__":
    run()
