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
from app.models.media_metadata import CandidateMember, MediaIdentityCandidate, UniversalIngestionReviewAction  # noqa: E402
from app.services.batch_split import execute_split_candidate  # noqa: E402


def album(title: str, artist: str, source_folder: str, year: str = "2026") -> dict:
    return {
        "album": title,
        "title": title,
        "artist": artist,
        "album_artist": artist,
        "year": year,
        "source_folder": source_folder,
        "genre": "Alternative",
        "track_count": 2,
    }


def add_album_files(batch: IngestBatch, release: dict, count: int = 2) -> list[IngestFile]:
    source_folder = release["source_folder"]
    created = []
    for index in range(1, count + 1):
        name = f"{index:02d} - Track {index}.mp3"
        ingest_file = IngestFile(
            file_path=str(Path(batch.source_path) / source_folder / name),
            file_name=name,
            extension=".mp3",
            size_bytes=4096,
            checksum=f"sha-{source_folder}-{index}",
            detected_role="audio_track",
            metadata_json={
                "artist": release["artist"],
                "album_artist": release["artist"],
                "album": release["album"],
                "title": f"Track {index}",
                "track_number": str(index),
                "year": release.get("year"),
                "genre": release.get("genre", "Alternative"),
                "_discography_album": release,
            },
        )
        batch.files.append(ingest_file)
        created.append(ingest_file)
    return created


def add_candidate(
    db,
    batch_id: int,
    title: str,
    artist: str,
    year: str,
    key: str,
    files: list[IngestFile],
    identity_evidence: dict | None = None,
) -> MediaIdentityCandidate:
    candidate = MediaIdentityCandidate(
        batch_id=batch_id,
        candidate_key=key,
        candidate_media_type="music",
        candidate_title=title,
        candidate_primary_creator=artist,
        candidate_year=year,
        candidate_confidence=0.91,
        identity_evidence_json=identity_evidence or {},
    )
    db.add(candidate)
    db.flush()
    for ingest_file in files:
        db.add(CandidateMember(
            candidate_id=candidate.id,
            batch_file_id=ingest_file.id,
            relative_path=str(Path(ingest_file.file_path).name),
            media_class="music_audio",
            role_in_candidate="primary",
            sort_key=ingest_file.file_name,
            evidence_json={},
        ))
    db.commit()
    db.refresh(candidate)
    return candidate


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


def add_identity_override(
    db,
    batch_id: int,
    candidate_id: int,
    title: str,
    artist: str,
    year: str,
) -> UniversalIngestionReviewAction:
    action = UniversalIngestionReviewAction(
        batch_id=batch_id,
        candidate_id=candidate_id,
        action_type="override_identity",
        override_title=title,
        override_primary_creator=artist,
        override_year=year,
        decision_status="active",
        reason="Workspace identity correction",
    )
    db.add(action)
    db.commit()
    db.refresh(action)
    return action


def make_parent(db, releases: list[dict], suffix: str) -> tuple[IngestBatch, dict[str, list[IngestFile]]]:
    batch = IngestBatch(
        source_kind="manual-drop",
        source_path=str(PROJECT_ROOT / ".tmp" / f"m4d5-{suffix}"),
        detected_type="music_discography",
        status="pending_review",
        confidence=0.82,
        metadata_json={
            "type": "music_discography",
            "artist": "Mixed Discography",
            "albums": releases.copy(),
            "album_count": len(releases),
            "release_count": len(releases),
        },
    )
    files_by_folder: dict[str, list[IngestFile]] = {}
    for release in releases:
        files_by_folder[release["source_folder"]] = add_album_files(batch, release)
    db.add(batch)
    db.commit()
    db.refresh(batch)
    return batch, files_by_folder


def expect_value_error(func) -> str:
    try:
        func()
    except ValueError as exc:
        return str(exc)
    raise AssertionError("Expected ValueError")


def test_member_source_folder_wins(db) -> None:
    release = album("The Life Of Pablo", "Kanye West", "The Life Of Pablo [2016]", "2016-02-11")
    parent, files = make_parent(db, [release], "member-source")
    candidate = add_candidate(
        db,
        parent.id,
        "The Life Of Pablo",
        "Kanye West",
        "2016-02-11",
        "music:kanye-west:the-life-of-pablo",
        files[release["source_folder"]],
        identity_evidence={},
    )
    result = execute_split_candidate(db, parent.id, candidate.id)
    child = db.get(IngestBatch, result["child_batch_id"])
    assert child.detected_type == "music_album"
    assert result["moved_file_count"] == 2
    assert db.query(IngestFile).filter(IngestFile.batch_id == child.id).count() == 2


def test_identity_override_does_not_need_album_match(db) -> None:
    release = album("Transatlanticism", "Death Cab for Cutie", "Transatlanticism", "2003")
    parent, files = make_parent(db, [release], "override-source")
    candidate = add_candidate(
        db,
        parent.id,
        "Unknown Album",
        "Unknown Artist",
        "",
        "music:unknown:unknown",
        files[release["source_folder"]],
        identity_evidence={},
    )
    add_identity_override(db, parent.id, candidate.id, "Transatlanticism", "Death Cab For Cutie", "2003")
    result = execute_split_candidate(db, parent.id, candidate.id)
    assert result["album"] == "Transatlanticism"
    assert result["moved_file_count"] == 2


def test_missing_album_row_synthesizes_metadata(db) -> None:
    release = album("Loose Album", "Loose Artist", "Loose Album", "2014")
    parent, files = make_parent(db, [release], "synthesized")
    parent.metadata_json = {**parent.metadata_json, "albums": [], "album_count": 0, "release_count": 0}
    db.commit()
    candidate = add_candidate(
        db,
        parent.id,
        "Loose Album",
        "Loose Artist",
        "2014",
        "music:loose-artist:loose-album",
        files[release["source_folder"]],
        identity_evidence={},
    )
    result = execute_split_candidate(db, parent.id, candidate.id)
    child = db.get(IngestBatch, result["child_batch_id"])
    assert child.metadata_json["synthesized_for_split"] is True
    assert child.metadata_json["split_source_folder"] == "Loose Album"
    assert result["moved_file_count"] == 2


def test_multiple_source_folders_blocks_safely(db) -> None:
    first = album("First Album", "Artist One", "first-folder", "2020")
    second = album("Second Album", "Artist Two", "second-folder", "2021")
    parent, files = make_parent(db, [first, second], "multi-source")
    candidate = add_candidate(
        db,
        parent.id,
        "Broad Candidate",
        "Mixed Artist",
        "2020",
        "music:mixed:broad",
        [*files[first["source_folder"]], *files[second["source_folder"]]],
        identity_evidence={},
    )
    file_count = db.query(IngestFile).count()
    child_count = db.query(IngestBatch).filter(IngestBatch.detected_type == "music_album").count()
    message = expect_value_error(lambda: execute_split_candidate(db, parent.id, candidate.id))
    assert "multiple source folders" in message
    assert db.query(IngestFile).count() == file_count
    assert db.query(IngestBatch).filter(IngestBatch.detected_type == "music_album").count() == child_count
    assert db.query(IngestFile).filter(IngestFile.batch_id == parent.id).count() == 4


def test_full_parent_completion_and_action_applied(db) -> None:
    releases = [
        album("First Album", "Artist One", "artist-one-first-album", "2020"),
        album("Second Album", "Artist Two", "artist-two-second-album", "2021"),
        album("Third Album", "Artist Three", "artist-three-third-album", "2022"),
    ]
    parent, files = make_parent(db, releases, "completion")
    candidates = [
        add_candidate(
            db,
            parent.id,
            release["album"],
            release["artist"],
            release["year"],
            f"music:{release['artist']}:{release['source_folder']}",
            files[release["source_folder"]],
            identity_evidence={},
        )
        for release in releases
    ]
    initial_file_count = db.query(IngestFile).count()

    action = add_split_action(db, parent.id, candidates[0].id)
    result = execute_split_candidate(db, parent.id, candidates[0].id)
    assert result["child_detected_type"] == "music_album"
    assert result["child_status"] == "pending_review"
    assert result["moved_file_count"] == 2
    assert "Discographies" not in (result["suggested_destination"] or "")
    db.refresh(action)
    assert action.decision_status == "applied"
    assert action.applied_at is not None
    db.refresh(parent)
    assert parent.status == "pending_review"
    assert len(parent.metadata_json["albums"]) == 2
    assert len(parent.metadata_json["split_history"]) == 1

    execute_split_candidate(db, parent.id, candidates[1].id)
    db.refresh(parent)
    assert parent.status == "pending_review"
    assert len(parent.metadata_json["albums"]) == 1

    execute_split_candidate(db, parent.id, candidates[2].id)
    db.refresh(parent)
    assert parent.status == "split_complete"
    assert parent.metadata_json["albums"] == []
    assert len(parent.metadata_json["split_history"]) == 3
    assert db.query(IngestFile).count() == initial_file_count


def test_invalid_inputs(db) -> None:
    release = album("Only Album", "Only Artist", "only-folder", "2020")
    parent, files = make_parent(db, [release], "invalid")
    candidate = add_candidate(
        db,
        parent.id,
        release["album"],
        release["artist"],
        release["year"],
        "music:only:only",
        files[release["source_folder"]],
    )
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
    expect_value_error(lambda: execute_split_candidate(db, non_discography.id, candidate.id))
    expect_value_error(lambda: execute_split_candidate(db, parent.id, 999999))


def main() -> None:
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    db = Session()
    try:
        test_member_source_folder_wins(db)
        test_identity_override_does_not_need_album_match(db)
        test_missing_album_row_synthesizes_metadata(db)
        test_multiple_source_folders_blocks_safely(db)
        test_full_parent_completion_and_action_applied(db)
        test_invalid_inputs(db)

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