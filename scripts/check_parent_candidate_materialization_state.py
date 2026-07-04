#!/usr/bin/env python3
"""AA-QA1-FIX1 parent candidate materialization state regression."""

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

from app.db.session import Base  # noqa: E402
from app.models.archive import IngestBatch  # noqa: E402
from app.models.media_metadata import MediaIdentityCandidate, UniversalIngestionReviewAction  # noqa: E402
from app.services.batch_display import build_batch_display_fields  # noqa: E402
from app.services.parent_candidate_materialization import build_parent_candidate_summary  # noqa: E402


def add_candidate(db, batch_id: int, title: str, artist: str, year: str) -> MediaIdentityCandidate:
    candidate = MediaIdentityCandidate(
        batch_id=batch_id,
        candidate_key=f"music:{artist}:{title}".casefold(),
        candidate_media_type="music",
        candidate_title=title,
        candidate_primary_creator=artist,
        candidate_year=year,
        candidate_confidence=0.93,
        identity_evidence_json={"source_folder": title},
    )
    db.add(candidate)
    db.flush()
    return candidate


def approve_candidate(db, batch_id: int, candidate_id: int) -> None:
    db.add(UniversalIngestionReviewAction(
        batch_id=batch_id,
        candidate_id=candidate_id,
        action_type="approve_candidate",
        decision_status="active",
        reason="QA1-FIX1 materialization regression",
    ))


def test_multi_candidate_parent_is_container(db) -> None:
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
            "albums": [
                {"album": "FWA", "artist": "Lil Wayne", "source_folder": "FWA"},
                {"album": "Funeral", "artist": "Lil Wayne", "source_folder": "Funeral"},
                {"album": "I Am Music", "artist": "Lil Wayne", "source_folder": "I Am Music"},
                {"album": "Rebirth", "artist": "Lil Wayne", "source_folder": "Rebirth"},
            ],
            "album_count": 4,
            "release_count": 4,
        },
    )
    db.add(parent)
    db.flush()

    candidates = [
        add_candidate(db, parent.id, "FWA", "Lil Wayne", "2015"),
        add_candidate(db, parent.id, "Funeral", "Lil Wayne", "2020"),
        add_candidate(db, parent.id, "I Am Music", "Lil Wayne", "2023"),
        add_candidate(db, parent.id, "Rebirth", "Lil Wayne", "2010"),
    ]
    for candidate in candidates:
        approve_candidate(db, parent.id, candidate.id)
    db.commit()

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
        test_single_item_batch_stays_normal(db)
        print("PASS - AA-QA1-FIX1 parent candidate materialization state verified")
    finally:
        db.close()


if __name__ == "__main__":
    main()
