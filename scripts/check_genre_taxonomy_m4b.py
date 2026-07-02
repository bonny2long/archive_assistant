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
from app.models.media_metadata import MetadataReviewFlag, NormalizedMusicProfile  # noqa: E402
from app.services.metadata_database import (  # noqa: E402
    genre_family_for,
    genre_taxonomy_match,
    seed_genre_taxonomy,
    snapshot_batch_metadata,
)


def metadata(genre, *, artist="Artist", albumartist="Artist", album="Album", title="Title", composer=None, work=None):
    fields = {
        "genre": genre,
        "artist": artist,
        "album_artist": albumartist,
        "album": album,
        "title": title,
        "track_number": "1",
        "composer": composer,
        "work": work,
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
    expected = {
        "IDM": "Electronic / EDM / House / Techno / IDM / Ambient",
        "Progressive House": "Electronic / EDM / House / Techno / IDM / Ambient",
        "Hip-Hop": "Hip-Hop / Rap / Mixtape",
        "Mixtape": "Hip-Hop / Rap / Mixtape",
        "Classical": "Classical",
        "Baroque": "Classical",
        "Reggae": "Reggae / Dancehall / Dub / Ska",
        "Dub": "Reggae / Dancehall / Dub / Ska",
        "Dancehall": "Reggae / Dancehall / Dub / Ska",
        "Afrobeats": "Afrobeats / African",
        "Afro-fusion": "Afrobeats / African",
        "Highlife": "Afrobeats / African",
        "Amapiano": "Afrobeats / African",
        "Folk": "Folk / Singer-Songwriter / Americana",
        "Singer-Songwriter": "Folk / Singer-Songwriter / Americana",
        "Jazz": "Jazz",
        "Bebop": "Jazz",
        "R&B": "R&B / Soul / Funk",
        "Neo Soul": "R&B / Soul / Funk",
        "Rock": "Rock / Alternative / Indie",
        "Alternative Rock": "Rock / Alternative / Indie",
        "Pop": "Pop",
        "Country": "Country",
        "Blues": "Blues",
        "Gospel": "Gospel",
        "Latin": "Latin / Caribbean",
        "Salsa": "Latin / Caribbean",
        "Metal": "Metal",
        "Punk": "Punk",
        "Soundtrack": "Soundtrack / Score",
        "Film Score": "Soundtrack / Score",
        "World": "World / International",
        "Spoken Word": "Spoken Word / Comedy",
        "Comedy": "Spoken Word / Comedy",
        "Children's": "Children's",
        "Unknown": "Unknown / Review Needed",
    }
    for raw, family in expected.items():
        assert genre_family_for(raw) == family, raw
    assert genre_family_for(None) == "Unknown / Review Needed"

    match = genre_taxonomy_match("World")
    assert match["genre_family"] == "World / International"
    assert "possible_broad_genre" in match["review_flags"]

    match = genre_taxonomy_match("Some Weird Genre That Is Not Mapped")
    assert match["genre_family"] == "Unknown / Review Needed"
    assert "unmapped_genre" in match["review_flags"]

    match = genre_taxonomy_match("World", folder_hint="Burna Boy Afrobeats")
    assert match["genre_family"] == "Afrobeats / African"
    assert match["match_source"] == "folder_hint"
    assert "possible_broad_genre" in match["review_flags"]

    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    db = Session()
    try:
        seed_genre_taxonomy(db)
        batch = IngestBatch(source_path=str(PROJECT_ROOT / ".tmp" / "Afrobeats"), detected_type="music_album")
        add_file(batch, "world.mp3", metadata("World", artist="Burna Boy", albumartist="Burna Boy", title="African Giant"))
        add_file(batch, "classical.mp3", metadata("Classical", artist=None, albumartist=None, album="Classical", title="Adagio"))
        db.add(batch)
        db.commit()
        db.refresh(batch)
        snapshot_batch_metadata(db, batch)
        db.commit()

        world = db.query(NormalizedMusicProfile).filter(NormalizedMusicProfile.title == "African Giant").one()
        assert world.primary_genre == "Afrobeats"
        assert world.genre_family == "Afrobeats / African"
        flag_types = {flag.flag_type for flag in db.query(MetadataReviewFlag).all()}
        assert "possible_broad_genre" in flag_types
        assert "missing_composer" in flag_types
        assert "missing_work_or_movement" in flag_types
        assert "missing_performer_or_ensemble" in flag_types
        assert "classical_metadata_incomplete" in flag_types
    finally:
        db.close()
        engine.dispose()

    print("M4B genre taxonomy mapper checks passed.")


if __name__ == "__main__":
    main()
