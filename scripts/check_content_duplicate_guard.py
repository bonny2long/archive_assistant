"""Isolated checks: identical files never reach the library twice, and moves run one at a time."""

from __future__ import annotations

import os
import shutil
import sys
import threading
import time
from pathlib import Path
from uuid import uuid4

from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

ROOT = Path(__file__).resolve().parents[1]
os.environ["DEBUG"] = "true"
sys.path.insert(0, str(ROOT / "backend"))

from app.api.routes import (  # noqa: E402
    _execute_selected_move,
    approve_batch,
    approve_selected_batches,
    move_approved,
)
from app.core.config import settings  # noqa: E402
from app.db.session import Base  # noqa: E402
from app.models.archive import IngestBatch, IngestFile  # noqa: E402
from app.schemas.archive import BulkApproveRequest  # noqa: E402
from app.services import mover  # noqa: E402
from app.services.content_guard import (  # noqa: E402
    DUPLICATE_WARNING_TYPE,
    find_content_duplicates,
    refresh_duplicate_state,
)
from app.services.mover import (  # noqa: E402
    exclusive_move,
    move_approved_batches,
    preflight_selected_batches,
)
from app.services.review_state import build_review_state  # noqa: E402

SETTING_NAMES = (
    "data_root", "music_mp3_dir", "music_flac_dir", "music_metadata_dir",
    "movies_dir", "movies_metadata_dir", "tv_dir", "tv_metadata_dir",
    "audiobooks_dir", "audiobooks_metadata_dir", "books_dir", "books_metadata_dir",
)
GOLDEN = (b"golden-son-chapter-" * 20000)  # about 380 KB


def configure(root: Path) -> dict:
    original = {name: getattr(settings, name) for name in SETTING_NAMES}
    settings.data_root = root
    settings.music_mp3_dir = root / "Music" / "Library" / "MP3"
    settings.music_flac_dir = root / "Music" / "Library" / "FLAC"
    settings.music_metadata_dir = root / "Music" / "Metadata"
    settings.movies_dir = root / "Movies" / "Library"
    settings.movies_metadata_dir = root / "Movies" / "Metadata"
    settings.tv_dir = root / "TV" / "Library"
    settings.tv_metadata_dir = root / "TV" / "Metadata"
    settings.audiobooks_dir = root / "Audiobooks" / "Library"
    settings.audiobooks_metadata_dir = root / "Audiobooks" / "Metadata"
    settings.books_dir = root / "Books"
    settings.books_metadata_dir = root / "Books" / "Metadata"
    return original


def restore(original: dict) -> None:
    for name, value in original.items():
        setattr(settings, name, value)


def source_file(root: Path, folder: str, name: str, role: str, content: bytes,
                metadata: dict | None = None) -> IngestFile:
    path = root / "_INGEST" / folder / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    return IngestFile(
        file_path=str(path),
        file_name=name,
        extension=path.suffix,
        size_bytes=len(content),
        detected_role=role,
        metadata_json=metadata or {},
    )


def race_album(db: Session, root: Path, index: int) -> IngestBatch:
    """An approved music album with three tracks. Music moves are the ones that re-check destination files."""
    folder = f"race-{index}"
    batch = add_batch(
        db, root, folder, "music_album",
        {"artist": f"Race Artist {index}", "album": "Race Album", "year": "2020", "format": "FLAC",
         "track_count": 3, "disc_count": 1, "metadata_quality": "good"},
        [
            source_file(root, folder, f"{number:02d}.flac", "audio_track",
                        f"race-{index}-track-{number}".encode() * 700,
                        {"title": f"Track {number}", "tracknumber": str(number), "discnumber": "1"})
            for number in (1, 2, 3)
        ],
        status="approved",
    )
    batch.suggested_destination = str(settings.music_flac_dir / f"Race Artist {index}" / "2020 - Race Album")
    db.commit()
    return batch


def add_batch(db: Session, root: Path, folder: str, detected_type: str, metadata: dict,
              files: list[IngestFile], status: str = "pending_review") -> IngestBatch:
    batch = IngestBatch(
        source_path=str(root / "_INGEST" / folder),
        detected_type=detected_type,
        status=status,
        confidence=1.0,
        metadata_confirmed=True,
        metadata_json=metadata,
        files=files,
    )
    db.add(batch)
    db.commit()
    db.refresh(batch)
    return batch


def audiobook(db: Session, root: Path, folder: str, filename: str, content: bytes,
              year: str | None, status: str = "pending_review") -> IngestBatch:
    metadata = {
        "author": "Pierce Brown", "title": "Golden Son", "format": "M4B",
        "metadata_quality": "good",
    }
    if year:
        metadata["year"] = year
        metadata["narrator"] = "Tim Gerard Reynolds"
    return add_batch(
        db, root, folder, "audiobook", metadata,
        [source_file(root, folder, filename, "audiobook_audio", content)], status,
    )


def check_golden_son_case(db: Session, root: Path) -> None:
    """Two identical audiobooks, one with a year and one without: only one may move."""
    original = audiobook(db, root, "golden-original", "Golden Son.m4b", GOLDEN, "2015")
    copy = audiobook(db, root, "golden-copy", "Golden Son - Copy.m4b", GOLDEN, None)
    assert original.id < copy.id

    approved = approve_batch(original.id, db)
    assert approved.message == "Batch approved", approved
    refused = approve_batch(copy.id, db)
    assert "Duplicate content" in refused.message and "Nothing was moved" in refused.message, refused
    db.refresh(copy)
    assert copy.status == "pending_review"
    assert DUPLICATE_WARNING_TYPE in copy.metadata_json["metadata_warnings"]
    assert copy.metadata_json["metadata_alerts"][0]["duplicate_count"] == 1
    assert any(
        item["type"] == DUPLICATE_WARNING_TYPE
        for item in build_review_state("audiobook", copy.metadata_json)["blocking_review_items"]
    )

    bulk = approve_selected_batches(BulkApproveRequest(batch_ids=[copy.id]), db)
    assert copy.id in bulk.skipped and bulk.errors[0].reason == "duplicate_content", bulk

    # Even if the copy was approved before the guard existed, the move pre-check and the mover refuse it.
    copy.status = "approved"
    db.commit()
    checks = {item["batch_id"]: item for item in preflight_selected_batches(db, [original.id, copy.id])}
    assert checks[original.id]["ready"], checks[original.id]
    assert not checks[copy.id]["ready"]
    assert "identical to" in " ".join(checks[copy.id]["blockers"])

    moved, errors = move_approved_batches(db, [original.id, copy.id])
    assert moved == 1, errors
    assert any("Duplicate content" in error and str(copy.id) in error for error in errors), errors
    db.refresh(original)
    db.refresh(copy)
    assert original.status == "moved"
    assert copy.status == "needs_metadata_review"
    assert Path(copy.files[0].file_path).exists(), "the refused copy must stay where it was"
    library_files = [p for p in settings.audiobooks_dir.rglob("*.m4b")]
    assert len(library_files) == 1, library_files

    # A later identical file is recognised as already in the library.
    later = audiobook(db, root, "golden-later", "Golden Son again.m4b", GOLDEN, "2015")
    message = approve_batch(later.id, db).message
    assert "already in the library" in message, message

    # While the refused copy still waits in ingest, the later batch stays held back too.
    library_files[0].unlink()
    assert len(refresh_duplicate_state(db, later)) == 1
    # Once every other copy is gone or rejected, the stale warning clears and the batch can be approved.
    copy.status = "rejected"
    db.commit()
    assert refresh_duplicate_state(db, later) == []
    assert DUPLICATE_WARNING_TYPE not in (later.metadata_json.get("metadata_warnings") or [])
    db.commit()
    assert approve_batch(later.id, db).message == "Batch approved"


def check_what_is_not_a_duplicate(db: Session, root: Path) -> None:
    same_size_a = b"A" * 5000
    same_size_b = b"B" * 5000
    first = add_batch(db, root, "size-a", "audiobook", {"author": "X", "title": "A"},
                      [source_file(root, "size-a", "one.mp3", "audiobook_audio", same_size_a)])
    second = add_batch(db, root, "size-b", "audiobook", {"author": "X", "title": "B"},
                       [source_file(root, "size-b", "one.mp3", "audiobook_audio", same_size_b)])
    assert find_content_duplicates(db, second) == [], "same size, different bytes"

    art_one = add_batch(db, root, "art-1", "music_album", {"artist": "Q", "album": "One"}, [
        source_file(root, "art-1", "01.flac", "music_track", b"track-art-1" * 500),
        source_file(root, "art-1", "cover.jpg", "artwork", b"cover" * 500),
        source_file(root, "art-1", "notes.txt", "audio_track", b"notes" * 500),
        source_file(root, "art-1", "empty.flac", "music_track", b""),
    ])
    art_two = add_batch(db, root, "art-2", "music_album", {"artist": "Q", "album": "Two"}, [
        source_file(root, "art-2", "01.flac", "music_track", b"track-art-2" * 500),
        source_file(root, "art-2", "cover.jpg", "artwork", b"cover" * 500),
        source_file(root, "art-2", "notes.txt", "audio_track", b"notes" * 500),
        source_file(root, "art-2", "empty.flac", "music_track", b""),
    ])
    assert find_content_duplicates(db, art_two) == [], "artwork, text and empty files are never duplicates"

    same_content = b"identical-flac-track" * 800
    keeper = add_batch(db, root, "mus-1", "music_album", {"artist": "Z", "album": "One"},
                       [source_file(root, "mus-1", "01.flac", "music_track", same_content)])
    twin = add_batch(db, root, "mus-2", "music_album", {"artist": "Z", "album": "Two"},
                     [source_file(root, "mus-2", "01 - renamed.flac", "discography_track", same_content)])
    found = find_content_duplicates(db, twin)
    assert len(found) == 1 and found[0].other_batch_id == keeper.id, found
    assert find_content_duplicates(db, keeper) == [], "the older batch is not held back by the newer one"

    twin.files[0].file_path = keeper.files[0].file_path  # the same physical file recorded twice
    db.commit()
    assert find_content_duplicates(db, twin) == []

    keeper.status = "rejected"
    db.commit()
    twin.files[0].file_path = str(root / "_INGEST" / "mus-2" / "01 - renamed.flac")
    db.commit()
    assert find_content_duplicates(db, twin) == [], "a rejected batch's files do not count"


def check_moves_run_one_at_a_time(root: Path) -> None:
    # Holding the lock: both move endpoints answer 409, and a direct caller waits its turn.
    engine = create_engine(f"sqlite:///{root / 'lock.db'}", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine)
    # Another request (another thread) is in the middle of a move.
    held, release, finished = threading.Event(), threading.Event(), threading.Event()

    def running_move() -> None:
        with exclusive_move():
            held.set()
            release.wait(15)

    def direct_caller() -> None:
        with factory() as other:
            move_approved_batches(other)
        finished.set()

    holder = threading.Thread(target=running_move)
    holder.start()
    assert held.wait(5)
    with factory() as db:
        for call in (lambda: _execute_selected_move(db, [1]), lambda: move_approved(db)):
            try:
                call()
            except HTTPException as exc:
                assert exc.status_code == 409 and "already running" in exc.detail
            else:
                raise AssertionError("a second move must be refused while one is running")
    waiter = threading.Thread(target=direct_caller)
    waiter.start()
    time.sleep(0.3)
    assert not finished.is_set(), "a direct caller should wait while the lock is held"
    release.set()
    holder.join(timeout=10)
    waiter.join(timeout=10)
    assert finished.is_set()

    # Two overlapping runs over the same approved batches: every batch moves exactly once and none is mislabelled.
    with factory() as db:
        ids = [race_album(db, root, index).id for index in range(4)]

    real_move = shutil.move
    mover.shutil.move = lambda src, dst: (time.sleep(0.03), real_move(src, dst))[1]
    results: list[tuple[int, list[str]]] = []
    try:
        def run() -> None:
            with factory() as session:
                results.append(move_approved_batches(session))

        threads = [threading.Thread(target=run) for _ in range(2)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=60)
    finally:
        mover.shutil.move = real_move

    assert sorted(moved for moved, _ in results) == [0, 4], results
    assert all(not errors for _, errors in results), results
    with factory() as db:
        statuses = {batch.id: batch.status for batch in db.query(IngestBatch).filter(IngestBatch.id.in_(ids))}
        assert set(statuses.values()) == {"moved"}, statuses
        assert len(list(settings.music_flac_dir.rglob("*.flac"))) == 12


def main() -> int:
    root = ROOT / "data" / "_CHECKS" / f"content-guard-{uuid4().hex}"
    root.mkdir(parents=True, exist_ok=True)
    original = configure(root)
    try:
        engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(engine)
        with Session(engine) as db:
            check_golden_son_case(db, root)
            print("PASS identical audiobooks with different metadata: only one moves")
            check_what_is_not_a_duplicate(db, root)
            print("PASS same size, artwork, text, empty, same-path and rejected files are not duplicates")
        check_moves_run_one_at_a_time(root)
        print("PASS moves are serialised and overlapping runs cannot mislabel a batch")
    finally:
        restore(original)
        shutil.rmtree(root, ignore_errors=True)
    print("content duplicate guard checks passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
