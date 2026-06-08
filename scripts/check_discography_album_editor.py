"""Check discography album corrections propagate to batch and file metadata."""

from __future__ import annotations

import os
import sys
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import Session


PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = PROJECT_ROOT / "backend"
os.environ["DEBUG"] = "true"
sys.path.insert(0, str(BACKEND_ROOT))

from app.api.routes import update_discography_metadata  # noqa: E402
from app.db.session import Base  # noqa: E402
from app.models.archive import IngestBatch, IngestFile  # noqa: E402
from app.schemas.archive import (  # noqa: E402
    DiscographyAlbumUpdate,
    DiscographyMetadataUpdate,
)


def check(label: str, condition: bool) -> int:
    print(f"{'PASS' if condition else 'FAIL'} {label}")
    return 0 if condition else 1


def main() -> int:
    failures = 0
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)

    with Session(engine) as db:
        batch = IngestBatch(
            source_path="Kanye West Discography",
            detected_type="music_discography",
            status="needs_metadata_review",
            confidence=0.6,
            suggested_destination="Music/Discographies/Kanye West",
            metadata_json={
                "artist": "Kanye West",
                "album_count": 1,
                "track_count": 1,
                "metadata_quality": "weak",
                "metadata_warnings": ["child_album_metadata_missing"],
                "albums": [{
                    "source_folder": "808s",
                    "artist": "Kanye West",
                    "album": "808s & Heartbreak",
                    "year": None,
                    "track_count": 1,
                    "release_type": "single",
                    "include": True,
                    "warnings": ["album_missing_year", "possible_single_or_ep"],
                }],
            },
        )
        db.add(batch)
        db.flush()
        ingest_file = IngestFile(
            batch_id=batch.id,
            file_path="01.flac",
            file_name="01.flac",
            extension=".flac",
            size_bytes=1,
            metadata_json={
                "_discography_album": {
                    "source_folder": "808s",
                    "album": "808s & Heartbreak",
                    "year": None,
                    "release_type": "single",
                    "include": True,
                }
            },
        )
        db.add(ingest_file)
        db.commit()

        result = update_discography_metadata(
            batch.id,
            DiscographyMetadataUpdate(
                artist="Kanye West",
                albums=[
                    DiscographyAlbumUpdate(
                        source_folder="808s",
                        album="808s & Heartbreak",
                        year="2008",
                        release_type="album",
                        include=True,
                    )
                ],
            ),
            db,
        )
        db.refresh(batch)
        db.refresh(ingest_file)
        album = batch.metadata_json["albums"][0]
        file_album = ingest_file.metadata_json["_discography_album"]

        failures += check(
            "album correction updates batch metadata",
            album["year"] == "2008"
            and album["release_type"] == "album"
            and album["status"] == "warning",
        )
        failures += check(
            "album correction updates file move-plan metadata",
            file_album["year"] == "2008"
            and file_album["release_type"] == "album",
        )
        failures += check(
            "resolved missing metadata returns batch to pending review",
            result.status == "pending_review"
            and "child_album_metadata_missing" not in result.metadata_warnings,
        )

    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
