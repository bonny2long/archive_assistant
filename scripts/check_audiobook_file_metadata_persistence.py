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
from app.models.archive import IngestBatch, IngestFile  # noqa: E402,F401
from app.services import scanner  # noqa: E402
from app.services.audiobook_metadata import build_audiobook_file_metadata  # noqa: E402


def main() -> None:
    root = PROJECT_ROOT / ".tmp"
    root.mkdir(exist_ok=True)
    source = root / "Star Wars Darth Bane Trilogy.mp3"
    db_path = root / "audiobook-metadata-check.db"
    report_path = root / "audiobook-metadata-report.json"
    for path in (source, db_path, report_path):
        if path.exists():
            path.unlink()
    try:
        audio = source
        audio.write_bytes(b"not a real mp3, but scanner must persist read-only evidence")

        file_metadata = build_audiobook_file_metadata(audio)
        assert file_metadata["media_kind"] == "audiobook_audio"
        assert file_metadata["metadata_contract"]["version"]
        assert "embedded_metadata" in file_metadata
        assert file_metadata["embedded_technical"]["file_extension"] == ".mp3"

        engine = create_engine(f"sqlite:///{db_path}", connect_args={"check_same_thread": False})
        Base.metadata.create_all(engine)
        Session = sessionmaker(bind=engine)
        db = Session()

        original_reports = scanner.settings.reports_dir
        original_audiobooks = scanner.settings.audiobooks_dir
        scanner.settings.reports_dir = root
        scanner.settings.audiobooks_dir = root / "Audiobooks" / "Library"
        try:
            batch = scanner._create_audiobook_batch(db, source)
            assert batch is not None
            rows = db.query(IngestFile).filter(IngestFile.batch_id == batch.id).all()
            audio_rows = [row for row in rows if row.detected_role == "audiobook_audio"]
            artwork_rows = [row for row in rows if row.detected_role == "audiobook_artwork"]
            assert len(audio_rows) == 1
            assert audio_rows[0].metadata_json is not None
            assert audio_rows[0].metadata_json["media_kind"] == "audiobook_audio"
            assert audio_rows[0].metadata_json["metadata_contract"]["version"]
            assert "embedded_metadata" in audio_rows[0].metadata_json
            assert audio_rows[0].metadata_json["embedded_technical"]["file_extension"] == ".mp3"
            assert artwork_rows == []
        finally:
            scanner.settings.reports_dir = original_reports
            scanner.settings.audiobooks_dir = original_audiobooks
            db.close()
            engine.dispose()
    finally:
        for path in (source, db_path, report_path):
            if path.exists():
                path.unlink()
        for path in root.glob("ingest_report_*.json"):
            path.unlink()

    print("Audiobook file metadata persistence checks passed.")


if __name__ == "__main__":
    main()