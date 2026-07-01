from pathlib import Path

from sqlalchemy import inspect, text
from sqlalchemy.orm import selectinload

from app.core.config import settings
from app.db.session import Base, SessionLocal, engine
from app.models import archive  # noqa: F401
from app.models import media_metadata  # noqa: F401
from app.models.archive import IngestBatch
from app.services.music_metadata import build_suggested_metadata, suggest_music_destination
from app.services.video_metadata import safe_movie_path_part, safe_tv_path_part
from app.services.metadata_database import seed_genre_taxonomy


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


def _backfill_movie_destinations() -> None:
    with SessionLocal() as db:
        batches = (
            db.query(IngestBatch)
            .filter(
                IngestBatch.detected_type == "video_movie",
                IngestBatch.status.notin_(["moved", "merged"]),
            )
            .all()
        )
        for batch in batches:
            metadata = batch.metadata_json or {}
            title = str(metadata.get("title") or "Unknown Movie")
            year = str(metadata.get("year") or "")[:4]
            folder = safe_movie_path_part(
                f"{year or 'Unknown Year'} - {title}"
            )
            batch.suggested_destination = str(settings.movies_dir / folder)
        db.commit()


def _backfill_tv_destinations() -> None:
    with SessionLocal() as db:
        batches = (
            db.query(IngestBatch)
            .filter(
                IngestBatch.detected_type == "video_tv_show",
                IngestBatch.status.notin_(["moved", "merged"]),
            )
            .all()
        )
        for batch in batches:
            metadata = batch.metadata_json or {}
            show_title = str(
                metadata.get("show_title") or "Unknown TV Show"
            )
            batch.suggested_destination = str(
                settings.tv_dir / safe_tv_path_part(show_title)
            )
        db.commit()


def init_db():
    for directory in (
        settings.movies_dir,
        settings.movies_metadata_dir,
        settings.tv_dir,
        settings.tv_metadata_dir,
        settings.books_dir / "Metadata",
        settings.audiobooks_dir,
        settings.data_root / "Audiobooks" / "Metadata",
    ):
        directory.mkdir(parents=True, exist_ok=True)
    Base.metadata.create_all(bind=engine)
    with SessionLocal() as db:
        seed_genre_taxonomy(db)
        db.commit()
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
    _backfill_movie_destinations()
    _backfill_tv_destinations()
    print("Database initialized.")


if __name__ == "__main__":
    init_db()
