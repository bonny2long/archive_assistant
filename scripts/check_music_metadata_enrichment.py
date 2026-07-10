"""Offline AA-META1 metadata enrichment regression."""
from __future__ import annotations

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
from app.services.music_metadata_enrichment import (  # noqa: E402
    apply_music_metadata_enrichment,
    preview_music_metadata_enrichment,
)


class FakeMusicBrainzProvider:
    def search_release_payloads(self, evidence: dict) -> list[dict]:
        assert evidence["release_title"] == "My Dear Melancholy"
        assert evidence["year"] == "2018"
        assert [item["track_number"] for item in evidence["tracks"]] == [2, 5]
        return [{
            "provider": "musicbrainz",
            "release_id": "fake-release-my-dear-melancholy",
            "release_group_id": "fake-group-my-dear-melancholy",
            "artist": "The Weeknd",
            "title": "My Dear Melancholy,",
            "year": "2018",
            "release_type": "EP",
            "genres": ["Alternative R&B"],
            "provider_score": 1.0,
            "tracks": [
                {"disc_number": 1, "track_number": "1", "title": "Call Out My Name", "recording_id": "recording-1"},
                {"disc_number": 1, "track_number": "2", "title": "Try Me", "recording_id": "recording-2"},
                {"disc_number": 1, "track_number": "3", "title": "Wasted Times", "recording_id": "recording-3"},
                {"disc_number": 1, "track_number": "4", "title": "I Was Never There", "recording_id": "recording-4"},
                {"disc_number": 1, "track_number": "5", "title": "Hurt You", "recording_id": "recording-5"},
                {"disc_number": 1, "track_number": "6", "title": " privilege", "recording_id": "recording-6"},
            ],
        }]


def main() -> None:
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    db = sessionmaker(bind=engine)()
    try:
        batch = IngestBatch(
            source_kind="manual-drop",
            source_path=str(PROJECT_ROOT / ".tmp" / "2018 - My Dear Melancholy (EP)"),
            detected_type="music_album",
            status="needs_metadata_review",
            confidence=0.5,
            suggested_destination=str(PROJECT_ROOT / ".tmp" / "Music" / "Library" / "FLAC" / "Unknown Artist"),
            suggested_metadata={
                "artist": "Unknown Artist",
                "album": "2018 - My Dear Melancholy (EP)",
                "year": "Unkn",
                "format": "FLAC",
            },
            metadata_json={
                "artist": "Unknown Artist",
                "album": "2018 - My Dear Melancholy (EP)",
                "year": "Unkn",
                "format": "FLAC",
                "metadata_quality": "weak",
                "track_count": 2,
                "file_count": 2,
            },
        )
        db.add(batch)
        db.flush()
        original_paths: list[str] = []
        for track_number, title in ((2, "Try Me"), (5, "Hurt You")):
            file_name = f"{track_number:02d}.- {title}.flac"
            file_path = str(Path(batch.source_path) / file_name)
            original_paths.append(file_path)
            db.add(IngestFile(
                batch_id=batch.id,
                file_path=file_path,
                file_name=file_name,
                extension=".flac",
                size_bytes=4096,
                checksum=f"enrichment-{track_number}",
                detected_role="music_audio",
                metadata_json={
                    "artist": "Unknown Artist",
                    "albumartist": "Unknown Artist",
                    "album": "2018 - My Dear Melancholy (EP)",
                    "title": title,
                    "tracknumber": "1",
                    "discnumber": 1,
                    "date": "Unknown Ye",
                },
            ))
        db.commit()
        db.refresh(batch)

        provider = FakeMusicBrainzProvider()
        preview = preview_music_metadata_enrichment(db, batch.id, provider=provider)
        assert preview["candidates"][0]["artist"] == "The Weeknd"
        assert preview["candidates"][0]["title"] == "My Dear Melancholy,"
        assert preview["candidates"][0]["match_confidence"] >= 0.95
        assert [item["track_number"] for item in preview["candidates"][0]["track_matches"]] == ["2", "5"]

        result = apply_music_metadata_enrichment(
            db,
            batch.id,
            "fake-release-my-dear-melancholy",
            provider=provider,
        )
        db.refresh(batch)
        assert result["applied_track_count"] == 2
        assert result["artist"] == "The Weeknd"
        assert result["release_type"] == "EP"
        assert batch.metadata_json["artist"] == "The Weeknd"
        assert batch.metadata_json["album"] == "My Dear Melancholy,"
        assert batch.metadata_json["metadata_contract"]["fields"]["artist"]["source"] == "musicbrainz_lookup"
        assert batch.metadata_confirmed is False
        assert "The Weeknd" in (batch.suggested_destination or "")
        assert "2018 - My Dear Melancholy" in (batch.suggested_destination or "")
        assert [file.file_path for file in batch.files] == original_paths
        assert [file.metadata_json["tracknumber"] for file in batch.files] == ["2", "5"]
        assert all(file.metadata_json["metadata_enrichment"]["provider"] == "musicbrainz" for file in batch.files)
        print("PASS - AA-META1 partial release enrichment verified")
    finally:
        db.close()


if __name__ == "__main__":
    main()