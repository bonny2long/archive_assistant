"""Isolated acceptance checks for AA-MOVE1 selected canary moves."""

from __future__ import annotations

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

from app.core.config import settings  # noqa: E402
from app.api.routes import move_selected  # noqa: E402
from app.db.session import Base  # noqa: E402
from app.models.archive import IngestBatch, IngestFile  # noqa: E402
from app.models.media_metadata import MediaIdentityCandidate  # noqa: E402
from app.schemas.archive import SelectedMoveRequest  # noqa: E402
from app.services.mover import (  # noqa: E402
    move_approved_batches,
    preflight_selected_batches,
)


SETTING_NAMES = (
    "data_root", "music_mp3_dir", "music_flac_dir", "music_metadata_dir",
    "movies_dir", "movies_metadata_dir", "tv_dir", "tv_metadata_dir",
    "audiobooks_dir", "audiobooks_metadata_dir",
    "books_dir", "books_metadata_dir",
)


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


def source_file(
    root: Path,
    folder: str,
    name: str,
    role: str,
    metadata: dict | None = None,
) -> IngestFile:
    path = root / "_INGEST" / folder / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"archive-assistant-canary")
    return IngestFile(
        file_path=str(path),
        file_name=name,
        extension=path.suffix,
        size_bytes=path.stat().st_size,
        detected_role=role,
        metadata_json=metadata or {},
    )


def add_batch(
    db: Session,
    *,
    source_root: Path,
    folder: str,
    detected_type: str,
    metadata: dict,
    files: list[IngestFile],
    destination: Path | None = None,
    status: str = "approved",
) -> IngestBatch:
    batch = IngestBatch(
        source_path=str(source_root / "_INGEST" / folder),
        detected_type=detected_type,
        status=status,
        confidence=1.0,
        suggested_destination=str(destination) if destination else None,
        metadata_confirmed=True,
        metadata_json=metadata,
        files=files,
    )
    db.add(batch)
    db.commit()
    db.refresh(batch)
    return batch


def assert_ready_and_move(db: Session, batch: IngestBatch) -> dict:
    check = preflight_selected_batches(db, [batch.id])[0]
    assert check["ready"], check
    moved, errors = move_approved_batches(db, [batch.id])
    assert moved == 1, errors
    db.refresh(batch)
    assert batch.status == "moved"
    assert (batch.metadata_json or {}).get("move_manifest")
    return check


def main() -> int:
    temp_root = ROOT / "data" / "_CHECKS" / f"selected-move-{uuid4().hex}"
    temp_root.mkdir(parents=True, exist_ok=True)
    original = configure(temp_root)
    try:
        engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(engine)
        with Session(engine) as db:
            music_destination = (
                settings.music_flac_dir / "Canary Artist" / "2026 - Canary Album"
            )
            music = add_batch(
                db,
                source_root=temp_root,
                folder="music",
                detected_type="music_album",
                destination=music_destination,
                metadata={
                    "artist": "Canary Artist", "album": "Canary Album",
                    "year": "2026", "format": "FLAC", "track_count": 1,
                    "disc_count": 1, "metadata_quality": "good",
                },
                files=[source_file(
                    temp_root, "music", "01 - Canary.flac", "audio_track",
                    {"title": "Canary", "tracknumber": "1", "discnumber": "1"},
                )],
            )
            assert_ready_and_move(db, music)
            assert (music_destination / "01 - Canary.flac").exists()

            pending = add_batch(
                db,
                source_root=temp_root,
                folder="pending",
                detected_type="music_album",
                status="pending_review",
                destination=settings.music_mp3_dir / "Pending" / "2026 - Pending",
                metadata={"artist": "Pending", "album": "Pending", "year": "2026"},
                files=[source_file(
                    temp_root, "pending", "01.mp3", "audio_track",
                    {"title": "Pending", "tracknumber": "1", "discnumber": "1"},
                )],
            )
            assert "approved is required" in " ".join(
                preflight_selected_batches(db, [pending.id])[0]["blockers"]
            )

            parent = add_batch(
                db,
                source_root=temp_root,
                folder="parent",
                detected_type="music_album",
                destination=settings.music_mp3_dir / "Parent" / "2026 - Parent",
                metadata={"artist": "Parent", "album": "Parent", "year": "2026"},
                files=[source_file(
                    temp_root, "parent", "01.mp3", "audio_track",
                    {"title": "One", "tracknumber": "1", "discnumber": "1"},
                )],
            )
            db.add_all([
                MediaIdentityCandidate(
                    batch_id=parent.id, candidate_key="music:parent:one",
                    candidate_media_type="music", candidate_title="One",
                    candidate_confidence=1.0,
                ),
                MediaIdentityCandidate(
                    batch_id=parent.id, candidate_key="music:parent:two",
                    candidate_media_type="music", candidate_title="Two",
                    candidate_confidence=1.0,
                ),
            ])
            db.commit()
            assert "Parent review containers" in " ".join(
                preflight_selected_batches(db, [parent.id])[0]["blockers"]
            )

            existing = add_batch(
                db,
                source_root=temp_root,
                folder="existing",
                detected_type="music_album",
                destination=settings.music_mp3_dir / "Existing" / "2026 - Existing",
                metadata={"artist": "Existing", "album": "Existing", "year": "2026"},
                files=[source_file(
                    temp_root, "existing", "01.mp3", "audio_track",
                    {"title": "One", "tracknumber": "1", "discnumber": "1"},
                )],
            )
            Path(existing.suggested_destination).mkdir(parents=True)
            assert "Destination already exists" in " ".join(
                preflight_selected_batches(db, [existing.id])[0]["blockers"]
            )

            shared = settings.music_mp3_dir / "Shared" / "2026 - Shared"
            shared_batches = [
                add_batch(
                    db,
                    source_root=temp_root,
                    folder=f"shared-{index}",
                    detected_type="music_album",
                    destination=shared,
                    metadata={
                        "artist": f"Shared {index}", "album": f"Shared {index}",
                        "year": "2026", "track_count": 1, "disc_count": 1,
                    },
                    files=[source_file(
                        temp_root, f"shared-{index}", f"0{index}.mp3",
                        "audio_track",
                        {"title": str(index), "tracknumber": "1", "discnumber": "1"},
                    )],
                )
                for index in (1, 2)
            ]
            shared_checks = preflight_selected_batches(
                db, [batch.id for batch in shared_batches]
            )
            assert all(
                "same destination" in " ".join(item["blockers"])
                for item in shared_checks
            )

            partial_ready = add_batch(
                db,
                source_root=temp_root,
                folder="partial-ready",
                detected_type="music_album",
                destination=(
                    settings.music_mp3_dir
                    / "Partial Artist"
                    / "2026 - Partial Album"
                ),
                metadata={
                    "artist": "Partial Artist", "album": "Partial Album",
                    "year": "2026", "track_count": 1, "disc_count": 1,
                },
                files=[source_file(
                    temp_root, "partial-ready", "01.mp3", "audio_track",
                    {"title": "Partial", "tracknumber": "1", "discnumber": "1"},
                )],
            )
            partial_response = move_selected(
                SelectedMoveRequest(batch_ids=[partial_ready.id, pending.id]),
                db,
            )
            partial_results = {
                item.batch_id: item for item in partial_response.results
            }
            assert partial_response.moved == 1, partial_response
            assert partial_results[partial_ready.id].moved is True
            assert partial_results[pending.id].moved is False
            assert partial_results[pending.id].blockers

            movie = add_batch(
                db,
                source_root=temp_root,
                folder="movie",
                detected_type="video_movie",
                metadata={"title": "Canary Movie", "year": "2026"},
                files=[
                    source_file(temp_root, "movie", "movie.mkv", "video_file"),
                    source_file(temp_root, "movie", "movie.en.srt", "subtitle"),
                    source_file(temp_root, "movie", "poster.jpg", "movie_artwork"),
                ],
            )
            movie_check = assert_ready_and_move(db, movie)
            assert movie_check["source_file_count"] == 3

            tv = add_batch(
                db,
                source_root=temp_root,
                folder="tv",
                detected_type="video_tv_show",
                metadata={"show_title": "Canary Show", "year": "2026"},
                files=[
                    source_file(
                        temp_root, "tv", f"episode-{number}.mkv", "tv_episode",
                        {
                            "include": True, "season_number": 1,
                            "episode_number": number,
                            "episode_code": f"S01E0{number}",
                            "episode_title": f"Episode {number}",
                            "destination_group": "season",
                            "is_special": False,
                        },
                    )
                    for number in (1, 2)
                ],
            )
            assert_ready_and_move(db, tv)
            assert len(list((settings.tv_dir / "Canary Show").rglob("*.mkv"))) == 2

            audiobook = add_batch(
                db,
                source_root=temp_root,
                folder="audiobook",
                detected_type="audiobook",
                metadata={
                    "author": "Canary Author", "title": "Canary Book",
                    "year": "2026", "format": "MP3", "metadata_quality": "good",
                },
                files=[
                    source_file(temp_root, "audiobook", "01.mp3", "audiobook_audio"),
                    source_file(temp_root, "audiobook", "cover.jpg", "audiobook_artwork"),
                ],
            )
            assert_ready_and_move(db, audiobook)
            audiobook_destination = Path(audiobook.suggested_destination)
            assert (audiobook_destination / "cover.jpg").exists()

            book = add_batch(
                db,
                source_root=temp_root,
                folder="book",
                detected_type="book",
                metadata={
                    "author": "Canary Author", "title": "Canary EPUB",
                    "year": "2026", "format": "EPUB", "metadata_quality": "good",
                },
                files=[source_file(
                    temp_root, "book", "Canary EPUB.epub", "book_file",
                )],
            )
            assert_ready_and_move(db, book)
            assert list(
                (settings.books_dir / "EPUB").rglob("Canary EPUB.epub")
            )

        routes = (ROOT / "backend/app/api/routes.py").read_text(encoding="utf-8")
        frontend = (ROOT / "frontend/src/App.tsx").read_text(encoding="utf-8")
        assert '"/move/selected/preflight"' in routes
        assert '"/move/selected"' in routes
        assert '"/batches/{batch_id}/move"' in routes
        assert "preflightSelectedMove" in frontend
        assert "scanMusic" not in frontend[frontend.index("const runSelectedMove"):frontend.index("const handleMove =")]
        print("PASS selected move preflight and canary execution")
        return 0
    finally:
        restore(original)
        shutil.rmtree(temp_root, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
