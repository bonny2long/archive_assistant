from pathlib import Path

from sqlalchemy import inspect, text
from sqlalchemy.orm import selectinload

from app.core.config import settings
from app.db.session import Base, SessionLocal, engine
from app.models import archive  # noqa: F401
from app.models.archive import IngestBatch
from app.services.music_metadata import build_suggested_metadata, suggest_music_destination


def _backfill_suggested_metadata() -> None:
    with SessionLocal() as db:
        batches = (
            db.query(IngestBatch)
            .options(selectinload(IngestBatch.files))
            .filter(
                IngestBatch.detected_type == "music_album",
                IngestBatch.suggested_metadata.is_(None),
                IngestBatch.status != "moved",
            )
            .all()
        )
        for batch in batches:
            detected = batch.metadata_json or {}
            track_metadata = [ingest_file.metadata_json or {} for ingest_file in batch.files]
            suggestion = build_suggested_metadata(
                Path(batch.source_path),
                track_metadata,
                detected,
            )
            batch.suggested_metadata = suggestion
            if suggestion:
                destination_metadata = {
                    "albumartist": suggestion.get("artist") or detected.get("artist"),
                    "album": suggestion.get("album") or detected.get("album"),
                    "date": suggestion.get("year") or detected.get("year"),
                    "extension": str(detected.get("format", "MP3")).lower(),
                }
                batch.suggested_destination = str(
                    suggest_music_destination(
                        destination_metadata,
                        settings.music_flac_dir,
                        settings.music_mp3_dir,
                    )
                )
        db.commit()


def init_db():
    Base.metadata.create_all(bind=engine)
    columns = {column["name"] for column in inspect(engine).get_columns("ingest_batches")}
    with engine.begin() as connection:
        if "suggested_metadata" not in columns:
            connection.execute(text("ALTER TABLE ingest_batches ADD COLUMN suggested_metadata JSON"))
        if "metadata_confirmed" not in columns:
            connection.execute(
                text(
                    "ALTER TABLE ingest_batches "
                    "ADD COLUMN metadata_confirmed BOOLEAN NOT NULL DEFAULT 0"
                )
            )
    _backfill_suggested_metadata()
    print("Database initialized.")


if __name__ == "__main__":
    init_db()
