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
from app.models.media_metadata import MetadataQualityDecision  # noqa: E402
from app.services.metadata_database import seed_genre_taxonomy, snapshot_batch_metadata  # noqa: E402
from app.services.metadata_quality_gate import snapshot_batch_quality_decisions  # noqa: E402


def metadata(genre, *, artist="Artist", albumartist="Artist", album="Album", title="Title", composer=None, work=None, ensemble=None, confidence=0.9):
    fields = {
        "genre": genre,
        "artist": artist,
        "album_artist": albumartist,
        "album": album,
        "title": title,
        "track_number": "1",
        "composer": composer,
        "work": work,
        "ensemble": ensemble,
    }
    fields = {key: value for key, value in fields.items() if value is not None}
    return {
        "genre": genre,
        "artist": artist,
        "albumartist": albumartist,
        "album": album,
        "title": title,
        "tracknumber": "1",
        "composer": composer,
        "work": work,
        "ensemble": ensemble,
        "confidence": confidence,
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


def decisions(db):
    return {row.media_file.file_name: row for row in db.query(MetadataQualityDecision).all()}


def main() -> None:
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    db = Session()
    try:
        seed_genre_taxonomy(db)
        batch = IngestBatch(source_path=str(PROJECT_ROOT / ".tmp" / "Burna Boy Afrobeats"), detected_type="music_album")
        add_file(batch, "clean-hiphop.mp3", metadata("Hip-Hop", artist="OutKast", albumartist="OutKast", title="Rosa Parks"))
        add_file(batch, "clean-reggae.mp3", metadata("Reggae", artist="Bob Marley", albumartist="Bob Marley", title="Jammin"))
        add_file(batch, "clean-afrobeats.mp3", metadata("Afrobeats", artist="Burna Boy", albumartist="Burna Boy", title="Anybody"))
        add_file(batch, "clean-folk.mp3", metadata("Folk", artist="Joni Mitchell", albumartist="Joni Mitchell", title="River"))
        add_file(batch, "clean-idm.mp3", metadata("IDM", artist="Aphex Twin", albumartist="Aphex Twin", title="Xtal"))
        add_file(batch, "world-afro-path.mp3", metadata("World", artist="Burna Boy", albumartist="Burna Boy", title="African Giant"))
        add_file(batch, "unknown-genre.mp3", metadata("Alienwave", artist="A", albumartist="A", title="Unknown Genre"))
        add_file(batch, "mojibake.mp3", metadata("Hip-Hop", artist="A", albumartist="A", title="Bonny \u00c3\u00a2\u00e2\u0082\u00ac\u00e2\u0084\u00a2 Test"))
        add_file(batch, "missing-title.mp3", metadata("Hip-Hop", artist="A", albumartist="A", title=None))
        add_file(batch, "missing-identity.mp3", metadata("Hip-Hop", artist=None, albumartist=None, title=None))
        add_file(batch, "classical-missing-composer.mp3", metadata("Classical", artist="Performer", albumartist="Performer", title="Adagio", composer=None, work="Adagio"))
        add_file(batch, "classical-missing-work.mp3", metadata("Classical", artist="Performer", albumartist="Performer", title="Adagio", composer="Barber", work=None))
        add_file(batch, "classical-clean.mp3", metadata("Classical", artist="Quartet", albumartist="Quartet", title="Movement I", composer="Beethoven", work="String Quartet", ensemble="Quartet"))
        db.add(batch)
        db.commit()
        db.refresh(batch)

        snapshot_batch_metadata(db, batch)
        summary = snapshot_batch_quality_decisions(db, batch.id)
        db.commit()
        rows = decisions(db)

        for name in ("clean-hiphop.mp3", "clean-reggae.mp3", "clean-afrobeats.mp3", "clean-folk.mp3", "clean-idm.mp3"):
            assert rows[name].decision == "approved_ready", (name, rows[name].decision, rows[name].reasons_json)
        assert rows["world-afro-path.mp3"].decision == "review_recommended"
        assert "broad_genre_refined_by_path_evidence" in rows["world-afro-path.mp3"].reasons_json
        assert rows["unknown-genre.mp3"].decision == "review_required"
        assert rows["mojibake.mp3"].decision == "review_required"
        assert rows["missing-title.mp3"].decision == "review_required"
        assert rows["missing-identity.mp3"].decision == "blocked"
        assert rows["classical-missing-composer.mp3"].decision == "review_required"
        assert rows["classical-missing-work.mp3"].decision == "review_required"
        assert rows["classical-clean.mp3"].decision in {"approved_ready", "review_recommended"}
        assert summary["total_files"] == 13
        assert summary["approved_ready_count"] >= 5
        assert summary["review_recommended_count"] >= 1
        assert summary["review_required_count"] >= 4
        assert summary["blocked_count"] == 1
        assert summary["worst_decision"] == "blocked"

        decision_count = db.query(MetadataQualityDecision).count()
        snapshot_batch_metadata(db, batch)
        snapshot_batch_quality_decisions(db, batch.id)
        db.commit()
        assert db.query(MetadataQualityDecision).count() == decision_count
    finally:
        db.close()
        engine.dispose()

    print("M4C metadata quality gate checks passed.")


if __name__ == "__main__":
    main()
