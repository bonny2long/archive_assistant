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
from app.services.metadata_database import seed_genre_taxonomy, snapshot_batch_metadata  # noqa: E402
from app.services.metadata_quality_gate import get_batch_metadata_quality  # noqa: E402


def metadata(genre, *, artist="Artist", albumartist="Artist", title="Title"):
    fields = {
        "genre": genre,
        "artist": artist,
        "album_artist": albumartist,
        "album": "Album",
        "title": title,
        "track_number": "1",
    }
    fields = {key: value for key, value in fields.items() if value is not None}
    return {
        "genre": genre,
        "artist": artist,
        "albumartist": albumartist,
        "album": "Album",
        "title": title,
        "tracknumber": "1",
        "confidence": 0.9,
        "metadata_quality": "good",
        "embedded_metadata": {"read_ok": True, "fields": fields, "technical": {}, "warnings": []},
        "embedded_metadata_fields": fields,
    }


def add_file(batch, name, data):
    batch.files.append(IngestFile(
        file_path=str(PROJECT_ROOT / ".tmp" / name),
        file_name=name,
        extension=".mp3",
        size_bytes=100,
        checksum=name,
        detected_role="music_track",
        metadata_json=data,
    ))


def main() -> None:
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    db = Session()
    try:
        seed_genre_taxonomy(db)
        batch = IngestBatch(source_path=str(PROJECT_ROOT / ".tmp" / "m4d"), detected_type="music_album")
        add_file(batch, "clean.mp3", metadata("Hip-Hop", artist="OutKast", albumartist="OutKast", title="Rosa Parks"))
        add_file(batch, "review.mp3", metadata("Alienwave", artist="A", albumartist="A", title="Unknown Genre"))
        add_file(batch, "blocked.mp3", metadata("Hip-Hop", artist=None, albumartist=None, title=None))
        old = IngestBatch(source_path="old", detected_type="video_movie", status="pending_review")
        db.add_all([batch, old])
        db.commit()
        db.refresh(batch)
        db.refresh(old)

        snapshot_batch_metadata(db, batch)
        db.commit()
        result = get_batch_metadata_quality(db, batch.id)
        assert result["batch_id"] == batch.id
        assert result["total_files"] == 3
        assert result["approved_ready_count"] == 1
        assert result["review_required_count"] == 1
        assert result["blocked_count"] == 1
        assert result["worst_decision"] == "blocked"
        assert len(result["items"]) == 3
        item_by_name = {item["file_name"]: item for item in result["items"]}
        assert item_by_name["clean.mp3"]["decision"] == "approved_ready"
        assert item_by_name["review.mp3"]["decision"] == "review_required"
        assert item_by_name["blocked.mp3"]["decision"] == "blocked"
        assert item_by_name["clean.mp3"]["profile"]["artist"] == "OutKast"
        assert isinstance(item_by_name["review.mp3"]["review_flags"], list)
        assert "unmapped_genre" in result["flag_counts"]

        old_result = get_batch_metadata_quality(db, old.id)
        assert old_result["batch_id"] == old.id
        assert old_result["total_files"] == 0
        assert old_result["items"] == []
    finally:
        db.close()
        engine.dispose()

    print("M4D metadata review UI backend checks passed.")


if __name__ == "__main__":
    main()
