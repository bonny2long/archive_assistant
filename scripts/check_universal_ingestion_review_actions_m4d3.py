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
from app.models.archive import IngestBatch, IngestFile  # noqa: E402
from app.services.universal_ingestion import snapshot_universal_ingestion_boundary  # noqa: E402
from app.services.universal_ingestion_review import (  # noqa: E402
    clear_review_action,
    create_or_update_review_action,
    get_batch_universal_ingestion_review,
    list_review_actions_for_batch,
)


def meta(track="1", album="Action Album"):
    fields = {
        "artist": "Action Artist",
        "album_artist": "Action Artist",
        "album": album,
        "title": f"Track {track}",
        "track_number": track,
    }
    return {"embedded_metadata_fields": fields, **fields}


def add_file(batch, relative_path, metadata=None):
    name = Path(relative_path).name
    batch.files.append(IngestFile(
        file_path=str(Path(batch.source_path) / relative_path),
        file_name=name,
        extension=Path(name).suffix.lower(),
        size_bytes=1234,
        checksum=f"sha-{relative_path}",
        detected_role="unknown",
        metadata_json=metadata or {},
    ))


def expect_invalid(func):
    try:
        func()
    except ValueError:
        return
    raise AssertionError("Expected ValueError")


def main() -> None:
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    db = Session()
    try:
        batch = IngestBatch(
            source_kind="manual-drop",
            source_path=str(PROJECT_ROOT / ".tmp" / "m4d3-actions"),
            detected_type="music_album",
            status="pending_review",
            confidence=0.5,
            metadata_json={},
        )
        add_file(batch, "drive-download-20260702T020202Z-1-001/01.mp3", meta("1"))
        add_file(batch, "drive-download-20260702T020202Z-1-002/02.mp3", meta("2"))
        add_file(batch, "drive-download-20260702T020202Z-1-002/book.epub")
        db.add(batch)
        db.commit()
        db.refresh(batch)
        snapshot_universal_ingestion_boundary(db, batch)
        db.commit()

        review = get_batch_universal_ingestion_review(db, batch.id)
        assert review["analysis_status"] == "analyzed"
        candidates = review["candidates"]
        assert len(candidates) >= 2
        candidate_id = candidates[0]["id"]
        other_candidate_id = candidates[1]["id"]

        approved = create_or_update_review_action(db, batch.id, {
            "action_type": "approve_candidate",
            "candidate_id": candidate_id,
            "reason": "User confirmed candidate grouping.",
        })
        assert approved["decision_status"] == "active"
        assert approved["action_type"] == "approve_candidate"

        approved_again = create_or_update_review_action(db, batch.id, {
            "action_type": "approve_candidate",
            "candidate_id": candidate_id,
            "reason": "Updated confirmation note.",
        })
        assert approved_again["id"] == approved["id"]
        assert approved_again["reason"] == "Updated confirmation note."

        review_later = create_or_update_review_action(db, batch.id, {
            "action_type": "mark_review_later",
            "candidate_id": candidate_id,
            "reason": "Lookup later.",
        })
        assert review_later["action_type"] == "mark_review_later"

        media_override = create_or_update_review_action(db, batch.id, {
            "action_type": "override_media_class",
            "candidate_id": candidate_id,
            "target_media_class": "ebook",
            "reason": "User corrected media class.",
        })
        assert media_override["target_media_class"] == "ebook"

        identity_override = create_or_update_review_action(db, batch.id, {
            "action_type": "override_identity",
            "candidate_id": candidate_id,
            "override_title": "Corrected Title",
            "override_primary_creator": "Corrected Creator",
            "override_year": "1999",
            "reason": "User corrected identity.",
        })
        assert identity_override["override_title"] == "Corrected Title"
        assert identity_override["override_primary_creator"] == "Corrected Creator"
        assert identity_override["override_year"] == "1999"

        excluded = create_or_update_review_action(db, batch.id, {
            "action_type": "exclude_from_move_plan",
            "candidate_id": candidate_id,
            "reason": "Do not include in current move plan. This is not deletion.",
        })
        assert excluded["action_type"] == "exclude_from_move_plan"

        blocked = create_or_update_review_action(db, batch.id, {
            "action_type": "block_candidate",
            "candidate_id": other_candidate_id,
            "reason": "Unsafe conflict.",
        })
        assert blocked["action_type"] == "block_candidate"

        split = create_or_update_review_action(db, batch.id, {
            "action_type": "split_candidate",
            "candidate_id": other_candidate_id,
            "reason": "Candidate needs split.",
        })
        assert split["action_type"] == "split_candidate"

        merge = create_or_update_review_action(db, batch.id, {
            "action_type": "merge_candidates",
            "candidate_id": candidate_id,
            "target_candidate_id": other_candidate_id,
            "reason": "User says these belong together.",
        })
        assert merge["target_candidate_id"] == other_candidate_id

        cleared = clear_review_action(db, batch.id, review_later["id"])
        assert cleared["decision_status"] == "cleared"
        active = list_review_actions_for_batch(db, batch.id, active_only=True)
        assert all(action.id != review_later["id"] for action in active)

        payload = get_batch_universal_ingestion_review(db, batch.id)
        assert payload["review_actions"]
        assert payload["summary"]["action_summary"]["active_action_count"] >= 6
        active_candidate = next(item for item in payload["candidates"] if item["id"] == candidate_id)
        assert active_candidate["active_actions"]
        assert any(action["action_type"] == "approve_candidate" for action in active_candidate["active_actions"])

        expect_invalid(lambda: create_or_update_review_action(db, batch.id, {"action_type": "not_real", "candidate_id": candidate_id}))
        expect_invalid(lambda: create_or_update_review_action(db, batch.id, {"action_type": "approve_candidate", "candidate_id": 999999}))
        expect_invalid(lambda: create_or_update_review_action(db, batch.id, {"action_type": "override_media_class", "candidate_id": candidate_id, "target_media_class": "photo"}))
        expect_invalid(lambda: create_or_update_review_action(db, batch.id, {"action_type": "merge_candidates", "candidate_id": candidate_id}))
        expect_invalid(lambda: clear_review_action(db, batch.id, 999999))

        watched_files = [
            PROJECT_ROOT / "backend/app/services/universal_ingestion_review.py",
            PROJECT_ROOT / "frontend/src/components/UniversalIngestionPanel.tsx",
        ]
        forbidden = ["unlink(", "rmtree", "send2trash", "writeback", "beets", "llama", "bm radio", "jellyfin"]
        for path in watched_files:
            source = path.read_text(encoding="utf-8").casefold()
            for token in forbidden:
                assert token not in source, f"Forbidden token {token} found in {path}"

        print("AA-M4D.3 Universal Ingestion Review Actions checks passed.")
    finally:
        db.close()


if __name__ == "__main__":
    main()