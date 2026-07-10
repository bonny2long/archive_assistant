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
from app.models.media_metadata import (  # noqa: E402
    FragmentReconstructionDecision,
    MediaIdentityCandidate,
    MixedMediaFlag,
    SourceFragment,
)
from app.services.universal_review_routing import get_batch_routing_decision  # noqa: E402

failures = []


def check(description, func):
    try:
        func()
        print(f"PASS: {description}")
    except Exception as exc:
        failures.append((description, str(exc)))
        print(f"FAIL: {description} - {exc}")


def make_batch(db, name, analyzed=True):
    batch = IngestBatch(
        source_kind="manual-drop",
        source_path=str(PROJECT_ROOT / ".tmp" / name),
        detected_type="music_discography",
        status="pending_review",
        confidence=0.5,
        metadata_json={},
    )
    db.add(batch)
    db.flush()
    if analyzed:
        db.add(SourceFragment(
            batch_id=batch.id,
            source_root=batch.source_path,
            relative_fragment_path=name,
            fragment_group_key=None,
            fragment_label=name,
            file_count=1,
            media_class_counts_json={"music_audio": 1},
        ))
    return batch


def add_candidate(db, batch, media_type="music", title="Album", creator="Artist", key=None):
    candidate = MediaIdentityCandidate(
        batch_id=batch.id,
        candidate_key=key or f"{media_type}:{creator}:{title}",
        candidate_media_type=media_type,
        candidate_title=title,
        candidate_primary_creator=creator,
        candidate_confidence=0.9,
        identity_evidence_json={},
    )
    db.add(candidate)
    db.flush()
    return candidate


def add_decision(db, batch, candidate, decision):
    db.add(FragmentReconstructionDecision(
        batch_id=batch.id,
        candidate_id=candidate.id,
        decision=decision,
        severity="error" if decision == "blocked_conflict" else "review",
        score=0.5,
        reasons_json=[decision],
        conflict_flags_json=[],
        recommended_action="review",
    ))


def add_flag(db, batch, flag_type, severity="review"):
    db.add(MixedMediaFlag(
        batch_id=batch.id,
        flag_type=flag_type,
        severity=severity,
        message=flag_type,
        examples_json=[],
    ))


def main():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    db = Session()
    try:
        def music_source_fragment_required():
            batch = make_batch(db, "m4d4-music-source-fragment")
            add_candidate(db, batch, "music")
            db.commit()
            result = get_batch_routing_decision(db, batch.id)
            assert result["decision"] == "universal_review_required"
            assert "source_fragment_group_detected" in result["reasons"]
            assert "music_discography" in result["blocked_editors"]

        def music_ebook_required():
            batch = make_batch(db, "m4d4-ebook")
            add_candidate(db, batch, "music")
            add_candidate(db, batch, "ebook", title="Book", creator="Author")
            db.commit()
            result = get_batch_routing_decision(db, batch.id)
            assert result["decision"] == "universal_review_required"
            assert "book_or_ebook_in_music_batch" in result["reasons"]
            assert "music_discography" in result["blocked_editors"]

        def music_audiobook_required():
            batch = make_batch(db, "m4d4-audiobook")
            add_candidate(db, batch, "music")
            add_candidate(db, batch, "audiobook", title="Audio Book", creator="Author")
            db.commit()
            result = get_batch_routing_decision(db, batch.id)
            assert result["decision"] == "universal_review_required"
            assert "audiobook_in_music_batch" in result["reasons"]

        def blocked_conflict():
            batch = make_batch(db, "m4d4-blocked")
            candidate = add_candidate(db, batch, "music")
            add_decision(db, batch, candidate, "blocked_conflict")
            db.commit()
            result = get_batch_routing_decision(db, batch.id)
            assert result["decision"] == "blocked_conflict"
            assert result["allowed_editors"] == ["universal"]
            assert "music_discography" in result["blocked_editors"]

        def fragment_required():
            batch = make_batch(db, "m4d4-fragment")
            add_candidate(db, batch, "music")
            add_flag(db, batch, "source_fragment_group_detected", "warning")
            db.commit()
            result = get_batch_routing_decision(db, batch.id)
            assert result["decision"] == "universal_review_required"
            assert "source_fragment_group_detected" in result["reasons"]

        def review_required_routes_to_universal():
            batch = make_batch(db, "m4d4-review")
            candidate = add_candidate(db, batch, "music")
            add_decision(db, batch, candidate, "review_required")
            db.commit()
            result = get_batch_routing_decision(db, batch.id)
            assert result["decision"] == "universal_review_required"
            assert "reconstruction_review_required" in result["reasons"]
            assert "source_fragment_group_detected" in result["reasons"]

        def chunk_identity():
            batch = make_batch(db, "m4d4-chunk")
            add_candidate(db, batch, "music", title="drive-download-20260628T012539Z-3-001", creator="Artist")
            db.commit()
            result = get_batch_routing_decision(db, batch.id)
            assert "source_folder_name_used_as_identity" in result["reasons"]
            assert result["summary"]["chunk_identity_candidate_count"] == 1

        def not_analyzed():
            batch = make_batch(db, "m4d4-no-analysis", analyzed=False)
            db.commit()
            result = get_batch_routing_decision(db, batch.id)
            assert result["decision"] == "not_analyzed"
            assert result["requires_snapshot"] is True

        def not_analyzed_allows_snapshot_path():
            batch = make_batch(db, "m4d4-allowed-editors", analyzed=False)
            add_candidate(db, batch, "music")
            db.commit()
            result = get_batch_routing_decision(db, batch.id)
            assert result["decision"] == "not_analyzed"
            assert result["blocked_editors"] == []

        def blocked_editors_for_required():
            batch = make_batch(db, "m4d4-required-blocked")
            add_candidate(db, batch, "music")
            add_candidate(db, batch, "tv", title="Show", creator=None)
            db.commit()
            result = get_batch_routing_decision(db, batch.id)
            assert result["decision"] == "universal_review_required"
            assert "music_discography" in result["blocked_editors"]

        check("Music source-fragment batch -> universal_review_required", music_source_fragment_required)
        check("Music + ebook batch -> universal_review_required", music_ebook_required)
        check("Music + audiobook batch -> universal_review_required", music_audiobook_required)
        check("Blocked conflict decision -> blocked_conflict routing", blocked_conflict)
        check("Source fragment group flag -> universal_review_required", fragment_required)
        check("Review-required reconstruction with source fragment -> universal_review_required", review_required_routes_to_universal)
        check("Chunk-derived candidate identity is flagged", chunk_identity)
        check("No analysis -> not_analyzed", not_analyzed)
        check("No analysis without source identity remains not_analyzed", not_analyzed_allows_snapshot_path)
        check("universal_review_required blocks music_discography", blocked_editors_for_required)
    finally:
        db.close()

    if failures:
        print()
        for description, reason in failures:
            print(f"FAIL: {description} - {reason}")
        raise SystemExit(1)


if __name__ == "__main__":
    main()