"""Bounded reset safety checks.

This script proves dev reset preserves real media in _INGEST and moves
restore-collision media to _RECOVERY instead of deleting it.
"""

from __future__ import annotations

import faulthandler
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
REAL_DATA_ROOT = ROOT / "data"
CHILD_ENV = "ARCHIVE_ASSISTANT_RESET_SAFETY_CHECK_CHILD"
TIMEOUT_SECONDS = 45
TEMP_ROOTS = [Path(r"C:\tmp"), ROOT / ".tmp"]
settings = None
Base = None
IngestBatch = None
MoveAction = None
reset_test_data = None
create_engine = None
sessionmaker = None


def cleanup_old_temp_folders() -> None:
    for tmp_root in TEMP_ROOTS:
        if not tmp_root.exists():
            continue
        for path in tmp_root.glob("archive-reset-safety-*"):
            if path.is_dir():
                shutil.rmtree(path, ignore_errors=True)


def make_temp_root(prefix: str) -> Path:
    denied_roots = []
    for tmp_root in TEMP_ROOTS:
        try:
            tmp_root.mkdir(parents=True, exist_ok=True)
        except PermissionError:
            denied_roots.append(tmp_root)
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
                denied_roots.append(tmp_root)
                break
    raise RuntimeError(
        "Could not create temp folder under "
        + ", ".join(str(root) for root in TEMP_ROOTS)
        + f"; permission denied for: {', '.join(str(root) for root in denied_roots)}"
    )


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
    assert settings.data_root.resolve() == root.resolve()
    assert settings.ingest_root.resolve() == (root / "_INGEST").resolve()
    assert settings.data_root.resolve() != REAL_DATA_ROOT.resolve()
    return original


def make_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    return sessionmaker(bind=engine)()


def test_loose_ingest_media_is_preserved(root: Path) -> None:
    print("check: reset safety preserve ingest", flush=True)
    db = make_session()
    try:
        loose = settings.ingest_root / "loose-real-file.mkv"
        loose.parent.mkdir(parents=True, exist_ok=True)
        loose.write_bytes(b"real ingest media")

        summary = reset_test_data(db, apply=True)

        assert summary.status == "ok"
        assert summary.recovered_media_files == 0
        assert loose.exists()
        assert loose.read_bytes() == b"real ingest media"
        assert not list((root / "_RECOVERY").glob("reset-*")) if (root / "_RECOVERY").exists() else True
    finally:
        db.close()


def test_restore_collision_goes_to_recovery(root: Path) -> None:
    print("check: reset safety restore collision", flush=True)
    db = make_session()
    try:
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
    finally:
        db.close()


def test_orphan_tv_library_restores_to_sidecar_ingest_folder(root: Path) -> None:
    print("check: orphan TV library restores to sidecar ingest folder", flush=True)
    db = make_session()
    try:
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
    finally:
        db.close()


def load_app_modules() -> None:
    global Base
    global IngestBatch
    global MoveAction
    global create_engine
    global reset_test_data
    global sessionmaker
    global settings

    print("check: before imports", flush=True)
    faulthandler.enable()
    faulthandler.dump_traceback_later(15, repeat=False)
    os.environ["DEBUG"] = "true"
    sys.path.insert(0, str(ROOT / "backend"))

    from sqlalchemy import create_engine as imported_create_engine
    from sqlalchemy.orm import sessionmaker as imported_sessionmaker

    from app.core.config import settings as imported_settings
    from app.db.session import Base as imported_base
    from app.models.archive import (
        IngestBatch as ImportedIngestBatch,
        MoveAction as ImportedMoveAction,
    )
    from app.services.dev_reset import reset_test_data as imported_reset_test_data

    Base = imported_base
    IngestBatch = ImportedIngestBatch
    MoveAction = ImportedMoveAction
    create_engine = imported_create_engine
    reset_test_data = imported_reset_test_data
    sessionmaker = imported_sessionmaker
    settings = imported_settings
    print("check: after imports", flush=True)


def run_checks() -> int:
    load_app_modules()
    cleanup_old_temp_folders()
    checks = [
        test_loose_ingest_media_is_preserved,
        test_restore_collision_goes_to_recovery,
        test_orphan_tv_library_restores_to_sidecar_ingest_folder,
    ]
    for check in checks:
        print("check: before temp root setup", flush=True)
        print("check: setup temp root", flush=True)
        root = make_temp_root("archive-reset-safety-")
        print(f"reset safety temp: {root}", flush=True)
        original = configure(root)
        original_guard = os.environ.get("ARCHIVE_ASSISTANT_RESET_TEST_ROOT")
        os.environ["ARCHIVE_ASSISTANT_RESET_TEST_ROOT"] = str(root)
        try:
            check(root)
        finally:
            print("check: before cleanup", flush=True)
            print("check: cleanup temp root", flush=True)
            for key, value in original.items():
                setattr(settings, key, value)
            if original_guard is None:
                os.environ.pop("ARCHIVE_ASSISTANT_RESET_TEST_ROOT", None)
            else:
                os.environ["ARCHIVE_ASSISTANT_RESET_TEST_ROOT"] = original_guard
            shutil.rmtree(root, ignore_errors=True)
            print("check: after cleanup", flush=True)
    print("reset safety checks passed")
    faulthandler.cancel_dump_traceback_later()
    return 0


def main() -> int:
    if os.environ.get(CHILD_ENV) == "1":
        return run_checks()

    env = {**os.environ, CHILD_ENV: "1"}
    try:
        completed = subprocess.run(
            [sys.executable, str(Path(__file__).resolve())],
            cwd=ROOT,
            env=env,
            text=True,
            capture_output=True,
            timeout=TIMEOUT_SECONDS,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        if exc.stdout:
            print(exc.stdout, end="")
        if exc.stderr:
            print(exc.stderr, end="", file=sys.stderr)
        print(
            f"FAIL check_reset_safety.py timed out after {TIMEOUT_SECONDS}s",
            flush=True,
        )
        return 124

    if completed.stdout:
        print(completed.stdout, end="")
    if completed.stderr:
        print(completed.stderr, end="", file=sys.stderr)
    return completed.returncode


if __name__ == "__main__":
    raise SystemExit(main())
