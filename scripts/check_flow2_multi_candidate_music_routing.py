"""AA-FLOW2 multi-candidate music routing regression."""

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

from app.api.routes import approve_batch  # noqa: E402
from app.db.session import Base  # noqa: E402
from app.models.archive import IngestBatch, IngestFile  # noqa: E402
from app.models.media_metadata import (  # noqa: E402
    CandidateMember,
    MediaIdentityCandidate,
    SourceFragment,
    UniversalIngestionReviewAction,
)
from app.services.approved_candidate_materialization import materialize_approved_candidates  # noqa: E402
from app.services.parent_candidate_materialization import build_parent_candidate_summary  # noqa: E402
from app.services.universal_review_routing import get_batch_routing_decision  # noqa: E402


def make_file(batch: IngestBatch, album: str, year: str, index: int) -> IngestFile:
    name = f"{index:02d} - Track {index}.flac"
    return IngestFile(
        batch_id=batch.id,
        file_path=str(Path(batch.source_path) / album / name),
        file_name=name,
        extension=".flac",
        size_bytes=4096,
        checksum=f"flow2-{album}-{index}",
        detected_role="music_audio",
        metadata_json={
            "artist": "Lil Wayne",
            "album_artist": "Lil Wayne",
            "albumartist": "Lil Wayne",
            "album": album,
            "title": f"Track {index}",
            "tracknumber": str(index),
            "date": year,
            "format": "FLAC",
            "embedded_metadata_fields": {
                "artist": "Lil Wayne",
                "album_artist": "Lil Wayne",
                "album": album,
                "title": f"Track {index}",
                "track_number": str(index),
                "year": year,
            },
        },
    )


def add_candidate(db, batch: IngestBatch, album: str, year: str, files: list[IngestFile]) -> MediaIdentityCandidate:
    candidate = MediaIdentityCandidate(
        batch_id=batch.id,
        candidate_key=f"music:lil-wayne:{album}".casefold(),
        candidate_media_type="music",
        candidate_title=album,
        candidate_primary_creator="Lil Wayne",
        candidate_year=year,
        candidate_confidence=0.94,
        identity_evidence_json={"album": album, "artist": "Lil Wayne"},
    )
    db.add(candidate)
    db.flush()
    for file in files:
        db.add(CandidateMember(
            candidate_id=candidate.id,
            batch_file_id=file.id,
            relative_path=f"{album}/{file.file_name}",
            media_class="music_audio",
            role_in_candidate="primary",
            sort_key=file.file_name,
            evidence_json={"album": album},
        ))
    db.add(UniversalIngestionReviewAction(
        batch_id=batch.id,
        candidate_id=candidate.id,
        action_type="approve_candidate",
        decision_status="active",
        reason="AA-FLOW2 regression approved candidate",
    ))
    return candidate


def make_source_music_batch(db) -> tuple[IngestBatch, list[MediaIdentityCandidate]]:
    batch = IngestBatch(
        source_kind="manual-drop",
        source_path=str(PROJECT_ROOT / ".tmp" / "drive-download-20260628T012539Z-3-010"),
        detected_type="music_album",
        status="pending_review",
        confidence=0.71,
        metadata_json={
            "artist": "drive-download-20260628T012539Z-3-010",
            "albumartist": "drive-download-20260628T012539Z-3-010",
            "album": "drive-download-20260628T012539Z-3-010",
            "track_count": 4,
            "format": "FLAC",
        },
        suggested_metadata={
            "artist": "drive-download-20260628T012539Z-3-010",
            "album": "drive-download-20260628T012539Z-3-010",
        },
        suggested_destination="Music/Library/FLAC/drive-download-20260628T012539Z-3-010/Unknown",
    )
    db.add(batch)
    db.flush()
    db.add(SourceFragment(
        batch_id=batch.id,
        source_root=batch.source_path,
        relative_fragment_path="drive-download-20260628T012539Z-3-010",
        fragment_group_key="drive-download-20260628T012539Z-3-010",
        fragment_label="drive-download-20260628T012539Z-3-010",
        file_count=4,
        media_class_counts_json={"music_audio": 4},
    ))

    releases = [("FWA", "2015"), ("Funeral", "2020")]
    candidates: list[MediaIdentityCandidate] = []
    for index, (album, year) in enumerate(releases, start=1):
        files = [make_file(batch, album, year, index), make_file(batch, album, year, index + 2)]
        db.add_all(files)
        db.flush()
        candidates.append(add_candidate(db, batch, album, year, files))
    db.commit()
    db.refresh(batch)
    return batch, candidates


def test_music_source_routes_to_universal_review(db) -> None:
    batch, _candidates = make_source_music_batch(db)
    routing = get_batch_routing_decision(db, batch.id, target_editor="music_album")
    assert routing["decision"] == "universal_review_required"
    assert "music_album" in routing["blocked_editors"]
    assert "universal" in routing["allowed_editors"]
    assert "multiple_candidate_groups" in routing["reasons"]
    assert "multiple_embedded_album_values" in routing["reasons"]
    assert "source_fragment_group_detected" in routing["reasons"]
    assert "source_folder_name_used_as_identity" in routing["reasons"]
    assert routing["summary"]["candidate_count"] == 2
    assert routing["summary"]["source_fragment_count"] == 1
    assert routing["summary"]["embedded_album_value_count"] == 2
    assert routing["summary"]["source_identity_risk"] is True

    summary = build_parent_candidate_summary(db, batch)
    assert summary["is_parent_review_container"] is True
    assert summary["candidate_group_count"] == 2
    assert summary["approved_candidate_count"] == 2
    assert summary["needs_materialization"] is True
    assert summary["approval_allowed"] is False
    assert summary["move_ready"] is False

    response = approve_batch(batch.id, db)
    assert response.status == "pending_review"
    assert "approval" in response.message.lower() or "child batches" in response.message.lower()

    result = materialize_approved_candidates(db, batch.id)
    assert result["created_count"] == 2
    assert result["parent_review_state"] == "split_complete"
    children = [db.get(IngestBatch, child_id) for child_id in result["created_child_batch_ids"]]
    assert {child.metadata_json["album"] for child in children if child is not None} == {"FWA", "Funeral"}
    assert all(child.detected_type == "music_album" for child in children if child is not None)
    assert all(child.status == "pending_review" for child in children if child is not None)
    assert all("drive-download" not in child.metadata_json["artist"] for child in children if child is not None)
    assert all("Music" in (child.suggested_destination or "") and "FLAC" in (child.suggested_destination or "") for child in children if child is not None)

    db.refresh(batch)
    parent_after = build_parent_candidate_summary(db, batch)
    assert parent_after["parent_is_drained"] is True
    assert parent_after["move_ready"] is False


def test_single_music_album_stays_music_editor_allowed(db) -> None:
    batch = IngestBatch(
        source_kind="manual-drop",
        source_path=str(PROJECT_ROOT / ".tmp" / "single-album"),
        detected_type="music_album",
        status="pending_review",
        confidence=0.95,
        metadata_json={"artist": "Death Cab for Cutie", "album": "Transatlanticism", "track_count": 11},
        suggested_destination="Music/Library/FLAC/Death Cab for Cutie/2003 - Transatlanticism",
    )
    db.add(batch)
    db.flush()
    db.add(make_file(batch, "Transatlanticism", "2003", 1))
    db.commit()
    routing = get_batch_routing_decision(db, batch.id, target_editor="music_album")
    assert routing["decision"] == "not_analyzed"

    summary = build_parent_candidate_summary(db, batch)
    assert summary["is_parent_review_container"] is False
    assert summary["needs_materialization"] is False


def main() -> None:
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    db = Session()
    try:
        test_music_source_routes_to_universal_review(db)
        test_single_music_album_stays_music_editor_allowed(db)
        print("PASS - AA-FLOW2 multi-candidate music routing verified")
    finally:
        db.close()


if __name__ == "__main__":
    main()