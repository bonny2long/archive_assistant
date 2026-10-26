"""Isolated checks: Archive Assistant moves by rename only and never copies then deletes."""

from __future__ import annotations

import errno
import os
import shutil
import sys
from pathlib import Path
from uuid import uuid4

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

ROOT = Path(__file__).resolve().parents[1]
os.environ["DEBUG"] = "true"
sys.path.insert(0, str(ROOT / "backend"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from app.core.config import settings  # noqa: E402
from app.db.session import Base  # noqa: E402
from app.services import mover, safe_move  # noqa: E402
from app.services.safe_move import (  # noqa: E402
    CROSS_DEVICE_MESSAGE,
    CrossDeviceMoveError,
    device_of,
    move_by_rename,
    same_device,
)
from check_content_duplicate_guard import configure, race_album, restore  # noqa: E402


def check_rename_semantics(root: Path) -> None:
    source = root / "a" / "track.flac"
    source.parent.mkdir(parents=True)
    source.write_bytes(b"audio")
    destination = root / "b" / "track.flac"
    destination.parent.mkdir()
    move_by_rename(source, destination)
    assert destination.read_bytes() == b"audio" and not source.exists()

    # Nothing that already exists is ever replaced, on any operating system.
    other = root / "a" / "other.flac"
    other.write_bytes(b"other")
    try:
        move_by_rename(other, destination)
        raise AssertionError("an existing destination was replaced")
    except FileExistsError:
        pass
    assert destination.read_bytes() == b"audio" and other.read_bytes() == b"other"

    folder = root / "folder"
    (folder / "disc 1").mkdir(parents=True)
    (folder / "disc 1" / "01.flac").write_bytes(b"x")
    moved = root / "moved folder"
    move_by_rename(folder, moved)
    assert (moved / "disc 1" / "01.flac").read_bytes() == b"x" and not folder.exists()
    (root / "empty").mkdir()
    try:
        move_by_rename(root / "empty", moved)
        raise AssertionError("an existing folder was moved into or over")
    except FileExistsError:
        pass
    assert sorted(p.name for p in moved.iterdir()) == ["disc 1"]


def check_a_move_that_would_copy_fails_untouched(root: Path) -> None:
    source = root / "src" / "book.m4b"
    source.parent.mkdir(parents=True)
    source.write_bytes(b"precious")
    destination = root / "dst" / "book.m4b"
    destination.parent.mkdir()
    real_rename = safe_move.os.rename

    def refuse(_source, _destination):
        raise OSError(errno.EXDEV, "Invalid cross-device link")

    def refuse_windows(_source, _destination):
        error = OSError(errno.EINVAL, "The system cannot move the file to a different disk drive")
        error.winerror = 17
        raise error

    for failing in (refuse, refuse_windows):
        safe_move.os.rename = failing
        try:
            move_by_rename(source, destination)
            raise AssertionError("a cross-device move was allowed")
        except CrossDeviceMoveError as exc:
            assert "different filesystems" in str(exc) and isinstance(exc, OSError)
        finally:
            safe_move.os.rename = real_rename
        assert source.read_bytes() == b"precious" and not destination.exists()

    # Any other failure is passed on as it was, not relabelled.
    def denied(_source, _destination):
        raise PermissionError(errno.EACCES, "denied")

    safe_move.os.rename = denied
    try:
        move_by_rename(source, destination)
        raise AssertionError("a permission error was swallowed")
    except PermissionError:
        pass
    finally:
        safe_move.os.rename = real_rename


def check_device_helpers(root: Path) -> None:
    (root / "x").mkdir(parents=True)
    assert device_of(root / "x") == device_of(root)
    assert device_of(root / "x" / "not" / "yet" / "created") == device_of(root / "x")
    assert same_device(root / "x", root / "x" / "later")
    assert same_device(root, root / "does" / "not" / "exist")


def check_a_batch_on_another_filesystem_is_blocked_up_front(root: Path) -> None:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        batch = race_album(db, root, 0)
        check = preflight_one(db, batch.id)
        assert check["ready"], check

        real_device_of = mover.device_of
        library = settings.music_flac_dir.resolve()

        def pretend(path):
            # The ingest folder sits on filesystem 1, the library on filesystem 2.
            return 2 if library in Path(path).resolve().parents or Path(path).resolve() == library else 1

        mover.device_of = pretend
        try:
            blocked = preflight_one(db, batch.id)
        finally:
            mover.device_of = real_device_of
        assert not blocked["ready"] and CROSS_DEVICE_MESSAGE in blocked["blockers"], blocked

        # If it were attempted anyway, every file fails the same way and none are copied or lost.
        real_rename = safe_move.os.rename

        def refuse(_source, _destination):
            raise OSError(errno.EXDEV, "Invalid cross-device link")

        safe_move.os.rename = refuse
        try:
            moved, errors = mover.move_approved_batches(db, [batch.id])
        finally:
            safe_move.os.rename = real_rename
        assert moved == 0, (moved, errors)
        assert len(list((root / "_INGEST" / "race-0").glob("*.flac"))) == 3
        assert not list(settings.music_flac_dir.rglob("*.flac"))
        db.refresh(batch)
        assert batch.status != "moved", batch.status


def preflight_one(db: Session, batch_id: int) -> dict:
    return mover.preflight_selected_batches(db, [batch_id])[0]


def main() -> int:
    root = ROOT / "data" / "_CHECKS" / f"rename-only-{uuid4().hex}"
    root.mkdir(parents=True, exist_ok=True)
    original = configure(root)
    try:
        check_rename_semantics(root / "unit-1")
        print("PASS moves are renames and never replace anything that exists")
        check_a_move_that_would_copy_fails_untouched(root / "unit-2")
        print("PASS a cross-filesystem move fails cleanly and leaves the source untouched")
        check_device_helpers(root / "unit-3")
        print("PASS filesystem detection works for paths that do not exist yet")
        check_a_batch_on_another_filesystem_is_blocked_up_front(root)
        print("PASS a batch whose destination is on another filesystem is blocked before anything moves")
    finally:
        restore(original)
        shutil.rmtree(root, ignore_errors=True)
    print("rename-only move checks passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
