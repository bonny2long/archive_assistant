from __future__ import annotations

import os
import sys
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = PROJECT_ROOT / "backend"
os.environ["DEBUG"] = "true"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.db.session import Base
from app.models.archive import IngestBatch, IngestFile
from app.services.media_type_correction import correct_batch_media_type
from app.services.parent_candidate_materialization import is_parent_container_batch
from app.services.universal_ingestion import build_candidate_drafts, classify_batch_files


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def file_row(path: str, album: str, source_folder: str) -> IngestFile:
    return IngestFile(
        file_path=path,
        file_name=path.rsplit("\\", 1)[-1],
        extension=".flac",
        size_bytes=100,
        detected_role="discography_track",
        metadata_json={
            "artist": "Wrong Embedded Artist",
            "albumartist": "Wrong Embedded Artist",
            "album": album,
            "_discography_album": {"source_folder": source_folder},
        },
    )


def main() -> None:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine, expire_on_commit=False)

    with session_factory() as db:
        batch = IngestBatch(
            source_path=r"C:\ready\drive-001",
            detected_type="music_album",
            status="pending_review",
            metadata_json={
                "artist": "Drew Karpyshyn",
                "album": "Star Wars The Old Republic Revan",
                "year": "2003",
                "review_origin": "multi_artist_discography_split",
            },
        )
        db.add(batch)
        db.flush()
        audio = [
            IngestFile(
                batch_id=batch.id,
                file_path=rf"C:\ready\drive-001\Star Wars The Old Republic Revan\Disc 1\{number:02d}.mp3",
                file_name=f"{number:02d}.mp3",
                extension=".mp3",
                size_bytes=100,
                detected_role="discography_track",
                metadata_json={
                    "artist": "Drew Karpyshyn",
                    "album": "Star Wars The Old Republic Revan",
                    "_discography_album": {"source_folder": "Star Wars The Old Republic Revan"},
                },
            )
            for number in (1, 2)
        ]
        db.add_all(audio)
        db.flush()
        db.commit()

        correct_batch_media_type(db, batch.id, "audiobook")
        db.refresh(batch)
        require(batch.detected_type == "audiobook", "The batch type should persist as audiobook")
        require("Audiobooks" in str(batch.suggested_destination), "Audiobook destination should be rebuilt")
        require(all(item.detected_role == "audiobook_audio" for item in audio), "Audio roles should become audiobook roles")
        require(bool((batch.metadata_json or {}).get("media_type_correction_audit")), "Media correction must retain an audit entry")

    with session_factory() as db:
        mixed = IngestBatch(
            source_path=r"C:\ready\drive-002",
            detected_type="music_album",
            status="pending_review",
            metadata_json={"review_origin": "approved_candidate_materialization"},
        )
        mixed.files = [
            file_row(
                r"C:\ready\drive-002\Lil Wayne - Discography 1999-2023 [FLAC]\2013 - I Am Not a Human Being II\01.flac",
                "I Am Not A Human Being II",
                "Lil Wayne - Discography 1999-2023 [FLAC]",
            ),
            file_row(
                r"C:\ready\drive-003\Lil Wayne - Discography 1999-2023 [FLAC]\2000 - Lights Out\01.flac",
                "I Am Not A Human Being II",
                "Lil Wayne - Discography 1999-2023 [FLAC]",
            ),
        ]
        drafts = build_candidate_drafts(classify_batch_files(mixed))
        titles = {draft.title for draft in drafts.values()}
        require(titles == {"I Am Not a Human Being II", "Lights Out"}, "Physical release folders must override stale shared album tags for grouping")

        audiobook = IngestBatch(
            source_path=r"C:\ready\drive-004",
            detected_type="music_album",
            status="pending_review",
            metadata_json={"review_origin": "multi_artist_discography_split"},
        )
        audiobook.files = [
            IngestFile(
                file_path=rf"C:\ready\drive-004\Star Wars The Old Republic Revan\Disc {disc}\01.mp3",
                file_name="01.mp3",
                extension=".mp3",
                size_bytes=100,
                detected_role="discography_track",
                metadata_json={
                    "artist": "Drew Karpyshyn",
                    "album": "Star Wars The Old Republic Revan",
                    "_discography_album": {"source_folder": "Star Wars The Old Republic Revan"},
                },
            )
            for disc in (1, 2, 3)
        ]
        drafts = build_candidate_drafts(classify_batch_files(audiobook))
        require(len(drafts) == 1, "Disc folders must not be mistaken for separate releases")

        repaired_child = IngestBatch(
            source_path=r"C:\ready\drive-005",
            detected_type="music_album",
            status="pending_review",
            metadata_json={
                "source_parent_batch_id": 12,
                "materialization_history": [{"candidate_id": 99, "child_batch_id": 100}],
            },
        )
        require(
            is_parent_container_batch(repaired_child),
            "A child with its own materialization history must become a nested repair container",
        )

    print("PASS: media type correction and nested release repair")


if __name__ == "__main__":
    main()
