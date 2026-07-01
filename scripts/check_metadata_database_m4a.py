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
from app.models.media_metadata import (  # noqa: E402
    GenreTaxonomy,
    MediaFile,
    MetadataReviewFlag,
    NormalizedMusicProfile,
    RawMediaTag,
)
from app.services.metadata_database import (  # noqa: E402
    UNKNOWN_GENRE_FAMILY,
    genre_family_for,
    seed_genre_taxonomy,
    snapshot_batch_metadata,
)


def track_metadata(
    *,
    artist=None,
    albumartist=None,
    album=None,
    title=None,
    genre=None,
    tracknumber=None,
    composer=None,
):
    fields = {
        key: value
        for key, value in {
            "artist": artist,
            "album_artist": albumartist,
            "album": album,
            "title": title,
            "genre": genre,
            "track_number": tracknumber,
            "composer": composer,
        }.items()
        if value is not None
    }
    metadata = {
        "artist": artist,
        "albumartist": albumartist,
        "album": album,
        "title": title,
        "genre": genre,
        "tracknumber": tracknumber,
        "composer": composer,
        "confidence": 0.91,
        "metadata_quality": "good",
        "embedded_metadata": {
            "read_ok": True,
            "media_type": "music_album",
            "fields": fields,
            "technical": {
                "duration_seconds": 181.5,
                "bitrate": 320000,
                "sample_rate": 44100,
                "container": "mp3",
                "codec": "audio/mpeg",
            },
            "artwork": [{"index": 1, "source": "APIC:", "mime_type": "image/jpeg", "size_bytes": 1234}],
            "warnings": [],
        },
        "embedded_metadata_fields": fields,
        "embedded_technical": {
            "duration_seconds": 181.5,
            "bitrate": 320000,
            "sample_rate": 44100,
            "container": "mp3",
            "codec": "audio/mpeg",
            "embedded_artwork_count": 1,
        },
        "embedded_artwork": [{"index": 1, "source": "APIC:", "mime_type": "image/jpeg", "size_bytes": 1234}],
        "embedded_artwork_count": 1,
        "extraction_warnings": [],
    }
    return {key: value for key, value in metadata.items() if value is not None}


def add_file(batch, name, metadata, checksum):
    batch.files.append(IngestFile(
        file_path=str(PROJECT_ROOT / ".tmp" / name),
        file_name=name,
        extension=".mp3",
        size_bytes=123456,
        checksum=checksum,
        detected_role="music_track",
        metadata_json=metadata,
    ))


def main() -> None:
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    db = Session()
    try:
        seed_genre_taxonomy(db)
        db.commit()
        first_seed_count = db.query(GenreTaxonomy).count()
        seed_genre_taxonomy(db)
        db.commit()
        assert db.query(GenreTaxonomy).count() == first_seed_count
        assert genre_family_for("Hip-Hop", db) == "Hip-Hop / Rap / Mixtape"
        assert genre_family_for("Alienwave", db) == UNKNOWN_GENRE_FAMILY

        batch = IngestBatch(
            source_kind="manual-drop",
            source_path=str(PROJECT_ROOT / ".tmp" / "m4a-metadata-db"),
            detected_type="music_album",
            status="pending_review",
            confidence=0.9,
            metadata_json={"album": "M4A Snapshot Test"},
        )
        add_file(
            batch,
            "01-good.mp3",
            track_metadata(
                artist="OutKast",
                albumartist="OutKast",
                album="Aquemini",
                title="Return of the G",
                genre="Hip-Hop",
                tracknumber="1",
            ),
            "sha-good",
        )
        mojibake_title = "Bonny \u00c3\u00a2\u00e2\u0082\u00ac\u00e2\u0084\u00a2 Test"
        add_file(
            batch,
            "02-review.mp3",
            track_metadata(
                artist="Review Artist",
                albumartist="Review Artist",
                album="Review Album",
                title=mojibake_title,
                genre="Alienwave",
                tracknumber="2",
            ),
            "sha-review",
        )
        add_file(
            batch,
            "03-classical.mp3",
            track_metadata(
                artist=None,
                albumartist=None,
                album="Untitled Classical",
                title="Adagio",
                genre="Classical",
                tracknumber="3",
                composer=None,
            ),
            "sha-classical",
        )
        add_file(
            batch,
            "04-missing-genre.mp3",
            track_metadata(
                artist="Genre Missing",
                albumartist="Genre Missing",
                album="No Genre",
                title="Blank Genre",
                genre=None,
                tracknumber="4",
            ),
            "sha-missing-genre",
        )
        db.add(batch)
        db.commit()
        db.refresh(batch)

        summary = snapshot_batch_metadata(db, batch)
        db.commit()
        assert summary["media_files"] == 4
        assert summary["raw_tags"] == 4
        assert summary["normalized_profiles"] == 4
        assert db.query(MediaFile).count() == 4
        assert db.query(RawMediaTag).count() == 4
        assert db.query(NormalizedMusicProfile).count() == 4

        good = (
            db.query(NormalizedMusicProfile)
            .filter(NormalizedMusicProfile.title == "Return of the G")
            .one()
        )
        assert good.artist == "OutKast"
        assert good.album == "Aquemini"
        assert good.primary_genre == "Hip-Hop"
        assert good.genre_family == "Hip-Hop / Rap / Mixtape"

        review = (
            db.query(NormalizedMusicProfile)
            .filter(NormalizedMusicProfile.title == mojibake_title)
            .one()
        )
        assert review.title == mojibake_title
        assert review.genre_family == UNKNOWN_GENRE_FAMILY

        flags = db.query(MetadataReviewFlag).all()
        flag_types = {flag.flag_type for flag in flags}
        assert "mojibake_detected" in flag_types
        assert "unmapped_genre" in flag_types
        assert "unknown_genre" in flag_types
        assert "missing_artist" in flag_types
        assert "missing_album_artist" in flag_types
        assert "classical_metadata_incomplete" in flag_types

        snapshot_batch_metadata(db, batch)
        db.commit()
        assert db.query(MediaFile).count() == 4
        assert db.query(RawMediaTag).count() == 4
        assert db.query(NormalizedMusicProfile).count() == 4
        flag_count = db.query(MetadataReviewFlag).count()
        snapshot_batch_metadata(db, batch)
        db.commit()
        assert db.query(MetadataReviewFlag).count() == flag_count
    finally:
        db.close()
        engine.dispose()

    print("M4A metadata database foundation checks passed.")


if __name__ == "__main__":
    main()
