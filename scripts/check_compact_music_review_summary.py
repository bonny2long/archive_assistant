import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = PROJECT_ROOT / "backend"
os.environ["DEBUG"] = "true"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.services.metadata_contract import approve_field  # noqa: E402
from app.services.metadata_inheritance import build_compact_music_review_summary  # noqa: E402


def main() -> None:
    metadata = {
        "metadata_quality": "good",
        "metadata_contract": {
            "fields": {
                "artist": approve_field("DJ Cinema & Lil Wayne", approved_by="local_admin"),
                "album": approve_field("Starring In Mardi Gras", approved_by="local_admin"),
                "year": approve_field("2008", approved_by="local_admin"),
                "genre": approve_field("Rap", approved_by="local_admin"),
                "format": approve_field("MP3", approved_by="local_admin"),
            }
        },
        "artist_profile": {
            "artist": approve_field("DJ Cinema & Lil Wayne", approved_by="local_admin"),
            "primary_genre": approve_field("Rap", approved_by="local_admin"),
        },
        "release_profile": {
            "release_title": approve_field("Starring In Mardi Gras", approved_by="local_admin"),
            "genre": approve_field("Rap", approved_by="local_admin"),
            "primary_genre": approve_field("Rap", approved_by="local_admin"),
        },
        "track_profiles": [
            {"file_name": "01 Intro.mp3", "inheritance_summary": {"inherited_field_count": 2}},
            {"file_name": "02 Track.mp3", "inheritance_summary": {"inherited_field_count": 2}},
        ],
        "inheritance_summary": {
            "explanations": [
                {"field": "genre", "inherited": True},
                {"field": "primary_genre", "inherited": True},
            ]
        },
        "metadata_warnings": ["embedded_metadata_reader_unavailable"],
        "blocking_review_items": [],
        "non_blocking_review_items": [],
    }
    summary = build_compact_music_review_summary(metadata)
    assert summary["core_metadata_status"] == "good"
    assert set(summary["approved_core_fields"]) == {"artist", "album", "year", "genre", "format"}
    assert summary["inherited_to_track_count"] == 2
    assert summary["inherited_fields"] == ["genre", "primary_genre"]
    assert "embedded_metadata_reader_unavailable" in summary["setup_warnings"]
    assert summary["profile_consistency"] == "ok"
    assert "subgenres" in summary["missing_optional_fields"]
    print("Compact music review summary checks passed.")


if __name__ == "__main__":
    main()
