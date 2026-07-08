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
from app.models.archive import IngestBatch, IngestFile, MoveAction  # noqa: E402
from app.services.duplicate_fragment_review import (  # noqa: E402
    DuplicateFragmentResolutionError,
    build_duplicate_fragment_review,
    duplicate_fragment_summary_for_batch,
    resolve_duplicate_fragment_group,
)
from app.services.mover import move_approved_batches  # noqa: E402
from app.api.routes import approve_batch, batch_duplicate_fragment_review, _batch_to_summary  # noqa: E402


def add_music_batch(
    db,
    *,
    artist: str,
    album: str,
    year: str,
    track_count: int,
    destination: str | None = None,
    edition: str | None = None,
    attach_files: bool = True,
    extension: str = ".flac",
    destination_format: str | None = None,
) -> IngestBatch:
    normalized_extension = extension if extension.startswith(".") else f".{extension}"
    format_bucket = destination_format or (
        "FLAC" if normalized_extension.lower() == ".flac"
        else "MP3" if normalized_extension.lower() == ".mp3"
        else normalized_extension.lstrip(".").upper()
    )
    suggested_destination = destination or str(PROJECT_ROOT / ".tmp" / "Music" / "Library" / format_bucket / artist / f"{year} - {album}")
    batch = IngestBatch(
        source_kind="manual-drop",
        source_path=str(PROJECT_ROOT / ".tmp" / artist / f"{year} - {album} {track_count}"),
        detected_type="music_album",
        status="pending_review",
        confidence=0.95,
        suggested_destination=suggested_destination,
        suggested_metadata={"artist": artist, "album": album, "year": year, "format": format_bucket},
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
            "file_count": track_count if attach_files else 0,
            "format": format_bucket,
            "suggested_destination": suggested_destination,
            "review_type": "music_album",
            "review_mode": "single_item",
        },
    )
    db.add(batch)
    db.flush()
    if attach_files:
        for index in range(1, track_count + 1):
            db.add(IngestFile(
                batch_id=batch.id,
                file_path=str(Path(batch.source_path) / f"{index:02d} - Track {index}{normalized_extension}"),
                file_name=f"{index:02d} - Track {index}{normalized_extension}",
                extension=normalized_extension,
                size_bytes=4096,
                checksum=f"{artist}:{album}:{track_count}:{normalized_extension}:{index}",
                detected_role="discography_track",
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

    scoped_review = batch_duplicate_fragment_review(donda3.id, db)
    assert len(scoped_review["clusters"]) == 1
    scoped_ids = {row["batch_id"] for row in scoped_review["clusters"][0]["batches"]}
    assert scoped_ids == {donda10.id, donda3.id, donda9.id}
    rows_by_id = {row["batch_id"]: row for row in scoped_review["clusters"][0]["batches"]}
    required_fields = {
        "batch_id",
        "title",
        "creator",
        "year",
        "item_count",
        "file_count",
        "file_formats",
        "suggested_destination",
        "source_path",
        "status",
        "detected_type",
        "file_ownership_status",
        "file_ownership_warning",
    }
    assert all(required_fields.issubset(row) for row in rows_by_id.values())
    assert rows_by_id[donda10.id]["file_count"] == 10
    assert rows_by_id[donda3.id]["file_count"] == 3
    assert rows_by_id[donda9.id]["file_count"] == 9
    assert scoped_review["clusters"][0]["has_file_ownership_warnings"] is False
    assert all(row["file_count"] > 0 for row in rows_by_id.values())
    assert all(row["file_ownership_status"] == "verified" for row in rows_by_id.values())

    response = approve_batch(donda3.id, db)
    assert response.status == "pending_review"
    assert "duplicate/fragment review" in response.message

    donda3.status = "approved"
    db.commit()
    moved, errors = move_approved_batches(db)
    assert moved == 0
    assert any("duplicate/fragment review" in error for error in errors)

def test_missing_file_ownership_is_flagged_and_blocked(db) -> None:
    complete = add_music_batch(db, artist="Kanye West", album="Donda", year="2021", track_count=10)
    missing = add_music_batch(db, artist="Kanye West", album="Donda", year="2021", track_count=3, attach_files=False)

    scoped_review = batch_duplicate_fragment_review(missing.id, db)
    assert len(scoped_review["clusters"]) == 1
    cluster = scoped_review["clusters"][0]
    assert cluster["review_type"] == "possible_fragment"
    assert cluster["has_file_ownership_warnings"] is True

    rows_by_id = {row["batch_id"]: row for row in cluster["batches"]}
    assert rows_by_id[complete.id]["file_count"] == 10
    assert rows_by_id[complete.id]["file_ownership_status"] == "verified"
    assert rows_by_id[missing.id]["item_count"] == 3
    assert rows_by_id[missing.id]["file_count"] == 0
    assert rows_by_id[missing.id]["file_ownership_status"] == "missing_files"
    assert rows_by_id[missing.id]["file_ownership_warning"] == "Batch has media item metadata but no attached scoped files."

    response = approve_batch(missing.id, db)
    assert response.status == "pending_review"
    assert "duplicate/fragment review" in response.message

    metadata = dict(missing.metadata_json or {})
    metadata["duplicate_fragment_review_state"] = "reviewed_keep_separate"
    missing.metadata_json = metadata
    db.commit()
    assert duplicate_fragment_summary_for_batch(db, missing)["requires_duplicate_review"] is True




def test_missing_file_ownership_cannot_resolve(db) -> None:
    add_music_batch(db, artist="Kanye West", album="Donda", year="2021", track_count=10)
    missing = add_music_batch(db, artist="Kanye West", album="Donda", year="2021", track_count=3, attach_files=False)

    try:
        resolve_duplicate_fragment_group(db, missing.id, "merge_into_one_batch")
    except DuplicateFragmentResolutionError as exc:
        assert "verified scoped files" in str(exc)
    else:
        raise AssertionError("Missing file ownership should block resolution")


def test_merge_resolution_reassigns_scoped_files_without_deleting_sources(db) -> None:
    donda10 = add_music_batch(db, artist="Kanye West", album="Donda", year="2021", track_count=10)
    donda3 = add_music_batch(db, artist="Kanye West", album="Donda", year="2021", track_count=3)

    result = resolve_duplicate_fragment_group(db, donda3.id, "merge_into_one_batch", canonical_batch_id=donda10.id)
    assert result["canonical_batch_id"] == donda10.id
    assert result["collapsed_batch_ids"] == [donda3.id]

    canonical = db.get(IngestBatch, donda10.id)
    source = db.get(IngestBatch, donda3.id)
    assert canonical is not None
    assert source is not None
    assert source.status == "merged"
    assert (source.metadata_json or {}).get("merged_into_batch_id") == canonical.id
    assert db.query(IngestFile).filter(IngestFile.batch_id == canonical.id).count() == 13
    assert db.query(IngestFile).filter(IngestFile.batch_id == source.id).count() == 0
    metadata = canonical.metadata_json or {}
    destination = str(canonical.suggested_destination or "").replace("\\", "/")
    assert metadata.get("format") == "FLAC"
    assert "Music/Library/FLAC" in destination
    assert metadata.get("suggested_destination") == canonical.suggested_destination
    assert metadata.get("file_count") == 13
    assert metadata.get("track_count") == 13
    assert len(metadata.get("tracks") or []) == 13
    assert metadata.get("duplicate_fragment_resolution_audit")
    assert all(file.detected_role == "music_track" for file in canonical.files)
    assert db.query(MoveAction).count() == 0
    assert duplicate_fragment_summary_for_batch(db, canonical)["requires_duplicate_review"] is False


def test_merge_resolution_rebuilds_mp3_destination(db) -> None:
    first = add_music_batch(db, artist="Kanye West", album="Yeezus", year="2013", track_count=5, extension=".mp3")
    second = add_music_batch(db, artist="Kanye West", album="Yeezus", year="2013", track_count=4, extension=".mp3")

    resolve_duplicate_fragment_group(db, second.id, "merge_into_one_batch", canonical_batch_id=first.id)
    canonical = db.get(IngestBatch, first.id)
    assert canonical is not None
    metadata = canonical.metadata_json or {}
    destination = str(canonical.suggested_destination or "").replace("\\", "/")
    assert metadata.get("format") == "MP3"
    assert "Music/Library/MP3" in destination
    assert metadata.get("file_count") == 9
    assert metadata.get("track_count") == 9
    assert db.query(MoveAction).count() == 0


def test_mixed_format_merge_is_blocked_before_collapse(db) -> None:
    flac = add_music_batch(db, artist="Kanye West", album="Donda", year="2021", track_count=10, extension=".flac")
    mp3 = add_music_batch(db, artist="Kanye West", album="Donda", year="2021", track_count=3, extension=".mp3")

    try:
        resolve_duplicate_fragment_group(db, mp3.id, "merge_into_one_batch", canonical_batch_id=flac.id)
    except DuplicateFragmentResolutionError as exc:
        assert "Mixed audio formats" in str(exc)
    else:
        raise AssertionError("Mixed format merge should be blocked")

    flac_after = db.get(IngestBatch, flac.id)
    mp3_after = db.get(IngestBatch, mp3.id)
    assert flac_after is not None
    assert mp3_after is not None
    assert flac_after.status == "pending_review"
    assert mp3_after.status == "pending_review"
    assert db.query(IngestFile).filter(IngestFile.batch_id == flac.id).count() == 10
    assert db.query(IngestFile).filter(IngestFile.batch_id == mp3.id).count() == 3
    assert db.query(MoveAction).count() == 0

def test_keep_separate_requires_distinct_destinations(db) -> None:
    destination = str(PROJECT_ROOT / ".tmp" / "Library" / "Kanye West" / "2007 - Graduation")
    first = add_music_batch(db, artist="Kanye West", album="Graduation", year="2007", track_count=13, destination=destination)
    add_music_batch(db, artist="Kanye West", album="Graduation", year="2007", track_count=13, destination=destination)

    try:
        resolve_duplicate_fragment_group(db, first.id, "keep_separate", confirm_distinct_destinations=True)
    except DuplicateFragmentResolutionError as exc:
        assert "distinct destination" in str(exc)
    else:
        raise AssertionError("Keep separate should reject duplicate destinations")

    db.close()


def test_keep_separate_with_distinct_destinations_clears_blocker(db) -> None:
    standard = add_music_batch(
        db,
        artist="Example Artist",
        album="Example Album",
        year="1982",
        track_count=10,
        destination=str(PROJECT_ROOT / ".tmp" / "Library" / "Example Artist" / "1982 - Example Album"),
    )
    deluxe = add_music_batch(
        db,
        artist="Example Artist",
        album="Example Album",
        year="1982",
        track_count=10,
        edition="Deluxe Edition",
        destination=str(PROJECT_ROOT / ".tmp" / "Library" / "Example Artist" / "1982 - Example Album [Deluxe]"),
    )

    resolve_duplicate_fragment_group(db, standard.id, "keep_separate", confirm_distinct_destinations=True)
    assert duplicate_fragment_summary_for_batch(db, standard)["requires_duplicate_review"] is False
    assert duplicate_fragment_summary_for_batch(db, deluxe)["requires_duplicate_review"] is False


def test_mark_duplicate_blocks_duplicate_batch_from_move(db) -> None:
    destination = str(PROJECT_ROOT / ".tmp" / "Library" / "Kanye West" / "2007 - Graduation")
    first = add_music_batch(db, artist="Kanye West", album="Graduation", year="2007", track_count=13, destination=destination)
    second = add_music_batch(db, artist="Kanye West", album="Graduation", year="2007", track_count=13, destination=destination)

    result = resolve_duplicate_fragment_group(
        db,
        first.id,
        "mark_duplicate",
        canonical_batch_id=first.id,
        duplicate_batch_ids=[second.id],
    )
    assert result["blocked_batch_ids"] == [second.id]
    duplicate = db.get(IngestBatch, second.id)
    assert duplicate is not None
    assert duplicate.status == "duplicate_review"
    assert (duplicate.metadata_json or {}).get("blocked_from_move") is True
    assert duplicate_fragment_summary_for_batch(db, duplicate)["requires_duplicate_review"] is True
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
        test_missing_file_ownership_is_flagged_and_blocked,
        test_missing_file_ownership_cannot_resolve,
        test_merge_resolution_reassigns_scoped_files_without_deleting_sources,
        test_merge_resolution_rebuilds_mp3_destination,
        test_mixed_format_merge_is_blocked_before_collapse,
        test_keep_separate_requires_distinct_destinations,
        test_keep_separate_with_distinct_destinations_clears_blocker,
        test_mark_duplicate_blocks_duplicate_batch_from_move,
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
