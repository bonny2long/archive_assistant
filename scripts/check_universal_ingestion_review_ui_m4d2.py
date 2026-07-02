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
from app.services.universal_ingestion_review import get_batch_universal_ingestion_review  # noqa: E402

PHASE = "AA-M4D.2 — Universal Ingestion Review API + UI"
DECISIONS = {"safe_group", "split_recommended", "merge_recommended", "review_required", "blocked_conflict"}
FORBIDDEN = ["delete", "writeback", "beets", "llama", "bm radio", "jellyfin"]


def read(path: str) -> str:
    return (PROJECT_ROOT / path).read_text(encoding="utf-8").casefold()


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


def music_meta(track: str):
    return {
        "artist": "Test Artist",
        "album_artist": "Test Artist",
        "album": "Split Album",
        "title": f"Track {track}",
        "track_number": track,
        "embedded_metadata_fields": {
            "artist": "Test Artist",
            "album_artist": "Test Artist",
            "album": "Split Album",
            "title": f"Track {track}",
            "track_number": track,
        },
    }


def main() -> None:
    schema = read("backend/app/schemas/archive.py")
    routes = read("backend/app/api/routes.py")
    service = read("backend/app/services/universal_ingestion_review.py")
    component = read("frontend/src/components/UniversalIngestionPanel.tsx")
    batch_detail = read("frontend/src/components/BatchDetail.tsx")
    client = read("frontend/src/api/client.ts")
    types = read("frontend/src/types/archive.ts")

    assert "batchuniversalingestionout" in schema
    assert "universalingestionsummaryout" in schema
    assert "/batches/{batch_id}/universal-ingestion" in routes
    assert "get_batch_universal_ingestion_review" in service
    assert "getbatchuniversalingestion" in client
    assert "batchuniversalingestion" in types
    assert "universalingestionpanel" in component
    assert "universalingestionpanel" in batch_detail
    for decision in DECISIONS:
        assert decision in component
        assert decision in service
    for forbidden in FORBIDDEN:
        assert forbidden not in component.replace("no deletion", "")

    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    db = Session()
    try:
        batch = IngestBatch(
            source_kind="manual-drop",
            source_path=str(PROJECT_ROOT / ".tmp" / "m4d2-review"),
            detected_type="music_album",
            status="pending_review",
            confidence=0.5,
            metadata_json={},
        )
        add_file(batch, "drive-download-20260702T010101Z-1-001/01.mp3", music_meta("1"))
        add_file(batch, "drive-download-20260702T010101Z-1-002/02.mp3", music_meta("2"))
        add_file(batch, "drive-download-20260702T010101Z-1-002/book.epub")
        db.add(batch)
        db.commit()
        db.refresh(batch)

        empty = get_batch_universal_ingestion_review(db, batch.id)
        assert empty["analysis_status"] == "not_analyzed"
        assert {"summary", "source_fragments", "candidates", "reconstruction_decisions", "mixed_media_flags", "analysis_status"}.issubset(empty)

        snapshot_universal_ingestion_boundary(db, batch)
        db.commit()
        payload = get_batch_universal_ingestion_review(db, batch.id)
        assert payload["phase"] == PHASE
        assert payload["analysis_status"] == "analyzed"
        assert payload["summary"]["source_fragment_count"] == 2
        assert payload["summary"]["candidate_count"] >= 2
        assert payload["summary"]["member_count"] >= 3
        assert payload["source_fragments"]
        assert payload["candidates"]
        assert payload["reconstruction_decisions"]
        assert payload["mixed_media_flags"]
        assert payload["summary"]["worst_decision"] in DECISIONS
        assert any(candidate["members"] for candidate in payload["candidates"])
    finally:
        db.close()

    print("AA-M4D.2 Universal Ingestion Review API + UI checks passed.")


if __name__ == "__main__":
    main()