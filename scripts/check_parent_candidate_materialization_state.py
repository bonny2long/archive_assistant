#!/usr/bin/env python3
"""AA-QA1-FIX1/FIX2 parent candidate materialization state regression."""

from __future__ import annotations

import os
import sys
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = PROJECT_ROOT / "backend"
os.environ["DEBUG"] = "true"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.api.routes import _batch_to_summary  # noqa: E402
from app.db.session import Base  # noqa: E402
from app.models.archive import IngestBatch, IngestFile  # noqa: E402
from app.models.media_metadata import CandidateMember, MediaIdentityCandidate, UniversalIngestionReviewAction  # noqa: E402
from app.services.approved_candidate_materialization import materialize_approved_candidates  # noqa: E402
from app.services.batch_split import execute_split_discography_releases  # noqa: E402
from app.services.batch_display import build_batch_display_fields  # noqa: E402
from app.services.mover import move_approved_batches  # noqa: E402
from app.services.parent_candidate_materialization import build_parent_candidate_summary  # noqa: E402


def album_row(title: str, year: str) -> dict:
    return {
        "album": title,
        "title": title,
        "artist": "Lil Wayne",
        "album_artist": "Lil Wayne",
        "year": year,
        "source_folder": title,
        "genre": "Hip-Hop",
    }


def add_album_file(batch: IngestBatch, release: dict, index: int, role: str = "music_audio", extension: str = ".flac") -> IngestFile:
    name = f"{index:02d} - Track {index}{extension}"
    ingest_file = IngestFile(
        file_path=str(Path(batch.source_path) / release["source_folder"] / name),
        file_name=name,
        extension=extension,
        size_bytes=4096,
        checksum=f"sha-{release['source_folder']}-{index}",
        detected_role=role,
        metadata_json={
            "artist": release["artist"],
            "album_artist": release["artist"],
            "albumartist": release["artist"],
            "album": release["album"],
            "title": f"Track {index}",
            "tracknumber": str(index),
            "date": release["year"],
            "genre": release["genre"],
            "format": extension.lstrip(".").upper(),
            "_discography_album": release,
        },
    )
    batch.files.append(ingest_file)
    return ingest_file


def add_candidate(db, batch_id: int, release: dict, files: list[IngestFile]) -> MediaIdentityCandidate:
    candidate = MediaIdentityCandidate(
        batch_id=batch_id,
        candidate_key=f"music:lil-wayne:{release['source_folder']}".casefold(),
        candidate_media_type="music",
        candidate_title=release["album"],
        candidate_primary_creator=release["artist"],
        candidate_year=release["year"],
        candidate_confidence=0.93,
        identity_evidence_json={"source_folder": release["source_folder"]},
    )
    db.add(candidate)
    db.flush()
    for ingest_file in files:
        db.add(CandidateMember(
            candidate_id=candidate.id,
            batch_file_id=ingest_file.id,
            relative_path=f"{release['source_folder']}/{ingest_file.file_name}",
            media_class="music_audio",
            role_in_candidate="primary",
            sort_key=ingest_file.file_name,
            evidence_json={"source_folder": release["source_folder"]},
        ))
    return candidate


def add_candidate_action(db, batch_id: int, candidate_id: int, action_type: str) -> None:
    db.add(UniversalIngestionReviewAction(
        batch_id=batch_id,
        candidate_id=candidate_id,
        action_type=action_type,
        decision_status="active",
        reason="QA1-FIX2 materialization regression",
    ))


def approve_candidate(db, batch_id: int, candidate_id: int) -> None:
    add_candidate_action(db, batch_id, candidate_id, "approve_candidate")


def make_lil_wayne_parent(db, include_album_rows: bool = True, role: str = "music_audio") -> tuple[IngestBatch, list[MediaIdentityCandidate]]:
    releases = [
        album_row("FWA", "2015"),
        album_row("Funeral", "2020"),
        album_row("I Am Music", "2023"),
        album_row("Rebirth", "2010"),
    ]
    parent = IngestBatch(
        source_kind="manual-drop",
        source_path=str(PROJECT_ROOT / ".tmp" / "Lil Wayne"),
        detected_type="music_discography",
        status="pending_review",
        confidence=0.81,
        metadata_json={
            "type": "music_discography",
            "artist": "Lil Wayne",
            "album": "I Am Music",
            "albums": releases if include_album_rows else [{"album": "Unmatched Parent Row", "artist": "Wrong Artist", "source_folder": "not-a-candidate"}],
            "album_count": len(releases),
            "release_count": len(releases),
        },
    )
    db.add(parent)
    db.flush()

    candidates: list[MediaIdentityCandidate] = []
    for index, release in enumerate(releases, start=1):
        files = [add_album_file(parent, release, index, role=role)]
        db.flush()
        candidate = add_candidate(db, parent.id, release, files)
        approve_candidate(db, parent.id, candidate.id)
        candidates.append(candidate)
    db.commit()
    db.refresh(parent)
    return parent, candidates


def test_multi_candidate_parent_is_container(db) -> None:
    parent, _candidates = make_lil_wayne_parent(db)
    summary = build_parent_candidate_summary(db, parent)
    assert summary["is_parent_review_container"] is True
    assert summary["candidate_group_count"] == 4
    assert summary["approved_candidate_count"] == 4
    assert summary["excluded_candidate_count"] == 0
    assert summary["remaining_candidate_count"] == 0
    assert summary["needs_materialization"] is True
    assert summary["parent_review_state"] == "candidates_approved_waiting_materialization"

    display = build_batch_display_fields(parent, summary)
    assert display["media_label"] == "Discography Source"
    assert display["primary_name"] == "Lil Wayne"
    assert display["secondary_name"] == "4 approved candidates, 0 remaining"
    assert display["item_label"] == "candidate groups"
    assert display["item_count"] == 4
    assert display["secondary_name"] != "I Am Music"


def test_materializes_approved_candidates_once(db) -> None:
    parent, _candidates = make_lil_wayne_parent(db, include_album_rows=False, role="discography_track")

    parent.status = "approved"
    db.commit()
    moved, errors = move_approved_batches(db)
    assert moved == 0
    assert any("parent review container" in error for error in errors)
    parent.status = "pending_review"
    db.commit()

    first = materialize_approved_candidates(db, parent.id)
    assert first["created_count"] == 4
    assert first["skipped_count"] == 0
    assert len(first["created_child_batch_ids"]) == 4
    assert first["parent_review_state"] == "split_complete"

    db.refresh(parent)
    assert parent.status == "split_complete"
    children = [db.get(IngestBatch, child_id) for child_id in first["created_child_batch_ids"]]
    assert all(child is not None for child in children)
    assert {child.metadata_json["album"] for child in children} == {"FWA", "Funeral", "I Am Music", "Rebirth"}
    assert all(child.status == "pending_review" for child in children)
    assert all(child.detected_type == "music_album" for child in children)
    assert all(child.metadata_json["track_count"] == 1 for child in children)
    assert all(child.metadata_json["source_candidate_id"] for child in children)
    assert all(db.query(IngestFile).filter(IngestFile.batch_id == child.id).count() == 1 for child in children)
    child_summaries = [_batch_to_summary(child, db=db) for child in children]
    assert all(summary.id == child.id for summary, child in zip(child_summaries, children))
    assert all(summary.status == "pending_review" for summary in child_summaries)
    assert all(summary.detected_type == "music_album" for summary in child_summaries)
    assert all(summary.edit_kind == "music_album" for summary in child_summaries)
    assert all(summary.requires_duplicate_review is False for summary in child_summaries)
    assert all(isinstance(summary.blocking_review_items, list) for summary in child_summaries)
    assert all(isinstance(summary.review_confirmed, bool) for summary in child_summaries)

    second = materialize_approved_candidates(db, parent.id)
    assert second["created_count"] == 0
    assert second["skipped_count"] == 4
    assert set(second["created_child_batch_ids"]) == set(first["created_child_batch_ids"])
    assert db.query(IngestBatch).filter(IngestBatch.detected_type == "music_album").count() == 4

    drained_summary = build_parent_candidate_summary(db, parent)
    assert drained_summary["parent_is_drained"] is True
    assert drained_summary["display_state"] == "drained_parent"
    assert drained_summary["approval_allowed"] is False
    assert drained_summary["move_ready"] is False
    assert drained_summary["requires_review"] is False
    assert drained_summary["active_file_count"] == 0
    assert drained_summary["child_batch_count"] == 4
    assert drained_summary["historical_scan_snapshot"] is True
    assert parent.metadata_json["albums"]
    drained_display = build_batch_display_fields(parent, drained_summary)
    assert drained_display["media_label"] == "Processed Container"
    assert drained_display["secondary_name"] == "4 child batches created; 0 active files"
    assert drained_display["edit_kind"] is None



def test_split_complete_parent_without_candidates_stays_container(db) -> None:
    parent = IngestBatch(
        source_kind="manual-drop",
        source_path=str(PROJECT_ROOT / ".tmp" / "drive-download-20260628T012539Z-3-010"),
        detected_type="music_discography",
        status="split_complete",
        confidence=1.0,
        metadata_json={
            "type": "music_discography",
            "artist": "drive-download-20260628T012539Z-3-010",
            "release_count": 3,
            "album_count": 3,
            "track_count": 63,
            "materialization_history": [
                {"candidate_id": 101, "child_batch_id": 201},
                {"candidate_id": 102, "child_batch_id": 202},
                {"candidate_id": 103, "child_batch_id": 203},
            ],
        },
    )
    db.add(parent)
    db.commit()
    db.refresh(parent)

    summary = build_parent_candidate_summary(db, parent)
    assert summary["is_parent_review_container"] is True
    assert summary["parent_review_state"] == "split_complete"
    assert summary["candidate_group_count"] == 3
    assert summary["approved_candidate_count"] == 0
    assert summary["materialized_child_count"] == 3
    assert summary["child_batch_count"] == 0
    assert summary["parent_container_state"] is None
    assert summary["parent_is_drained"] is False
    assert summary["remaining_candidate_count"] == 0
    assert summary["needs_materialization"] is False

    display = build_batch_display_fields(parent, summary)
    assert display["media_label"] == "Discography Source"
    assert display["secondary_name"] == "0 approved candidates, 0 remaining"
    assert display["item_label"] == "candidate groups"
    assert display["item_count"] == 3
    assert display["item_count"] != 63


def test_split_complete_parent_with_remaining_files_requires_remainder_review(db) -> None:
    parent = IngestBatch(
        source_kind="manual-drop",
        source_path=str(PROJECT_ROOT / ".tmp" / "drive-download-20260628T012539Z-3-010"),
        detected_type="music_discography",
        status="split_complete",
        confidence=1.0,
        metadata_json={
            "type": "music_discography",
            "artist": "drive-download-20260628T012539Z-3-010",
            "release_count": 3,
            "album_count": 3,
            "track_count": 63,
            "materialization_history": [
                {"candidate_id": 101, "child_batch_id": 201},
            ],
        },
    )
    db.add(parent)
    db.flush()
    add_album_file(parent, album_row("Remaining Discography", "2024"), 1, role="discography_track")
    add_album_file(parent, album_row("Remaining Discography", "2024"), 2, role="discography_track")
    db.commit()
    db.refresh(parent)

    summary = build_parent_candidate_summary(db, parent)
    assert summary["is_parent_review_container"] is True
    assert summary["parent_review_state"] == "review_in_progress"
    assert summary["candidate_group_count"] == 3
    assert summary["materialized_child_count"] == 0
    assert summary["child_candidate_count"] == 0
    assert summary["child_batch_count"] == 0
    assert summary["parent_container_state"] == "active_parent_container"
    assert summary["parent_is_drained"] is False
    assert summary["unresolved_candidate_count"] == 1
    assert summary["remaining_candidate_count"] == 1
    assert summary["needs_materialization"] is False

    display = build_batch_display_fields(parent, summary)
    assert display["media_label"] == "Discography Source"
    assert display["secondary_name"] == "0 approved candidates, 1 remaining"
    assert display["item_label"] == "candidate groups"
    assert display["item_count"] == 3
    assert display["item_count"] != 63
    assert display["edit_kind"] == "music_discography"


def test_partial_materialization_keeps_unresolved_parent_remainder(db) -> None:
    parent = IngestBatch(
        source_kind="manual-drop",
        source_path=str(PROJECT_ROOT / ".tmp" / "drive-download-20260628T012539Z-3-004"),
        detected_type="music_discography",
        status="pending_review",
        confidence=0.68,
        metadata_json={
            "type": "music_discography",
            "artist": "drive-download-20260628T012539Z-3-004",
            "album_count": 5,
            "release_count": 5,
        },
    )
    db.add(parent)
    db.flush()

    known_release = album_row("Known Album", "2024")
    blocked_release = album_row("Blocked Unknown", "2024")
    review_later_release = album_row("Review Later Unknown", "2024")
    excluded_release = album_row("Excluded Unknown", "2024")
    unresolved_release = album_row("Still Unknown", "2024")
    known_file = add_album_file(parent, known_release, 1, role="discography_track")
    blocked_file = add_album_file(parent, blocked_release, 2, role="discography_track")
    review_later_file = add_album_file(parent, review_later_release, 3, role="discography_track")
    excluded_file = add_album_file(parent, excluded_release, 4, role="discography_track")
    unresolved_file = add_album_file(parent, unresolved_release, 5, role="discography_track")
    db.flush()

    known = add_candidate(db, parent.id, known_release, [known_file])
    blocked = add_candidate(db, parent.id, blocked_release, [blocked_file])
    review_later = add_candidate(db, parent.id, review_later_release, [review_later_file])
    excluded = add_candidate(db, parent.id, excluded_release, [excluded_file])
    unresolved = add_candidate(db, parent.id, unresolved_release, [unresolved_file])
    approve_candidate(db, parent.id, known.id)
    add_candidate_action(db, parent.id, blocked.id, "block_candidate")
    add_candidate_action(db, parent.id, review_later.id, "mark_review_later")
    add_candidate_action(db, parent.id, excluded.id, "exclude_from_move_plan")
    db.commit()

    result = materialize_approved_candidates(db, parent.id)
    assert result["created_count"] == 1
    assert result["skipped_count"] == 0
    assert result["parent_review_state"] == "review_in_progress"
    assert result["unresolved_candidate_count"] == 1
    assert result["blocked_candidate_count"] == 1
    assert result["excluded_candidate_count"] == 1
    assert result["review_later_candidate_count"] == 1

    db.refresh(parent)
    assert parent.status == "pending_review"
    summary = build_parent_candidate_summary(db, parent)
    assert summary["is_parent_review_container"] is True
    assert summary["parent_review_state"] == "review_in_progress"
    assert summary["materialized_child_count"] == 1
    assert summary["unresolved_candidate_count"] == 1
    assert summary["blocked_candidate_count"] == 1
    assert summary["review_later_candidate_count"] == 1
    assert summary["excluded_candidate_count"] == 1
    assert summary["needs_materialization"] is False

    child = db.get(IngestBatch, result["created_child_batch_ids"][0])
    assert child is not None
    assert child.detected_type == "music_album"
    assert child.metadata_json["album"] == "Known Album"
    assert db.query(IngestFile).filter(IngestFile.batch_id == child.id).count() == 1
    assert db.query(IngestFile).filter(IngestFile.batch_id == child.id, IngestFile.id == known_file.id).count() == 1
    for remainder_file in (blocked_file, review_later_file, excluded_file, unresolved_file):
        assert db.query(IngestFile).filter(IngestFile.batch_id == parent.id, IngestFile.id == remainder_file.id).count() == 1

    audit = (parent.metadata_json or {}).get("partial_materialization_audit") or []
    assert audit
    latest = audit[-1]
    assert latest["materialized_candidate_ids"] == [known.id]
    assert latest["blocked_candidate_ids"] == [blocked.id]
    assert latest["excluded_candidate_ids"] == [excluded.id]
    assert latest["review_later_candidate_ids"] == [review_later.id]
    assert latest["unresolved_candidate_ids"] == [unresolved.id]

    parent.status = "approved"
    db.commit()
    moved, errors = move_approved_batches(db)
    assert moved == 0
    assert any("parent review container" in error for error in errors)

def test_split_complete_parent_counts_actual_children_without_history(db) -> None:
    parent = IngestBatch(
        source_kind="manual-drop",
        source_path=str(PROJECT_ROOT / ".tmp" / "stale-parent-history"),
        detected_type="music_discography",
        status="split_complete",
        confidence=1.0,
        metadata_json={
            "type": "music_discography",
            "artist": "drive-download-20260628T012539Z-3-010",
            "album_count": 3,
            "release_count": 3,
            "track_count": 63,
            "parent_review_state": "split_complete",
        },
    )
    db.add(parent)
    db.flush()
    for album in ("Graduation", "Tha Block Is Hot"):
        db.add(IngestBatch(
            source_kind="manual-drop",
            source_path=parent.source_path,
            detected_type="music_album",
            status="pending_review",
            confidence=0.9,
            suggested_destination=str(PROJECT_ROOT / ".tmp" / "Music" / "Library" / "FLAC" / album),
            suggested_metadata={"artist": "Test Artist", "album": album},
            metadata_json={
                "artist": "Test Artist",
                "album": album,
                "track_count": 1,
                "split_from_batch_id": parent.id,
            },
        ))
    db.commit()
    db.refresh(parent)

    summary = build_parent_candidate_summary(db, parent)
    assert summary["is_parent_review_container"] is True
    assert summary["parent_review_state"] == "split_complete"
    assert summary["materialized_child_count"] == 2
    assert summary["child_candidate_count"] == 2
    assert summary["remaining_candidate_count"] == 0
    assert summary["parent_is_drained"] is True
    assert summary["display_state"] == "drained_parent"
    assert summary["active_file_count"] == 0
    assert summary["child_batch_count"] == 2

    display = build_batch_display_fields(parent, summary)
    assert display["media_label"] == "Processed Container"
    assert display["secondary_name"] == "2 child batches created; 0 active files"
    assert display["item_label"] == "child batches"
    assert display["item_count"] == 2


def test_discography_editor_rows_create_child_batches_without_candidates(db) -> None:
    releases = [
        {**album_row("Graduation", "2007"), "artist": "Kanye West", "source_folder": "Kanye West - Discography", "format": "FLAC"},
        {**album_row("Tha Block Is Hot", "1999"), "artist": "Lil Wayne", "source_folder": "Lil Wayne - Tha Block Is Hot", "format": "FLAC"},
        {**album_row("Trilogy - House Of Balloons", "2012"), "artist": "The Weeknd", "source_folder": "The Weeknd Discography", "format": "FLAC"},
        {**album_row("Impossible", "2006"), "artist": "Kanye West", "source_folder": "Kanye West - Impossible", "format": "MP3"},
    ]
    parent = IngestBatch(
        source_kind="manual-drop",
        source_path=str(PROJECT_ROOT / ".tmp" / "drive-download-20260628T012539Z-3-010"),
        detected_type="music_discography",
        status="pending_review",
        confidence=1.0,
        suggested_destination=str(PROJECT_ROOT / ".tmp" / "Music" / "Discographies" / "drive-download-20260628T012539Z-3-010"),
        suggested_metadata={"artist": "drive-download-20260628T012539Z-3-010"},
        metadata_json={
            "type": "music_discography",
            "artist": "drive-download-20260628T012539Z-3-010",
            "review_type": "music_discography",
            "review_mode": "item_list",
            "albums": [
                {**release, "format": "FLAC", "include": True, "release_type": "album", "warnings": ["folder_artist_mismatch"]}
                for release in releases
            ],
            "album_count": 4,
            "release_count": 4,
            "track_count": 4,
        },
    )
    db.add(parent)
    db.flush()
    for index, release in enumerate(releases, start=1):
        extension = ".mp3" if release.get("format") == "MP3" else ".flac"
        add_album_file(parent, release, index, role="discography_track", extension=extension)
    db.commit()
    db.refresh(parent)

    result = execute_split_discography_releases(db, parent.id)
    assert result["created_count"] == 4
    assert result["skipped_count"] == 0
    assert result["parent_status"] == "split_complete"
    assert result["parent_review_state"] == "split_complete"
    assert result["remaining_parent_file_count"] == 0

    db.refresh(parent)
    assert parent.status == "split_complete"
    assert db.query(IngestFile).filter(IngestFile.batch_id == parent.id).count() == 0
    children = [db.get(IngestBatch, child_id) for child_id in result["created_child_batch_ids"]]
    assert {child.metadata_json["artist"] for child in children if child is not None} == {"Kanye West", "Lil Wayne", "The Weeknd"}
    assert {child.metadata_json["album"] for child in children if child is not None} == {"Graduation", "Tha Block Is Hot", "Trilogy - House Of Balloons", "Impossible"}
    assert all(child.detected_type == "music_album" for child in children if child is not None)
    assert all(child.status == "pending_review" for child in children if child is not None)
    flac_children = [child for child in children if child is not None and child.metadata_json.get("format") == "FLAC"]
    mp3_children = [child for child in children if child is not None and child.metadata_json.get("format") == "MP3"]
    assert flac_children and all("Music" in (child.suggested_destination or "") and "FLAC" in (child.suggested_destination or "") for child in flac_children)
    assert mp3_children and all("Music" in (child.suggested_destination or "") and "MP3" in (child.suggested_destination or "") for child in mp3_children)
    stale_flac = flac_children[0]
    stale_flac.suggested_destination = (stale_flac.suggested_destination or "").replace("Music\\Library\\FLAC", "Music\\Library\\MP3").replace("Music/Library/FLAC", "Music/Library/MP3")
    stale_meta = dict(stale_flac.metadata_json or {})
    stale_meta["suggested_destination"] = stale_flac.suggested_destination
    stale_flac.metadata_json = stale_meta
    stale_suggested = dict(stale_flac.suggested_metadata or {})
    stale_suggested["suggested_destination"] = stale_flac.suggested_destination
    stale_flac.suggested_metadata = stale_suggested
    db.commit()

    second = execute_split_discography_releases(db, parent.id)
    assert second["created_count"] == 0
    assert set(second["existing_child_batch_ids"]) == set(result["created_child_batch_ids"])
    db.refresh(stale_flac)
    assert stale_flac.metadata_json["format"] == "FLAC"
    assert "FLAC" in (stale_flac.suggested_destination or "")
    assert stale_flac.suggested_metadata["suggested_destination"] == stale_flac.suggested_destination
    assert stale_flac.metadata_json["suggested_destination"] == stale_flac.suggested_destination
    assert db.query(IngestBatch).filter(
        IngestBatch.detected_type == "music_album",
        IngestBatch.source_path == parent.source_path,
    ).count() == 4


def test_support_only_discography_release_stays_on_parent(db) -> None:
    release = album_row("Artwork Remainder", "2024") | {
        "release_decision": "extract_as_child",
        "include": True,
    }
    parent = IngestBatch(
        source_kind="manual-drop",
        source_path=str(PROJECT_ROOT / ".tmp" / "support-only-parent"),
        detected_type="music_discography",
        status="pending_review",
        confidence=0.8,
        metadata_json={
            "type": "music_discography",
            "artist": "Archive Artist",
            "albums": [release],
            "album_count": 1,
            "release_count": 1,
        },
    )
    db.add(parent)
    db.flush()
    artwork = IngestFile(
        batch_id=parent.id,
        file_path=str(Path(parent.source_path) / release["source_folder"] / "cover.jpg"),
        file_name="cover.jpg",
        extension=".jpg",
        size_bytes=2048,
        checksum="support-only-cover",
        detected_role="artwork",
        metadata_json={"_discography_album": release},
    )
    db.add(artwork)
    db.commit()
    child_count_before = db.query(IngestBatch).filter(IngestBatch.detected_type == "music_album").count()

    result = execute_split_discography_releases(db, parent.id)
    assert result["created_count"] == 0
    assert "support-only folder" in result["message"]
    assert db.query(IngestBatch).filter(IngestBatch.detected_type == "music_album").count() == child_count_before
    assert db.query(IngestFile).filter(IngestFile.id == artwork.id, IngestFile.batch_id == parent.id).count() == 1

    db.refresh(parent)
    remainder = parent.metadata_json["albums"][0]
    assert remainder["release_decision"] == "unresolved"
    assert remainder["status"] == "support_only_remainder"
    assert remainder["support_only_file_count"] == 1
    assert remainder["support_only_files"] == ["cover.jpg"]
    assert "support_files_without_media_owner" in remainder["warnings"]
    assert parent.metadata_json["discography_split_audit"][-1]["support_only_source_folders"] == ["Artwork Remainder"]
    assert parent.metadata_json["parent_is_drained"] is False
    assert parent.metadata_json["active_parent_file_count"] == 1

def test_failed_materialization_does_not_complete_parent(db) -> None:
    good_release = album_row("Good Candidate", "2024")
    broken_release = album_row("Broken Candidate", "2024")
    parent = IngestBatch(
        source_kind="manual-drop",
        source_path=str(PROJECT_ROOT / ".tmp" / "broken-parent"),
        detected_type="music_discography",
        status="pending_review",
        confidence=0.72,
        metadata_json={
            "type": "music_discography",
            "artist": "Broken Artist",
            "albums": [],
            "album_count": 2,
            "release_count": 2,
        },
    )
    db.add(parent)
    db.flush()

    good_file = add_album_file(parent, good_release, 1, role="discography_track")
    db.flush()
    good_candidate = add_candidate(db, parent.id, good_release, [good_file])
    broken_candidate = MediaIdentityCandidate(
        batch_id=parent.id,
        candidate_key="music:broken:no-files",
        candidate_media_type="music",
        candidate_title=broken_release["album"],
        candidate_primary_creator=broken_release["artist"],
        candidate_year=broken_release["year"],
        candidate_confidence=0.8,
        identity_evidence_json={},
    )
    db.add(broken_candidate)
    db.flush()
    approve_candidate(db, parent.id, good_candidate.id)
    approve_candidate(db, parent.id, broken_candidate.id)
    db.commit()

    try:
        materialize_approved_candidates(db, parent.id)
    except ValueError as exc:
        assert "Candidate has no scoped files available" in str(exc)
    else:
        raise AssertionError("Expected materialization failure")

    db.refresh(parent)
    assert parent.status == "pending_review"
    assert db.query(IngestFile).filter(IngestFile.batch_id == parent.id, IngestFile.id == good_file.id).count() == 1
    child_batches = db.query(IngestBatch).all()
    assert not any(
        isinstance(batch.metadata_json, dict)
        and batch.metadata_json.get("source_candidate_id") in {good_candidate.id, broken_candidate.id}
        for batch in child_batches
    )


def test_discography_release_decisions_leave_remainder_on_parent(db) -> None:
    safe = album_row("Safe Release", "2020") | {"release_decision": "extract_as_child", "include": True}
    review_later = album_row("Needs Later Review", "2021") | {"release_decision": "review_later", "include": False, "lookup_later": True}
    excluded = album_row("Wrong Library", "2022") | {"release_decision": "exclude", "include": False}
    blocked = album_row("Blocked Release", "2023") | {"release_decision": "blocked", "include": False}
    releases = [safe, review_later, excluded, blocked]
    parent = IngestBatch(
        source_kind="manual-drop",
        source_path=str(PROJECT_ROOT / ".tmp" / "mixed-discography"),
        detected_type="music_discography",
        status="pending_review",
        confidence=0.82,
        metadata_json={
            "type": "music_discography",
            "artist": "Mixed Artist",
            "albums": releases,
            "album_count": len(releases),
            "release_count": len(releases),
        },
    )
    db.add(parent)
    db.flush()
    safe_file = add_album_file(parent, safe, 1, role="discography_track")
    review_file = add_album_file(parent, review_later, 2, role="discography_track")
    excluded_file = add_album_file(parent, excluded, 3, role="discography_track")
    blocked_file = add_album_file(parent, blocked, 4, role="discography_track")
    db.commit()

    result = execute_split_discography_releases(db, parent.id)
    assert result["created_count"] == 1
    assert result["parent_review_state"] == "review_in_progress"
    db.refresh(parent)
    assert parent.status == "pending_review"
    assert parent.metadata_json["parent_container_state"] == "partial_parent_container"
    assert parent.metadata_json["child_batch_count"] == 1
    assert parent.metadata_json["active_parent_file_count"] == 3
    assert parent.metadata_json["materialized_child_count"] == 1
    assert parent.metadata_json["remaining_parent_file_count"] == 3
    assert parent.metadata_json["review_later_candidate_count"] == 1
    assert parent.metadata_json["excluded_candidate_count"] == 1
    assert parent.metadata_json["blocked_candidate_count"] == 1
    assert parent.metadata_json["extractable_candidate_count"] == 0
    assert parent.metadata_json["discography_split_audit"][-1]["extracted_source_folders"] == ["Safe Release"]
    assert parent.metadata_json["discography_split_audit"][-1]["review_later_source_folders"] == ["Needs Later Review"]
    assert parent.metadata_json["discography_split_audit"][-1]["excluded_source_folders"] == ["Wrong Library"]
    assert parent.metadata_json["discography_split_audit"][-1]["blocked_source_folders"] == ["Blocked Release"]

    child_id = result["created_child_batch_ids"][0]
    child = db.get(IngestBatch, child_id)
    assert child is not None
    assert db.query(IngestFile).filter(IngestFile.batch_id == child.id).count() == 1
    assert db.query(IngestFile).filter(IngestFile.batch_id == child.id, IngestFile.id == safe_file.id).count() == 1
    assert db.query(IngestFile).filter(IngestFile.batch_id == parent.id, IngestFile.id.in_([review_file.id, excluded_file.id, blocked_file.id])).count() == 3

    summary = build_parent_candidate_summary(db, parent)
    assert summary["is_parent_review_container"] is True
    assert summary["parent_review_state"] == "review_in_progress"
    assert summary["parent_container_state"] == "partial_parent_container"
    assert summary["child_batch_count"] == 1
    assert summary["active_parent_file_count"] == 3
    assert summary["materialized_child_count"] == 1
    assert summary["remaining_candidate_count"] == 3

    parent.status = "approved"
    db.commit()
    moved, errors = move_approved_batches(db)
    assert moved == 0
    assert any("parent" in error.lower() and "container" in error.lower() for error in errors)
    parent.status = "pending_review"
    db.commit()
def test_single_item_batch_stays_normal(db) -> None:
    batch = IngestBatch(
        source_kind="manual-drop",
        source_path=str(PROJECT_ROOT / ".tmp" / "single-album"),
        detected_type="music_album",
        status="pending_review",
        confidence=0.91,
        metadata_json={
            "artist": "Death Cab for Cutie",
            "album": "Transatlanticism",
            "track_count": 11,
        },
    )
    db.add(batch)
    db.commit()

    summary = build_parent_candidate_summary(db, batch)
    assert summary["is_parent_review_container"] is False
    assert summary["needs_materialization"] is False

    display = build_batch_display_fields(batch, summary)
    assert display["media_label"] == "Music Album"
    assert display["primary_name"] == "Death Cab for Cutie"
    assert display["secondary_name"] == "Transatlanticism"
    assert display["item_label"] == "tracks"


def main() -> None:
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    db = Session()
    try:
        test_multi_candidate_parent_is_container(db)
        test_materializes_approved_candidates_once(db)
        test_split_complete_parent_without_candidates_stays_container(db)
        test_split_complete_parent_with_remaining_files_requires_remainder_review(db)
        test_partial_materialization_keeps_unresolved_parent_remainder(db)
        test_split_complete_parent_counts_actual_children_without_history(db)
        test_discography_editor_rows_create_child_batches_without_candidates(db)
        test_support_only_discography_release_stays_on_parent(db)
        test_discography_release_decisions_leave_remainder_on_parent(db)
        test_failed_materialization_does_not_complete_parent(db)
        test_single_item_batch_stays_normal(db)
        print("PASS - AA-QA1-FIX2.2 candidate-member-first materialization verified")
    finally:
        db.close()


if __name__ == "__main__":
    main()
