"""AA-QA1-FIX3 duplicate/fragment review regression."""

from __future__ import annotations

import os
import sys
from pathlib import Path

from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = PROJECT_ROOT / "backend"
os.environ["DEBUG"] = "true"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.db.session import Base  # noqa: E402
from app.models.archive import IngestBatch, IngestFile  # noqa: E402
from app.services.duplicate_fragment_review import (  # noqa: E402
    build_duplicate_fragment_review,
    duplicate_fragment_summary_for_batch,
)
from app.services.mover import move_approved_batches  # noqa: E402
from app.api.routes import approve_batch, _batch_to_summary  # noqa: E402


def add_music_batch(
    db,
    *,
    artist: str,
    album: str,
    year: str,
    track_count: int,
    destination: str | None = None,
    edition: str | None = None,
) -> IngestBatch:
    batch = IngestBatch(
        source_kind="manual-drop",
        source_path=str(PROJECT_ROOT / ".tmp" / artist / f"{year} - {album} {track_count}"),
        detected_type="music_album",
        status="pending_review",
        confidence=0.95,
        suggested_destination=destination or str(PROJECT_ROOT / ".tmp" / "Library" / artist / f"{year} - {album}"),
        suggested_metadata={"artist": artist, "album": album, "year": year},
        metadata_confirmed=True,
        metadata_json={
            "metadata_quality": "good",
            "metadata_warnings": [],
            "blocking_review_items": [],
            "artist": artist,
            "albumartist": artist,
            "album": album,
            "title": album,
            "year": year,
            "edition": edition,
            "track_count": track_count,
            "review_type": "music_album",
            "review_mode": "single_item",
        },
    )
    db.add(batch)
    db.flush()
    for index in range(1, track_count + 1):
        db.add(IngestFile(
            batch_id=batch.id,
            file_path=str(Path(batch.source_path) / f"{index:02d} - Track {index}.flac"),
            file_name=f"{index:02d} - Track {index}.flac",
            extension=".flac",
            size_bytes=4096,
            checksum=f"{artist}:{album}:{track_count}:{index}",
            detected_role="music_audio",
            metadata_json={
                "artist": artist,
                "albumartist": artist,
                "album": album,
                "title": f"Track {index}",
                "tracknumber": str(index),
                "date": year,
            },
        ))
    db.commit()
    db.refresh(batch)
    return batch


def test_fragment_cluster_blocks_approval_and_move(db) -> None:
    donda10 = add_music_batch(db, artist="Kanye West", album="Donda", year="2021", track_count=10)
    donda3 = add_music_batch(db, artist="Kanye West", album="Donda", year="2021", track_count=3)
    donda9 = add_music_batch(db, artist="Kanye West", album="Donda", year="2021", track_count=9)

    review = build_duplicate_fragment_review(db)
    clusters = review["clusters"]
    donda_clusters = [cluster for cluster in clusters if {row["batch_id"] for row in cluster["batches"]} == {donda10.id, donda3.id, donda9.id}]
    assert len(donda_clusters) == 1, clusters
    cluster = donda_clusters[0]
    assert cluster["review_type"] == "possible_fragment"
    assert "different item counts" in cluster["reason"]

    summary = duplicate_fragment_summary_for_batch(db, donda3)
    assert summary["requires_duplicate_review"] is True
    assert summary["possible_fragment_count"] == 3

    rendered = _batch_to_summary(donda3, db=db)
    assert rendered.requires_duplicate_review is True
    assert rendered.duplicate_fragment_review_state == "possible_fragment"

    response = approve_batch(donda3.id, db)
    assert response.status == "pending_review"
    assert "duplicate/fragment review" in response.message

    donda3.status = "approved"
    db.commit()
    moved, errors = move_approved_batches(db)
    assert moved == 0
    assert any("duplicate/fragment review" in error for error in errors)


def test_same_destination_creates_duplicate_conflict(db) -> None:
    destination = str(PROJECT_ROOT / ".tmp" / "Library" / "Kanye West" / "2007 - Graduation")
    first = add_music_batch(db, artist="Kanye West", album="Graduation", year="2007", track_count=13, destination=destination)
    second = add_music_batch(db, artist="Kanye West", album="Graduation", year="2007", track_count=13, destination=destination)

    clusters = build_duplicate_fragment_review(db)["clusters"]
    matching = [cluster for cluster in clusters if {row["batch_id"] for row in cluster["batches"]} == {first.id, second.id}]
    assert len(matching) == 1, clusters
    assert matching[0]["review_type"] == "possible_duplicate"
    assert "same destination" in matching[0]["reason"]


def test_singletons_are_not_flagged(db) -> None:
    graduation = add_music_batch(db, artist="Kanye West", album="Graduation", year="2007", track_count=13)
    late = add_music_batch(db, artist="Kanye West", album="Late Registration", year="2005", track_count=21)
    jesus = add_music_batch(db, artist="Kanye West", album="JESUS IS KING", year="2019", track_count=11)

    for batch in (graduation, late, jesus):
        summary = duplicate_fragment_summary_for_batch(db, batch)
        assert summary["requires_duplicate_review"] is False
        assert summary["duplicate_fragment_review_state"] == "none"


def test_edition_conflicts_are_grouped_not_fragmented(db) -> None:
    standard = add_music_batch(db, artist="Example Artist", album="Example Album", year="1982", track_count=10)
    deluxe = add_music_batch(db, artist="Example Artist", album="Example Album", year="1982", track_count=10, edition="Deluxe Edition")

    clusters = build_duplicate_fragment_review(db)["clusters"]
    matching = [cluster for cluster in clusters if {row["batch_id"] for row in cluster["batches"]} == {standard.id, deluxe.id}]
    assert len(matching) == 1, clusters
    assert matching[0]["review_type"] == "possible_edition_conflict"
    assert duplicate_fragment_summary_for_batch(db, deluxe)["requires_duplicate_review"] is True

    metadata = dict(deluxe.metadata_json or {})
    metadata["duplicate_fragment_review_state"] = "reviewed_keep_separate"
    deluxe.metadata_json = metadata
    db.commit()
    assert duplicate_fragment_summary_for_batch(db, deluxe)["requires_duplicate_review"] is False


def main() -> None:
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    tests = [
        test_fragment_cluster_blocks_approval_and_move,
        test_same_destination_creates_duplicate_conflict,
        test_singletons_are_not_flagged,
        test_edition_conflicts_are_grouped_not_fragmented,
    ]
    for test in tests:
        db = Session()
        try:
            test(db)
        except HTTPException as exc:
            raise AssertionError(f"Unexpected HTTPException in {test.__name__}: {exc.detail}") from exc
        finally:
            db.close()
            Base.metadata.drop_all(bind=engine)
            Base.metadata.create_all(bind=engine)
    print("PASS - AA-QA1-FIX3 duplicate/fragment review verified")


if __name__ == "__main__":
    main()