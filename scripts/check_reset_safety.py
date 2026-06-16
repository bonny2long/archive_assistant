"""Bounded reset safety checks.

This script proves dev reset preserves real media in _INGEST and moves
restore-collision media to _RECOVERY instead of deleting it.
"""

from __future__ import annotations

import os
import sys
import tempfile
import shutil
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker


ROOT = Path(__file__).resolve().parents[1]
os.environ["DEBUG"] = "true"
sys.path.insert(0, str(ROOT / "backend"))

from app.core.config import settings  # noqa: E402
from app.db.session import Base  # noqa: E402
from app.models.archive import IngestBatch, MoveAction  # noqa: E402
from app.services.dev_reset import reset_test_data  # noqa: E402


def configure(root: Path) -> dict:
    original = {
        "data_root": settings.data_root,
        "ingest_root": settings.ingest_root,
        "reports_dir": settings.reports_dir,
        "music_flac_dir": settings.music_flac_dir,
        "music_mp3_dir": settings.music_mp3_dir,
        "music_discographies_dir": settings.music_discographies_dir,
        "music_metadata_dir": settings.music_metadata_dir,
        "movies_dir": settings.movies_dir,
        "movies_metadata_dir": settings.movies_metadata_dir,
        "tv_dir": settings.tv_dir,
        "tv_metadata_dir": settings.tv_metadata_dir,
        "books_dir": settings.books_dir,
        "books_metadata_dir": settings.books_metadata_dir,
        "audiobooks_dir": settings.audiobooks_dir,
        "audiobooks_metadata_dir": settings.audiobooks_metadata_dir,
        "quarantine_discography_dir": settings.quarantine_discography_dir,
        "quarantine_unknown_dir": settings.quarantine_unknown_dir,
        "quarantine_unsupported_dir": settings.quarantine_unsupported_dir,
        "quarantine_reports_dir": settings.quarantine_reports_dir,
    }
    settings.data_root = root
    settings.ingest_root = root / "_INGEST"
    settings.reports_dir = root / "_REPORTS" / "ingest-reports"
    settings.music_flac_dir = root / "Music" / "Library" / "FLAC"
    settings.music_mp3_dir = root / "Music" / "Library" / "MP3"
    settings.music_discographies_dir = root / "Music" / "Discographies"
    settings.music_metadata_dir = root / "Music" / "Metadata"
    settings.movies_dir = root / "Movies" / "Library"
    settings.movies_metadata_dir = root / "Movies" / "Metadata"
    settings.tv_dir = root / "TV" / "Library"
    settings.tv_metadata_dir = root / "TV" / "Metadata"
    settings.books_dir = root / "Books"
    settings.books_metadata_dir = root / "Books" / "Metadata"
    settings.audiobooks_dir = root / "Audiobooks" / "Library"
    settings.audiobooks_metadata_dir = root / "Audiobooks" / "Metadata"
    settings.quarantine_discography_dir = root / "_QUARANTINE" / "music" / "discography-excluded"
    settings.quarantine_unknown_dir = root / "_QUARANTINE" / "unknown-type"
    settings.quarantine_unsupported_dir = root / "_QUARANTINE" / "unsupported-file"
    settings.quarantine_reports_dir = root / "_REPORTS" / "quarantine-reports"
    return original


def make_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    return sessionmaker(bind=engine)()


def test_loose_ingest_media_is_preserved(root: Path) -> None:
    print("check: loose ingest media is preserved", flush=True)
    db = make_session()
    loose = settings.ingest_root / "loose-real-file.mkv"
    loose.parent.mkdir(parents=True, exist_ok=True)
    loose.write_bytes(b"real ingest media")

    summary = reset_test_data(db, apply=True)

    assert summary.status == "ok"
    assert summary.recovered_media_files == 0
    assert loose.exists()
    assert loose.read_bytes() == b"real ingest media"
    assert not list((root / "_RECOVERY").glob("reset-*")) if (root / "_RECOVERY").exists() else True
    db.close()


def test_restore_collision_goes_to_recovery(root: Path) -> None:
    print("check: restore collision goes to recovery", flush=True)
    db = make_session()
    source = settings.ingest_root / "Rick and Morty - S06E01.mkv"
    destination = settings.tv_dir / "Rick and Morty" / "Season 06" / source.name
    source.parent.mkdir(parents=True, exist_ok=True)
    destination.parent.mkdir(parents=True, exist_ok=True)
    source.write_bytes(b"existing user ingest media")
    destination.write_bytes(b"tracked moved media")

    batch = IngestBatch(
        source_kind="manual-drop",
        source_path=str(source),
        detected_type="video_tv_show",
        status="moved",
        confidence=1.0,
        suggested_destination=str(destination.parent.parent),
        metadata_json={"show_title": "Rick and Morty"},
        metadata_confirmed=True,
    )
    db.add(batch)
    db.flush()
    db.add(MoveAction(
        batch_id=batch.id,
        source_path=str(source),
        destination_path=str(destination),
        status="completed",
    ))
    db.commit()

    summary = reset_test_data(db, apply=True)

    assert summary.status == "ok"
    assert summary.recovered_media_files == 1
    assert source.exists()
    assert source.read_bytes() == b"tracked moved media"
    recovered = list((root / "_RECOVERY").glob("reset-*/*.mkv"))
    assert len(recovered) == 1
    assert recovered[0].read_bytes() == b"existing user ingest media"
    assert not destination.exists()
    db.close()


def test_orphan_tv_library_restores_to_sidecar_ingest_folder(root: Path) -> None:
    print("check: orphan TV library restores to sidecar ingest folder", flush=True)
    db = make_session()
    ingest_folder = settings.ingest_root / "Severance Season 1 Mp4 1080p"
    sidecar = ingest_folder / "Read Me.txt"
    library_file = (
        settings.tv_dir
        / "Severance"
        / "Season 01"
        / "S01E01.mp4"
    )
    sidecar.parent.mkdir(parents=True, exist_ok=True)
    library_file.parent.mkdir(parents=True, exist_ok=True)
    sidecar.write_text("release note", encoding="utf-8")
    library_file.write_bytes(b"orphan tv media")

    summary = reset_test_data(db, apply=True)

    restored = ingest_folder / "Season 01" / "S01E01.mp4"
    assert summary.status == "ok"
    assert summary.restored_files == 1
    assert restored.exists()
    assert restored.read_bytes() == b"orphan tv media"
    assert sidecar.exists()
    assert sidecar.read_text(encoding="utf-8") == "release note"
    assert not library_file.exists()
    db.close()


def main() -> None:
    Path(r"C:\tmp").mkdir(parents=True, exist_ok=True)
    checks = [
        test_loose_ingest_media_is_preserved,
        test_restore_collision_goes_to_recovery,
        test_orphan_tv_library_restores_to_sidecar_ingest_folder,
    ]
    for check in checks:
        root = Path(
            tempfile.mkdtemp(prefix="archive-reset-safety-", dir=r"C:\tmp")
        )
        original = configure(root)
        try:
            check(root)
        finally:
            for key, value in original.items():
                setattr(settings, key, value)
            shutil.rmtree(root, ignore_errors=True)
    print("reset safety checks passed")


if __name__ == "__main__":
    main()
