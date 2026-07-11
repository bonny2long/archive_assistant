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
from app.schemas.archive import BatchUniversalIngestionOut  # noqa: E402
from app.services.duplicate_fragment_review import (  # noqa: E402
    DuplicateFragmentResolutionError,
    build_duplicate_fragment_review,
    duplicate_fragment_summary_for_batch,
    resolve_duplicate_fragment_group,
)
from app.services.mover import move_approved_batches  # noqa: E402
from app.services.universal_ingestion_review import get_batch_universal_ingestion_review  # noqa: E402
from app.services.universal_review_routing import get_batch_routing_decision  # noqa: E402
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


def add_music_batch_with_tracks(
    db,
    *,
    artist: str,
    album: str,
    year: str,
    track_numbers: list[int],
    extension: str = ".flac",
    title_overrides: dict[int, str] | None = None,
    size_overrides: dict[int, int] | None = None,
    track_count_override: int | None = None,
    tracknumber_overrides: dict[int, str] | None = None,
) -> IngestBatch:
    normalized_extension = extension if extension.startswith(".") else f".{extension}"
    format_bucket = "FLAC" if normalized_extension.lower() == ".flac" else "MP3"
    suggested_destination = str(PROJECT_ROOT / ".tmp" / "Music" / "Library" / format_bucket / artist / f"{year} - {album}")
    batch = IngestBatch(
        source_kind="manual-drop",
        source_path=str(PROJECT_ROOT / ".tmp" / artist / f"{year} - {album} tracks {'-'.join(str(item) for item in track_numbers)}"),
        detected_type="music_album",
        status="pending_review",
        confidence=0.95,
        suggested_destination=suggested_destination,
        suggested_metadata={"artist": artist, "album": album, "year": year, "format": format_bucket, "suggested_destination": suggested_destination},
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
            "track_count": track_count_override if track_count_override is not None else (max(track_numbers) if track_numbers else 0),
            "file_count": len(track_numbers),
            "format": format_bucket,
            "suggested_destination": suggested_destination,
            "review_type": "music_album",
            "review_mode": "single_item",
        },
    )
    db.add(batch)
    db.flush()
    for track_number in track_numbers:
        title = (title_overrides or {}).get(track_number, f"Track {track_number}")
        size = (size_overrides or {}).get(track_number, 4096 + track_number)
        db.add(IngestFile(
            batch_id=batch.id,
            file_path=str(Path(batch.source_path) / f"{track_number:02d} - {title}{normalized_extension}"),
            file_name=f"{track_number:02d} - {title}{normalized_extension}",
            extension=normalized_extension,
            size_bytes=size,
            checksum=f"{artist}:{album}:{normalized_extension}:{track_number}:{title}:{size}",
            detected_role="discography_track",
            metadata_json={
                "artist": artist,
                "albumartist": artist,
                "album": album,
                "title": title,
                "tracknumber": (tracknumber_overrides or {}).get(track_number, str(track_number)),
                "date": year,
            },
        ))
    db.commit()
    db.refresh(batch)
    return batch


def _set_resolved_filename_track_evidence(db, batch: IngestBatch) -> None:
    for ingest_file in batch.files or []:
        track_number = int(ingest_file.file_name.split(" - ", 1)[0])
        metadata = dict(ingest_file.metadata_json or {})
        embedded_track = int(str(metadata.get("tracknumber") or "0").split("/", 1)[0] or 0)
        metadata["track_number_evidence"] = {
            "filename_track": track_number,
            "embedded_track": embedded_track,
            "resolved_track": track_number,
            "disc": 1,
            "preferred_source": "filename_prefix",
            "confidence": 0.9,
            "warnings": [
                "duplicate_embedded_tracknumber",
                "track_order_source_filename_preferred",
            ],
        }
        ingest_file.metadata_json = metadata
    db.commit()
    db.refresh(batch)


def _mark_appendable_canonical(db, batch: IngestBatch) -> None:
    metadata = dict(batch.metadata_json or {})
    metadata["duplicate_fragment_review_state"] = "reviewed_merged"
    batch.metadata_json = metadata
    db.commit()
    db.refresh(batch)

def _cluster_row_for_batch(db, batch: IngestBatch) -> dict:
    scoped_review = batch_duplicate_fragment_review(batch.id, db)
    assert scoped_review["active_cluster"] is True
    assert len(scoped_review["clusters"]) == 1
    rows = {row["batch_id"]: row for row in scoped_review["clusters"][0]["batches"]}
    return rows[batch.id]


def test_track_completeness_detects_internal_gaps(db) -> None:
    add_music_batch_with_tracks(db, artist="Kanye West", album="Gap Album", year="2021", track_numbers=[1, 2, 3, 4, 5, 6])
    fragment = add_music_batch_with_tracks(
        db,
        artist="Kanye West",
        album="Gap Album",
        year="2021",
        track_numbers=[3, 4, 6],
        track_count_override=3,
        tracknumber_overrides={3: "track 03", 4: "04/12", 6: "6 of 12"},
    )
    fragment_row = _cluster_row_for_batch(db, fragment)
    assert fragment_row["present_track_numbers"] == [3, 4, 6]
    assert fragment_row["missing_track_numbers"] == [1, 2, 5]
    assert fragment_row["completeness_status"] == "incomplete"

    db.query(IngestFile).delete()
    db.query(IngestBatch).delete()
    db.commit()

    add_music_batch_with_tracks(db, artist="Kanye West", album="Gap Album", year="2021", track_numbers=[1, 2, 3, 4])
    internal_gap = add_music_batch_with_tracks(db, artist="Kanye West", album="Gap Album", year="2021", track_numbers=[1, 2, 4])
    internal_row = _cluster_row_for_batch(db, internal_gap)
    assert internal_row["present_track_numbers"] == [1, 2, 4]
    assert internal_row["missing_track_numbers"] == [3]
    assert internal_row["completeness_status"] == "incomplete"

    db.query(IngestFile).delete()
    db.query(IngestBatch).delete()
    db.commit()

    add_music_batch_with_tracks(db, artist="Kanye West", album="Single Gap", year="2021", track_numbers=[1, 2])
    single_gap = add_music_batch_with_tracks(db, artist="Kanye West", album="Single Gap", year="2021", track_numbers=[2])
    single_gap_row = _cluster_row_for_batch(db, single_gap)
    assert single_gap_row["present_track_numbers"] == [2]
    assert single_gap_row["missing_track_numbers"] == [1]
    assert single_gap_row["completeness_status"] == "incomplete"

    db.query(IngestFile).delete()
    db.query(IngestBatch).delete()
    db.commit()

    add_music_batch_with_tracks(db, artist="Kanye West", album="Complete Album", year="2021", track_numbers=[1, 2, 3])
    complete = add_music_batch_with_tracks(db, artist="Kanye West", album="Complete Album", year="2021", track_numbers=[1, 2, 3])
    complete_row = _cluster_row_for_batch(db, complete)
    assert complete_row["present_track_numbers"] == [1, 2, 3]
    assert complete_row["missing_track_numbers"] == []
    assert complete_row["completeness_status"] == "complete"

    db.query(IngestFile).delete()
    db.query(IngestBatch).delete()
    db.commit()

    add_music_batch_with_tracks(db, artist="Kanye West", album="Filename Fallback", year="2021", track_numbers=[1, 2, 3, 4, 5, 6])
    collapsed_tags = add_music_batch_with_tracks(
        db,
        artist="Kanye West",
        album="Filename Fallback",
        year="2021",
        track_numbers=[3, 4, 6],
        track_count_override=6,
        tracknumber_overrides={3: "1", 4: "1", 6: "1"},
    )
    collapsed_row = _cluster_row_for_batch(db, collapsed_tags)
    assert collapsed_row["present_track_numbers"] == [3, 4, 6]
    assert collapsed_row["missing_track_numbers"] == [1, 2, 5]
    assert collapsed_row["track_completeness"]["track_number_source"] == "filename"
    assert collapsed_row["completeness_status"] == "incomplete"


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
    assert (canonical.suggested_metadata or {}).get("suggested_destination") == canonical.suggested_destination
    assert metadata.get("file_count") == 13
    assert metadata.get("track_count") == 13
    assert len(metadata.get("tracks") or []) == 13
    assert metadata.get("duplicate_fragment_resolution_audit")
    assert all(file.detected_role == "music_track" for file in canonical.files)
    assert db.query(MoveAction).count() == 0
    summary = duplicate_fragment_summary_for_batch(db, canonical)
    assert summary["requires_duplicate_review"] is False
    assert summary["possible_duplicate_count"] == 0
    assert summary["possible_fragment_count"] == 0
    rendered = _batch_to_summary(canonical, db=db)
    assert rendered.requires_duplicate_review is False
    assert rendered.possible_duplicate_count == 0
    assert rendered.possible_fragment_count == 0
    scoped_review = batch_duplicate_fragment_review(canonical.id, db)
    assert scoped_review["active_cluster"] is False
    assert scoped_review["clusters"] == []
    assert scoped_review["message"] == "No active duplicate or fragment review is required for this batch."


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
    assert metadata.get("suggested_destination") == canonical.suggested_destination
    assert (canonical.suggested_metadata or {}).get("suggested_destination") == canonical.suggested_destination
    assert metadata.get("file_count") == 9
    assert metadata.get("track_count") == 9
    assert db.query(MoveAction).count() == 0


def test_stale_top_level_destination_blocks_approval(db) -> None:
    first = add_music_batch(db, artist="Kanye West", album="Yeezus", year="2013", track_count=5, extension=".flac")
    second = add_music_batch(db, artist="Kanye West", album="Yeezus", year="2013", track_count=4, extension=".flac")

    resolve_duplicate_fragment_group(db, second.id, "merge_into_one_batch", canonical_batch_id=first.id)
    canonical = db.get(IngestBatch, first.id)
    assert canonical is not None
    canonical.suggested_destination = str(PROJECT_ROOT / ".tmp" / "Music" / "Library" / "MP3" / "Kanye West" / "2013 - Yeezus")
    db.commit()

    summary = duplicate_fragment_summary_for_batch(db, canonical)
    assert summary["requires_duplicate_review"] is True
    assert summary["duplicate_fragment_review_state"] == "reviewed_merge_required"
    response = approve_batch(canonical.id, db)
    assert response.status == "pending_review"
    assert "duplicate/fragment review" in response.message

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
    assert batch_duplicate_fragment_review(standard.id, db)["active_cluster"] is False
    assert batch_duplicate_fragment_review(deluxe.id, db)["active_cluster"] is False


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
    duplicate_summary = duplicate_fragment_summary_for_batch(db, duplicate)
    assert duplicate_summary["requires_duplicate_review"] is False
    assert duplicate_summary["possible_duplicate_count"] == 0
    assert batch_duplicate_fragment_review(duplicate.id, db)["active_cluster"] is False

def test_same_destination_creates_duplicate_conflict(db) -> None:
    destination = str(PROJECT_ROOT / ".tmp" / "Library" / "Kanye West" / "2007 - Graduation")
    first = add_music_batch(db, artist="Kanye West", album="Graduation", year="2007", track_count=13, destination=destination)
    second = add_music_batch(db, artist="Kanye West", album="Graduation", year="2007", track_count=13, destination=destination)

    clusters = build_duplicate_fragment_review(db)["clusters"]
    matching = [cluster for cluster in clusters if {row["batch_id"] for row in cluster["batches"]} == {first.id, second.id}]
    assert len(matching) == 1, clusters
    assert matching[0]["review_type"] == "possible_duplicate"
    assert "same destination" in matching[0]["reason"]


def test_artwork_only_music_rows_do_not_form_duplicate_clusters(db) -> None:
    rows = []
    for suffix in ("a", "b"):
        batch = add_music_batch(
            db,
            artist="Kanye West",
            album="The College Dropout",
            year="2004",
            track_count=13,
            attach_files=False,
        )
        db.add(IngestFile(
            batch_id=batch.id,
            file_path=str(Path(batch.source_path) / f"cover-{suffix}.jpg"),
            file_name=f"cover-{suffix}.jpg",
            extension=".jpg",
            size_bytes=2048,
            checksum=f"artwork-only-{suffix}",
            detected_role="artwork",
            metadata_json={"artwork_name": f"cover-{suffix}.jpg"},
        ))
        rows.append(batch)
    db.commit()

    review = build_duplicate_fragment_review(db)
    clustered_ids = {
        row["batch_id"]
        for cluster in review["clusters"]
        for row in cluster["batches"]
    }
    assert all(batch.id not in clustered_ids for batch in rows)

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



def test_incremental_append_adds_only_new_files_and_blocks_incomplete_move(db) -> None:
    canonical_seed = add_music_batch_with_tracks(db, artist="Kanye West", album="Donda", year="2021", track_numbers=[1, 2])
    first_fragment = add_music_batch_with_tracks(db, artist="Kanye West", album="Donda", year="2021", track_numbers=[5])
    resolve_duplicate_fragment_group(db, first_fragment.id, "merge_into_one_batch", canonical_batch_id=canonical_seed.id)

    incoming = add_music_batch_with_tracks(db, artist="Kanye West", album="Donda", year="2021", track_numbers=[2, 3])
    scoped_review = batch_duplicate_fragment_review(incoming.id, db)
    assert scoped_review["active_cluster"] is True
    cluster = scoped_review["clusters"][0]
    assert cluster["review_type"] == "possible_append_to_canonical"
    assert cluster["canonical_batch_id"] == canonical_seed.id
    append_plan = cluster["append_plan"]
    assert append_plan["canonical_batch_id"] == canonical_seed.id
    assert len(append_plan["new_file_ids"]) == 1
    assert len(append_plan["duplicate_file_ids"]) == 1
    assert append_plan["conflict_file_ids"] == []

    result = resolve_duplicate_fragment_group(
        db,
        incoming.id,
        "append_to_existing_canonical_batch",
        canonical_batch_id=canonical_seed.id,
    )
    assert result["canonical_batch_id"] == canonical_seed.id
    canonical = db.get(IngestBatch, canonical_seed.id)
    source = db.get(IngestBatch, incoming.id)
    assert canonical is not None
    assert source is not None
    assert source.status == "merged"
    assert db.query(IngestFile).filter(IngestFile.batch_id == canonical.id).count() == 4
    assert db.query(IngestFile).filter(IngestFile.batch_id == source.id).count() == 1
    metadata = canonical.metadata_json or {}
    assert metadata.get("duplicate_fragment_resolution_audit")[-1]["action"] == "append_to_existing_canonical_batch"
    assert metadata.get("track_count") == 4
    assert metadata.get("file_count") == 4
    assert metadata.get("completeness_status") == "incomplete"
    assert metadata.get("missing_track_numbers") == [4]
    assert metadata.get("format") == "FLAC"
    assert "Music/Library/FLAC" in str(canonical.suggested_destination).replace("\\", "/")

    response = approve_batch(canonical.id, db)
    assert response.status == "pending_review"
    assert "missing track numbers" in response.message
    canonical.status = "approved"
    db.commit()
    moved, errors = move_approved_batches(db)
    assert moved == 0
    assert any("missing track numbers" in error for error in errors)
    assert db.query(MoveAction).count() == 0


def test_incremental_append_conflict_is_blocked(db) -> None:
    canonical_seed = add_music_batch_with_tracks(db, artist="Kanye West", album="Donda", year="2021", track_numbers=[1, 2])
    first_fragment = add_music_batch_with_tracks(db, artist="Kanye West", album="Donda", year="2021", track_numbers=[5])
    resolve_duplicate_fragment_group(db, first_fragment.id, "merge_into_one_batch", canonical_batch_id=canonical_seed.id)

    incoming = add_music_batch_with_tracks(
        db,
        artist="Kanye West",
        album="Donda",
        year="2021",
        track_numbers=[2],
        title_overrides={2: "Different Track Two"},
        size_overrides={2: 9999},
    )
    scoped_review = batch_duplicate_fragment_review(incoming.id, db)
    cluster = scoped_review["clusters"][0]
    assert cluster["review_type"] == "possible_append_to_canonical"
    assert len(cluster["append_plan"]["conflict_file_ids"]) == 1

    try:
        resolve_duplicate_fragment_group(db, incoming.id, "append_to_existing_canonical_batch", canonical_batch_id=canonical_seed.id)
    except DuplicateFragmentResolutionError as exc:
        assert "Track conflicts" in str(exc)
    else:
        raise AssertionError("Append should reject same track number with different identity")
    assert db.query(IngestFile).filter(IngestFile.batch_id == canonical_seed.id).count() == 3
    assert db.query(IngestFile).filter(IngestFile.batch_id == incoming.id).count() == 1

def test_resolved_filename_evidence_prevents_false_append_conflicts(db) -> None:
    canonical = add_music_batch_with_tracks(
        db,
        artist="Lil Wayne",
        album="Tha Carter II",
        year="2005",
        track_numbers=[1, 2, 3],
        tracknumber_overrides={1: "1", 2: "1", 3: "1"},
    )
    _set_resolved_filename_track_evidence(db, canonical)
    _mark_appendable_canonical(db, canonical)

    incoming = add_music_batch_with_tracks(
        db,
        artist="Lil Wayne",
        album="Tha Carter II",
        year="2005",
        track_numbers=[4, 5, 6],
        tracknumber_overrides={4: "1", 5: "1", 6: "1"},
    )
    _set_resolved_filename_track_evidence(db, incoming)

    scoped_review = batch_duplicate_fragment_review(incoming.id, db)
    cluster = scoped_review["clusters"][0]
    assert cluster["review_type"] == "possible_append_to_canonical"
    plan = cluster["append_plan"]
    assert len(plan["new_file_ids"]) == 3
    assert plan["duplicate_file_ids"] == []
    assert plan["conflict_file_ids"] == []

    result = resolve_duplicate_fragment_group(
        db,
        incoming.id,
        "append_to_existing_canonical_batch",
        canonical_batch_id=canonical.id,
    )
    assert result["canonical_batch_id"] == canonical.id
    assert db.query(IngestFile).filter(IngestFile.batch_id == canonical.id).count() == 6
    assert db.get(IngestBatch, incoming.id).status == "merged"


def test_fragment_append_refreshes_universal_review_from_resolved_tracks(db) -> None:
    canonical = add_music_batch_with_tracks(
        db,
        artist="Unknown Artist",
        album="Tha Carter II",
        year="2005",
        track_numbers=[1, 2, 3, 4, 5, 6, 7],
        track_count_override=22,
        tracknumber_overrides={number: "1" for number in [1, 2, 3, 4, 5, 6, 7]},
    )
    _set_resolved_filename_track_evidence(db, canonical)
    _mark_appendable_canonical(db, canonical)

    source_track_sets = [
        [9, 10, 11, 12, 13],
        [14, 15, 16, 17, 18],
        [19, 21, 22],
    ]
    sources = []
    for track_numbers in source_track_sets:
        source = add_music_batch_with_tracks(
            db,
            artist="Unknown Artist",
            album="Tha Carter II",
            year="2005",
            track_numbers=track_numbers,
            track_count_override=22,
            tracknumber_overrides={number: "1" for number in track_numbers},
        )
        _set_resolved_filename_track_evidence(db, source)
        sources.append(source)

    result = resolve_duplicate_fragment_group(
        db,
        sources[0].id,
        "append_to_existing_canonical_batch",
        canonical_batch_id=canonical.id,
    )
    assert result["canonical_batch_id"] == canonical.id
    assert db.query(IngestFile).filter(IngestFile.batch_id == canonical.id).count() == 20
    assert all(db.get(IngestBatch, source.id).status == "merged" for source in sources)

    db.refresh(canonical)
    metadata = canonical.metadata_json or {}
    assert metadata["duplicate_fragment_review_state"] == "reviewed_merged"
    assert metadata["duplicate_track_numbers"] == []
    assert metadata["track_number_conflicts"] == []
    assert metadata["missing_track_numbers"] == [8, 20]
    assert metadata["completeness_status"] == "incomplete"
    assert metadata["source_origin_count"] == 4
    assert metadata["resolved_source_origin_count"] == 4
    assert metadata["source_origins_resolved"] is True
    track_rows = metadata["tracks"]
    assert len(track_rows) == 20
    assert sorted(row["track_number"] for row in track_rows) == [
        1, 2, 3, 4, 5, 6, 7, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 21, 22,
    ]
    assert all(row["track_number_source"] == "filename_prefix" for row in track_rows)

    legacy_metadata = dict(canonical.metadata_json or {})
    legacy_metadata.pop("source_origins_resolved", None)
    legacy_metadata.pop("source_origin_count", None)
    legacy_metadata.pop("resolved_source_origin_count", None)
    legacy_metadata["tracks"] = [
        {**row, "track_number": "1", "track_number_source": "embedded_tracknumber"}
        for row in legacy_metadata["tracks"]
    ]
    canonical.metadata_json = legacy_metadata
    db.commit()

    review = get_batch_universal_ingestion_review(db, canonical.id, snapshot=True)
    db.refresh(canonical)
    repaired_metadata = canonical.metadata_json or {}
    assert repaired_metadata["source_origins_resolved"] is True
    assert sorted(row["track_number"] for row in repaired_metadata["tracks"]) == [
        1, 2, 3, 4, 5, 6, 7, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 21, 22,
    ]
    validated_review = BatchUniversalIngestionOut.model_validate(review)
    assert validated_review.summary.candidate_count == 1
    assert review["summary"]["candidate_count"] == 1
    assert review["summary"]["member_count"] == 20
    assert all(
        isinstance(member["track_number"], str)
        for candidate in review["candidates"]
        for member in candidate["members"]
    )
    assert review["summary"]["source_origin_count"] == 4
    assert review["summary"]["source_origins_resolved"] is True
    flag_types = {flag["flag_type"] for flag in review["mixed_media_flags"]}
    assert "track_number_conflict" not in flag_types
    assert "merge_recommended" not in flag_types
    assert "split_release_candidate" not in flag_types
    assert "partial_track_set" in flag_types
    assert review["summary"]["decision_counts"]["review_required"] == 0

    routing = get_batch_routing_decision(db, canonical.id)
    assert routing["decision"] == "music_editor_allowed"
    assert "source_fragment_group_detected" not in routing["reasons"]
    assert "reconstruction_review_required" not in routing["reasons"]

    metadata = dict(canonical.metadata_json or {})
    metadata["accepted_incomplete_album"] = True
    canonical.metadata_json = metadata
    canonical.metadata_confirmed = False
    db.commit()
    approval = approve_batch(canonical.id, db)
    assert approval.status == "pending_review"
    assert "metadata review" in approval.message.casefold()

def test_resolved_same_track_conflict_still_blocks_append(db) -> None:
    canonical = add_music_batch_with_tracks(
        db,
        artist="Lil Wayne",
        album="Tha Carter II",
        year="2005",
        track_numbers=[6],
        title_overrides={6: "Shooter"},
        size_overrides={6: 6000},
        tracknumber_overrides={6: "1"},
    )
    _set_resolved_filename_track_evidence(db, canonical)
    _mark_appendable_canonical(db, canonical)

    incoming = add_music_batch_with_tracks(
        db,
        artist="Lil Wayne",
        album="Tha Carter II",
        year="2005",
        track_numbers=[6],
        title_overrides={6: "Different Song"},
        size_overrides={6: 9999},
        tracknumber_overrides={6: "1"},
    )
    _set_resolved_filename_track_evidence(db, incoming)

    cluster = batch_duplicate_fragment_review(incoming.id, db)["clusters"][0]
    plan = cluster["append_plan"]
    assert len(plan["conflict_file_ids"]) == 1
    assert plan["new_file_ids"] == []
    detail = plan["conflict_details"][0]
    assert detail["disc_number"] == "1"
    assert detail["track_number"] == "6"
    assert detail["existing_file_names"] == ["06 - Shooter.flac"]

    try:
        resolve_duplicate_fragment_group(
            db,
            incoming.id,
            "append_to_existing_canonical_batch",
            canonical_batch_id=canonical.id,
        )
    except DuplicateFragmentResolutionError as exc:
        assert "Track conflicts require review before append." in str(exc)
    else:
        raise AssertionError("Resolved same-track conflict should block append")


def test_resolved_same_track_duplicate_is_skipped(db) -> None:
    canonical = add_music_batch_with_tracks(
        db,
        artist="Lil Wayne",
        album="Tha Carter II",
        year="2005",
        track_numbers=[6],
        title_overrides={6: "Shooter"},
        size_overrides={6: 6000},
        tracknumber_overrides={6: "1"},
    )
    _set_resolved_filename_track_evidence(db, canonical)
    _mark_appendable_canonical(db, canonical)

    incoming = add_music_batch_with_tracks(
        db,
        artist="Lil Wayne",
        album="Tha Carter II",
        year="2005",
        track_numbers=[6],
        title_overrides={6: "Shooter"},
        size_overrides={6: 6000},
        tracknumber_overrides={6: "1"},
    )
    _set_resolved_filename_track_evidence(db, incoming)

    plan = batch_duplicate_fragment_review(incoming.id, db)["clusters"][0]["append_plan"]
    assert len(plan["duplicate_file_ids"]) == 1
    assert plan["new_file_ids"] == []
    assert plan["conflict_file_ids"] == []

def main() -> None:
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    tests = [
        test_track_completeness_detects_internal_gaps,
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
        test_incremental_append_adds_only_new_files_and_blocks_incomplete_move,
        test_incremental_append_conflict_is_blocked,
        test_resolved_filename_evidence_prevents_false_append_conflicts,
        test_fragment_append_refreshes_universal_review_from_resolved_tracks,
        test_resolved_same_track_conflict_still_blocks_append,
        test_resolved_same_track_duplicate_is_skipped,
        test_artwork_only_music_rows_do_not_form_duplicate_clusters,
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
