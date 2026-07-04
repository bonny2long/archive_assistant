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
from app.models.media_metadata import CandidateMember, MediaIdentityCandidate, UniversalIngestionReviewAction  # noqa: E402
from app.services.batch_split import execute_split_candidate  # noqa: E402


def make_album(source_folder: str, artist: str, album: str, year: str = "2005", **extra) -> dict:
    row = {
        "source_folder": source_folder,
        "artist": artist,
        "album_artist": artist,
        "album": album,
        "title": album,
        "year": year,
        "genre": "Hip-Hop",
        "format": "FLAC",
        "release_type": "album",
        "include": True,
    }
    row.update(extra)
    return row


def make_file(batch: IngestBatch, source_folder: str, name: str, role: str, metadata: dict | None = None) -> IngestFile:
    ext = Path(name).suffix.lower()
    ingest_file = IngestFile(
        file_path=str(Path(batch.source_path) / source_folder / name),
        file_name=name,
        extension=ext,
        size_bytes=1024,
        checksum=f"sha-{source_folder}-{name}",
        detected_role=role,
        metadata_json=metadata or {},
    )
    batch.files.append(ingest_file)
    return ingest_file


def audio_meta(album_row: dict, title: str, track: str, disc: str = "1") -> dict:
    return {
        "artist": album_row["artist"],
        "album_artist": album_row["artist"],
        "albumartist": album_row["artist"],
        "album": album_row["album"],
        "title": title,
        "tracknumber": track,
        "discnumber": disc,
        "date": album_row["year"],
        "genre": album_row.get("genre", "Hip-Hop"),
        "format": "FLAC",
        "_discography_album": album_row,
        "embedded_metadata_fields": {
            "albumartist": album_row["artist"],
            "album": album_row["album"],
            "title": title,
            "tracknumber": track,
            "discnumber": disc,
            "date": album_row["year"],
            "genre": album_row.get("genre", "Hip-Hop"),
        },
    }


def asset_meta(album_row: dict) -> dict:
    return {"_discography_album": album_row}


def add_candidate(db, batch: IngestBatch, album_row: dict, files: list[IngestFile], title: str | None = None, artist: str | None = None) -> MediaIdentityCandidate:
    candidate = MediaIdentityCandidate(
        batch_id=batch.id,
        candidate_key=f"music:{album_row['artist']}:{album_row['source_folder']}",
        candidate_media_type="music",
        candidate_title=title or album_row["album"],
        candidate_primary_creator=artist or album_row["artist"],
        candidate_year=album_row.get("year"),
        candidate_confidence=0.9,
        identity_evidence_json={},
    )
    db.add(candidate)
    db.flush()
    for file in files:
        db.add(CandidateMember(
            candidate_id=candidate.id,
            batch_file_id=file.id,
            relative_path=str(Path(file.file_path).name),
            media_class="music_audio" if file.extension == ".flac" else "artwork",
            role_in_candidate="primary",
            sort_key=file.file_name,
            evidence_json={},
        ))
    db.commit()
    db.refresh(candidate)
    return candidate


def split_action(db, batch_id: int, candidate_id: int) -> None:
    db.add(UniversalIngestionReviewAction(
        batch_id=batch_id,
        candidate_id=candidate_id,
        action_type="split_candidate",
        decision_status="active",
        reason="metadata scope regression",
    ))
    db.commit()


def identity_override(db, batch_id: int, candidate_id: int, title: str, artist: str, year: str) -> None:
    db.add(UniversalIngestionReviewAction(
        batch_id=batch_id,
        candidate_id=candidate_id,
        action_type="override_identity",
        override_title=title,
        override_primary_creator=artist,
        override_year=year,
        decision_status="active",
        reason="destination identity regression",
    ))
    db.commit()


def make_parent(db, albums: list[dict], suffix: str) -> IngestBatch:
    batch = IngestBatch(
        source_kind="manual-drop",
        source_path=str(PROJECT_ROOT / ".tmp" / f"scope-{suffix}"),
        detected_type="music_discography",
        status="pending_review",
        confidence=0.8,
        metadata_json={
            "type": "music_discography",
            "artist": "Parent Artist",
            "metadata_assist_version": "scope-test",
            "albums": albums,
            "album_count": len(albums),
            "release_count": len(albums),
        },
    )
    db.add(batch)
    db.flush()
    return batch


def assert_no_non_audio_tracks(metadata: dict) -> None:
    forbidden = (".jpg", ".jpeg", ".png", ".webp", ".txt", ".log", ".cue", ".m3u", ".m3u8")
    for track in metadata.get("tracks", []):
        file_name = str(track.get("file_name") or "").lower()
        title = str(track.get("title") or "").casefold()
        assert not file_name.endswith(forbidden), file_name
        assert title not in {"cover", "folder", "artist"}, title


def test_audio_only_tracks_and_scoped_counts(db) -> None:
    album_row = make_album(
        "Late Registration",
        "Kanye West",
        "Late Registration",
        artwork_count=12,
        artwork_files=["cover.jpg"] * 12,
        tracks=[{"title": "cover", "track_number": "1"}],
        ignored_sidecar_count=99,
    )
    batch = make_parent(db, [album_row], "late-registration")
    audio_one = make_file(batch, album_row["source_folder"], "02. Heard Em Say.flac", "music_audio", audio_meta(album_row, "Heard Em Say", "2"))
    audio_two = make_file(batch, album_row["source_folder"], "13. Diamonds From Sierra Leone.flac", "music_audio", audio_meta(album_row, "Diamonds From Sierra Leone", "13"))
    cover = make_file(batch, album_row["source_folder"], "cover.jpg", "artwork", asset_meta(album_row))
    sidecar = make_file(batch, album_row["source_folder"], "DR6.txt", "metadata_sidecar", asset_meta(album_row))
    db.commit()
    candidate = add_candidate(db, batch, album_row, [audio_one, audio_two, cover, sidecar])
    initial_files = db.query(IngestFile).count()
    split_action(db, batch.id, candidate.id)
    result = execute_split_candidate(db, batch.id, candidate.id)
    child = db.get(IngestBatch, result["child_batch_id"])
    metadata = child.metadata_json

    assert metadata["track_count"] == 2
    assert len(metadata["tracks"]) == 2
    assert_no_non_audio_tracks(metadata)
    assert metadata["artwork_count"] == 1
    assert metadata["artwork_files"] == ["cover.jpg"]
    assert metadata["ignored_sidecar_count"] == 1
    assert metadata["ignored_sidecar_files"] == ["DR6.txt"]
    assert db.query(IngestFile).count() == initial_files


def test_sibling_sidecars_do_not_bleed(db) -> None:
    late = make_album("Late Registration", "Kanye West", "Late Registration")
    grad = make_album("Graduation", "Kanye West", "Graduation", "2007")
    batch = make_parent(db, [late, grad], "siblings")
    late_audio = make_file(batch, late["source_folder"], "01. Wake Up Mr West.flac", "music_audio", audio_meta(late, "Wake Up Mr West", "1"))
    late_cover = make_file(batch, late["source_folder"], "cover.jpg", "artwork", asset_meta(late))
    late_sidecar = make_file(batch, late["source_folder"], "DR6.txt", "metadata_sidecar", asset_meta(late))
    make_file(batch, grad["source_folder"], "cover.jpg", "artwork", asset_meta(grad))
    make_file(batch, grad["source_folder"], "Graduation.m3u", "playlist", asset_meta(grad))
    db.commit()
    candidate = add_candidate(db, batch, late, [late_audio, late_cover, late_sidecar])
    result = execute_split_candidate(db, batch.id, candidate.id)
    child = db.get(IngestBatch, result["child_batch_id"])
    metadata = child.metadata_json
    assert metadata["artwork_files"] == ["cover.jpg"]
    assert metadata["ignored_sidecar_files"] == ["DR6.txt"]
    assert "Graduation.m3u" not in metadata["ignored_sidecar_files"]


def test_destination_uses_clean_identity(db) -> None:
    album_row = make_album("Transatlanticism", "Death Cab for Cutie", "drive-download-003", "2003")
    batch = make_parent(db, [album_row], "destination")
    audio = make_file(batch, album_row["source_folder"], "01 - The New Year.flac", "music_audio", audio_meta(album_row, "The New Year", "1"))
    db.commit()
    candidate = add_candidate(db, batch, album_row, [audio], title="Unknown Album", artist="Unknown Artist")
    identity_override(db, batch.id, candidate.id, "Transatlanticism", "Death Cab For Cutie", "2003")
    result = execute_split_candidate(db, batch.id, candidate.id)
    destination = result["suggested_destination"]
    assert "Death Cab For Cutie" in destination
    assert "2003 - Transatlanticism" in destination
    assert "drive-download" not in destination


def main() -> None:
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    db = Session()
    try:
        test_audio_only_tracks_and_scoped_counts(db)
        test_sibling_sidecars_do_not_bleed(db)
        test_destination_uses_clean_identity(db)
        print("AA-M4D.5.2 Split Child Metadata Scope checks passed.")
    finally:
        db.close()


if __name__ == "__main__":
    main()