#!/usr/bin/env python3
"""Verify scoped audiobook tags survive candidate materialization and repair."""

from __future__ import annotations

import os
import sys
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = PROJECT_ROOT / "backend"
os.environ["DEBUG"] = "true"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.db.session import Base  # noqa: E402
from app.models.archive import IngestBatch, IngestFile  # noqa: E402
from app.models.media_metadata import (  # noqa: E402
    CandidateMember,
    MediaIdentityCandidate,
    UniversalIngestionReviewAction,
)
from app.services.approved_candidate_materialization import (  # noqa: E402
    materialize_approved_candidates,
    repair_materialized_audiobook_children,
)


def tagged_audio(path: Path) -> dict:
    number = "1" if "01" in path.stem else "2"
    return {
        "title": "Endymion",
        "author": "Dan Simmons",
        "year": "1996",
        "narrator": "Victor Garber",
        "chapter_title": path.stem,
        "track_number": number,
        "disc_number": "1",
    }


def tagged_file(path: Path) -> dict:
    values = tagged_audio(path)
    return {
        "media_kind": "audiobook_audio",
        "author": values["author"],
        "album": values["title"],
        "title": values["chapter_title"],
        "tracknumber": values["track_number"],
        "discnumber": values["disc_number"],
        "embedded_metadata_fields": {
            "artist": values["author"],
            "album_artist": values["author"],
            "album": values["title"],
        },
    }


def add_file(db, parent: IngestBatch, path: Path, role: str) -> IngestFile:
    row = IngestFile(
        batch_id=parent.id,
        file_path=str(path),
        file_name=path.name,
        extension=path.suffix.lower(),
        size_bytes=path.stat().st_size,
        checksum=f"test-{path.name}",
        detected_role=role,
        metadata_json={"artist": "Unknown Artist"},
    )
    db.add(row)
    db.flush()
    return row


def add_candidate(
    db,
    parent: IngestBatch,
    *,
    key: str,
    title: str,
    files: list[IngestFile],
) -> MediaIdentityCandidate:
    candidate = MediaIdentityCandidate(
        batch_id=parent.id,
        candidate_key=key,
        candidate_media_type="music_audio",
        candidate_title=title,
        candidate_primary_creator="Unknown Artist",
        candidate_year="1996",
        candidate_confidence=0.9,
        identity_evidence_json={"identity_source": "stale_music_scan"},
    )
    db.add(candidate)
    db.flush()
    for ingest_file in files:
        db.add(CandidateMember(
            candidate_id=candidate.id,
            batch_file_id=ingest_file.id,
            relative_path=ingest_file.file_name,
            media_class="music_audio",
            role_in_candidate=(
                "support"
                if ingest_file.extension in {".jpg", ".jpeg", ".png", ".webp"}
                else "primary"
            ),
            sort_key=ingest_file.file_name,
            evidence_json={},
        ))
    return candidate


def run_check(db, root: Path) -> None:
    book_folder = root / "1996 - Endymion (Foushee) 602mb"
    music_folder = root / "Example Album"
    book_folder.mkdir(parents=True)
    music_folder.mkdir()
    audio_paths = [book_folder / "Endymion 01.mp3", book_folder / "Endymion 02.mp3"]
    for path in audio_paths:
        path.write_bytes(b"audio")
    cover = book_folder / "cover.jpg"
    cover.write_bytes(b"cover")
    music_path = music_folder / "01 - Song.mp3"
    music_path.write_bytes(b"music")

    parent = IngestBatch(
        source_kind="manual-drop",
        source_path=str(root),
        detected_type="music_discography",
        status="pending_review",
        confidence=0.9,
        metadata_json={"review_type": "discography"},
    )
    db.add(parent)
    db.flush()
    audiobook_files = [
        add_file(db, parent, audio_paths[0], "music_track"),
        add_file(db, parent, audio_paths[1], "music_track"),
        add_file(db, parent, cover, "artwork"),
    ]
    music_file = add_file(db, parent, music_path, "music_track")
    audiobook = add_candidate(
        db,
        parent,
        key="music:source:1996-endymion",
        title="Endymion (Foushee) 602mb",
        files=audiobook_files,
    )
    music = add_candidate(
        db,
        parent,
        key="music:source:example-album",
        title="Example Album",
        files=[music_file],
    )
    db.add_all([
        UniversalIngestionReviewAction(
            batch_id=parent.id,
            candidate_id=audiobook.id,
            action_type="override_media_class",
            target_media_class="audiobook_audio",
            decision_status="active",
        ),
        UniversalIngestionReviewAction(
            batch_id=parent.id,
            candidate_id=audiobook.id,
            action_type="approve_candidate",
            decision_status="active",
        ),
        UniversalIngestionReviewAction(
            batch_id=parent.id,
            candidate_id=music.id,
            action_type="exclude_from_move_plan",
            decision_status="active",
        ),
    ])
    db.commit()

    with (
        patch(
            "app.services.audiobook_metadata.extract_audio_metadata",
            side_effect=tagged_audio,
        ),
        patch(
            "app.services.approved_candidate_materialization.build_audiobook_file_metadata",
            side_effect=tagged_file,
        ),
    ):
        result = materialize_approved_candidates(db, parent.id)
    assert result["created_count"] == 1
    child = db.get(IngestBatch, result["created_child_batch_ids"][0])
    assert child.detected_type == "audiobook"
    assert child.metadata_json["author"] == "Dan Simmons"
    assert child.metadata_json["title"] == "Endymion (Foushee) 602mb"
    assert child.metadata_json["year"] == "1996"
    assert child.suggested_metadata["author"] == "Dan Simmons"
    assert "/Audiobooks/Library/Dan Simmons/1996 - Endymion (Foushee) 602mb" in (
        child.suggested_destination.replace("\\", "/")
    )
    assert {row.detected_role for row in child.files} == {
        "audiobook_audio",
        "audiobook_artwork",
    }
    assert all(
        row.metadata_json.get("author") == "Dan Simmons"
        for row in child.files
        if row.extension == ".mp3"
    )
    db.refresh(parent)
    assert parent.detected_type == "music_discography"
    assert music_file.batch_id == parent.id
    assert db.query(MediaIdentityCandidate).filter_by(batch_id=parent.id).count() == 2

    stale = dict(child.metadata_json)
    stale.update({"author": "Unknown Artist"})
    child.metadata_json = stale
    child.suggested_metadata = {"author": "Unknown Artist", "title": stale["title"]}
    child.suggested_destination = "Audiobooks/Library/Unknown Artist/Endymion"
    db.commit()
    with patch(
        "app.services.audiobook_metadata.extract_audio_metadata",
        side_effect=tagged_audio,
    ):
        dry_run = repair_materialized_audiobook_children(
            db,
            parent_batch_id=parent.id,
            apply=False,
        )
    assert dry_run["repairable_child_batch_ids"] == [child.id]
    assert db.get(IngestBatch, child.id).metadata_json["author"] == "Unknown Artist"

    with (
        patch(
            "app.services.audiobook_metadata.extract_audio_metadata",
            side_effect=tagged_audio,
        ),
        patch(
            "app.services.approved_candidate_materialization.build_audiobook_file_metadata",
            side_effect=tagged_file,
        ),
    ):
        repaired = repair_materialized_audiobook_children(
            db,
            parent_batch_id=parent.id,
            apply=True,
        )
    assert repaired["repaired_child_batch_ids"] == [child.id]
    db.refresh(child)
    assert child.metadata_json["author"] == "Dan Simmons"
    assert child.metadata_json["audiobook_child_metadata_repair_audit"]


def main() -> None:
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    with TemporaryDirectory(dir=PROJECT_ROOT) as temp, Session() as db:
        run_check(db, Path(temp) / "The Hyperion Cantos - Dan Simmons")
    print("PASS - audiobook child materialization uses attached embedded metadata")


if __name__ == "__main__":
    main()
