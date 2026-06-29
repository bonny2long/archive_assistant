import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = PROJECT_ROOT / "backend"
os.environ["DEBUG"] = "true"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.services.metadata_contract import approve_field, metadata_field  # noqa: E402
from app.services.metadata_inheritance import build_compact_music_review_summary  # noqa: E402


def main() -> None:
    placeholder_artist = approve_field("Unknown Artist", approved_by="local_admin")
    placeholder_year = approve_field("Unknown Ye", approved_by="local_admin")
    metadata = {
        "metadata_quality": "weak",
        "metadata_contract": {
            "fields": {
                "artist": placeholder_artist,
                "year": placeholder_year,
                "genre": approve_field("indie folk", approved_by="local_admin"),
            }
        },
        "artist_profile": {
            "artist": placeholder_artist,
            "primary_genre": approve_field("indie folk", approved_by="local_admin"),
        },
        "release_profile": {
            "release_title": metadata_field("Missing", source="manual", approval_state="approved", approved=True),
            "year": placeholder_year,
            "genre": approve_field("indie folk", approved_by="local_admin"),
        },
        "metadata_warnings": ["artist_missing", "year_missing"],
        "blocking_review_items": [],
        "non_blocking_review_items": [],
    }
    summary = build_compact_music_review_summary(metadata)
    assert "artist" not in summary["approved_core_fields"]
    assert "year" not in summary["approved_core_fields"]
    assert "genre" in summary["approved_core_fields"]
    assert summary["artist_profile"]["artist"]["approved"] is False
    assert summary["artist_profile"]["artist"]["approval_state"] == "needs_review"
    assert summary["release_profile"]["year"]["approved"] is False
    assert summary["release_profile"]["genre"]["approved"] is True

    approved = build_compact_music_review_summary({
        "metadata_quality": "good",
        "metadata_contract": {
            "fields": {
                "artist": approve_field("The Head & The Heart", approved_by="local_admin"),
                "genre": approve_field("indie folk", approved_by="local_admin"),
            }
        },
        "artist_profile": {
            "artist": approve_field("The Head & The Heart", approved_by="local_admin"),
            "primary_genre": approve_field("indie folk", approved_by="local_admin"),
        },
        "release_profile": {},
    })
    assert set(approved["approved_core_fields"]) == {"artist", "genre"}
    assert approved["artist_profile"]["artist"]["approved"] is True
    assert approved["artist_profile"]["primary_genre"]["approved"] is True
    print("Placeholder metadata display checks passed.")


if __name__ == "__main__":
    main()