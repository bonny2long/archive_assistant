import os
import subprocess
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
from app.models.media_metadata import MediaIdentityCandidate, UniversalIngestionReviewAction  # noqa: E402
from app.services.batch_split import execute_split_candidate  # noqa: E402


def album(title: str, artist: str, source_folder: str, year: str = "2026") -> dict:
    return {
        "album": title,
        "title": title,
        "artist": artist,
        "album_artist": artist,
        "year": year,
        "source_folder": source_folder,
        "track_count": 2,
    }


def add_album_files(batch: IngestBatch, release: dict, count: int = 2) -> None:
    source_folder = release["source_folder"]
    for index in range(1, count + 1):
        name = f"{index:02d} - Track {index}.mp3"
        batch.files.append(IngestFile(
            file_path=str(Path(batch.source_path) / source_folder / name),
            file_name=name,
            extension=".mp3",
            size_bytes=4096,
            checksum=f"sha-{source_folder}-{index}",
            detected_role="audio_track",
            metadata_json={
                "artist": release["artist"],
                "album": release["album"],
                "title": f"Track {index}",
                "track_number": str(index),
                "_discography_album": release,
            },
        ))


def add_candidate(batch_id: int, release: dict) -> MediaIdentityCandidate:
    return MediaIdentityCandidate(
        batch_id=batch_id,
        candidate_key=f"music:{release['artist']}:{release['source_folder']}",
        candidate_media_type="music",
        candidate_title=release["album"],
        candidate_primary_creator=release["artist"],
        candidate_year=release.get("year"),
        candidate_confidence=0.91,
        identity_evidence_json={"source_folder": release["source_folder"]},
    )


def add_split_action(db, batch_id: int, candidate_id: int) -> UniversalIngestionReviewAction:
    action = UniversalIngestionReviewAction(
        batch_id=batch_id,
        candidate_id=candidate_id,
        action_type="split_candidate",
        decision_status="active",
        reason="Regression split request",
    )
    db.add(action)
    db.commit()
    db.refresh(action)
    return action


def make_discography(db, releases: list[dict]) -> tuple[IngestBatch, list[MediaIdentityCandidate]]:
    batch = IngestBatch(
        source_kind="manual-drop",
        source_path=str(PROJECT_ROOT / ".tmp" / "m4d5-discography"),
        detected_type="music_discography",
        status="pending_review",
        confidence=0.82,
        metadata_json={
            "type": "music_discography",
            "artist": "Mixed Discography",
            "albums": releases,
            "album_count": len(releases),
            "release_count": len(releases),
        },
    )
    for release in releases:
        add_album_files(batch, release)
    db.add(batch)
    db.commit()
    db.refresh(batch)

    candidates = [add_candidate(batch.id, release) for release in releases]
    db.add_all(candidates)
    db.commit()
    for candidate in candidates:
        db.refresh(candidate)
    return batch, candidates


def expect_value_error(func) -> None:
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
        releases = [
            album("First Album", "Artist One", "artist-one-first-album", "2020"),
            album("Second Album", "Artist Two", "artist-two-second-album", "2021"),
            album("Third Album", "Artist Three", "artist-three-third-album", "2022"),
        ]
        parent, candidates = make_discography(db, releases)
        initial_file_count = db.query(IngestFile).count()
        assert initial_file_count == 6

        override = UniversalIngestionReviewAction(
            batch_id=parent.id,
            candidate_id=candidates[0].id,
            action_type="override_identity",
            override_title="First Album",
            override_primary_creator="Artist One",
            override_year="2020",
            decision_status="active",
            reason="Workspace identity correction",
        )
        db.add(override)
        db.commit()

        action = add_split_action(db, parent.id, candidates[0].id)
        result = execute_split_candidate(db, parent.id, candidates[0].id)
        assert result["child_detected_type"] == "music_album"
        assert result["child_status"] == "pending_review"
        assert result["moved_file_count"] == 2
        assert "Discographies" not in (result["suggested_destination"] or "")
        assert result["artist"] == "Artist One"
        assert result["album"] == "First Album"
        assert db.query(IngestFile).count() == initial_file_count

        db.refresh(action)
        assert action.decision_status == "applied"
        assert action.applied_at is not None

        child = db.get(IngestBatch, result["child_batch_id"])
        assert child is not None
        assert child.detected_type == "music_album"
        assert child.metadata_json["split_from_batch_id"] == parent.id
        assert db.query(IngestFile).filter(IngestFile.batch_id == child.id).count() == 2

        db.refresh(parent)
        assert parent.status == "pending_review"
        assert len(parent.metadata_json["albums"]) == 2
        assert len(parent.metadata_json["split_history"]) == 1
        assert db.query(IngestFile).filter(IngestFile.batch_id == parent.id).count() == 4

        add_split_action(db, parent.id, candidates[1].id)
        second = execute_split_candidate(db, parent.id, candidates[1].id)
        assert second["moved_file_count"] == 2
        db.refresh(parent)
        assert parent.status == "pending_review"
        assert len(parent.metadata_json["albums"]) == 1

        add_split_action(db, parent.id, candidates[2].id)
        third = execute_split_candidate(db, parent.id, candidates[2].id)
        assert third["moved_file_count"] == 2
        db.refresh(parent)
        assert parent.status == "split_complete"
        assert parent.metadata_json["albums"] == []
        assert len(parent.metadata_json["split_history"]) == 3
        assert db.query(IngestFile).count() == initial_file_count
        assert db.query(IngestBatch).filter(IngestBatch.detected_type == "music_album").count() == 3

        non_discography = IngestBatch(
            source_kind="manual-drop",
            source_path=str(PROJECT_ROOT / ".tmp" / "m4d5-album"),
            detected_type="music_album",
            status="pending_review",
            confidence=0.5,
            metadata_json={},
        )
        db.add(non_discography)
        db.commit()
        expect_value_error(lambda: execute_split_candidate(db, non_discography.id, candidates[0].id))
        expect_value_error(lambda: execute_split_candidate(db, parent.id, 999999))

        completed = subprocess.run(
            [sys.executable, str(PROJECT_ROOT / "scripts" / "check_universal_ingestion_review_actions_m4d3.py")],
            check=True,
            capture_output=True,
            text=True,
        )
        assert "checks passed" in completed.stdout

        print("AA-M4D.5 Multi-Artist Discography Split checks passed.")
    finally:
        db.close()


if __name__ == "__main__":
    main()