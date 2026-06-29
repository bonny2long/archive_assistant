import os
import sys
from pathlib import Path
from types import SimpleNamespace


PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = PROJECT_ROOT / "backend"
os.environ["DEBUG"] = "true"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.services.metadata_contract import (  # noqa: E402
    apply_manual_field_envelopes,
    field_value,
)
from app.services.metadata_inheritance import (  # noqa: E402
    rehydrate_music_review_metadata_after_manual_save,
    validate_music_profile_consistency,
)


RAW_ALBUM = "DJ_Cinema_and_Lil_Wayne_-_Starring_In_Mardi_Gras_Bootleg_2008"


def main() -> None:
    metadata = {
        "artist": "DJ Cinema & Lil Wayne",
        "albumartist": "DJ Cinema & Lil Wayne",
        "album": "Starring In Mardi Gras",
        "year": "2008",
        "date": "2008",
        "genre": "Rap",
        "format": "MP3",
        "metadata_warnings": ["profile_inheritance_stale", "raw_folder_name_detected"],
        "artist_profile": {
            "artist": {
                "value": "Unknown Artist",
                "source": "folder_inference",
                "confidence": 0.5,
                "approval_state": "pending",
                "approved": False,
            }
        },
        "release_profile": {
            "release_title": {
                "value": RAW_ALBUM,
                "source": "folder_inference",
                "confidence": 0.5,
                "approval_state": "pending",
                "approved": False,
            },
            "year": {
                "value": "Unknown Ye",
                "source": "folder_inference",
                "confidence": 0.5,
                "approval_state": "pending",
                "approved": False,
            },
        },
        "inheritance_summary": {"missing_field_count": 99, "explanations": []},
    }
    apply_manual_field_envelopes(
        metadata,
        ("artist", "albumartist", "album", "year", "genre", "format"),
        reason="Saved from music album metadata review.",
        approved_by="local_admin",
    )

    track_row = SimpleNamespace(
        file_name="01 Intro.mp3",
        detected_role="music_track",
        metadata_json={
            "albumartist": "Unknown Artist",
            "artist": "Unknown Artist",
            "album": RAW_ALBUM,
            "title": "Intro",
            "tracknumber": "1",
            "discnumber": "1",
            "date": "Unknown Ye",
            "genre": "Unknown",
            "duration_seconds": 111.0,
            "embedded_metadata": {"read_ok": False},
            "extraction_warnings": ["embedded_metadata_reader_unavailable"],
            "embedded_metadata_fields": {"artist": "Unknown Artist"},
        },
    )

    assert validate_music_profile_consistency(metadata) == ["profile_inheritance_stale"]
    rehydrated = rehydrate_music_review_metadata_after_manual_save(
        metadata,
        [track_row],
    )

    fields = rehydrated["metadata_contract"]["fields"]
    assert field_value(fields["artist"]) == "DJ Cinema & Lil Wayne"
    assert fields["artist"]["approved"] is True
    assert rehydrated["artist"] == "DJ Cinema & Lil Wayne"
    assert rehydrated["album"] == "Starring In Mardi Gras"
    assert rehydrated["year"] == "2008"
    assert rehydrated["genre"] == "Rap"

    assert field_value(rehydrated["artist_profile"]["artist"]) == "DJ Cinema & Lil Wayne"
    assert field_value(rehydrated["release_profile"]["release_title"]) == "Starring In Mardi Gras"
    assert field_value(rehydrated["release_profile"]["year"]) == "2008"
    assert field_value(rehydrated["release_profile"]["genre"]) == "Rap"
    assert "Unknown Artist" not in str(rehydrated["artist_profile"])
    assert "Unknown Ye" not in str(rehydrated["release_profile"])

    track_meta = track_row.metadata_json
    assert track_meta["albumartist"] == "DJ Cinema & Lil Wayne"
    assert track_meta["artist"] == "DJ Cinema & Lil Wayne"
    assert track_meta["album"] == "Starring In Mardi Gras"
    assert track_meta["date"] == "2008"
    assert track_meta["year"] == "2008"
    assert track_meta["genre"] == "Rap"
    assert track_meta["title"] == "Intro"
    assert track_meta["tracknumber"] == "1"
    assert track_meta["discnumber"] == "1"
    assert track_meta["duration_seconds"] == 111.0
    assert track_meta["extraction_warnings"] == ["embedded_metadata_reader_unavailable"]
    assert track_meta["embedded_metadata_fields"] == {"artist": "Unknown Artist"}
    assert track_meta["track_profile"]

    assert "profile_inheritance_stale" not in rehydrated.get("metadata_warnings", [])
    assert rehydrated["inheritance_summary"]["explanations"]
    assert rehydrated["track_profiles"][0]["file_name"] == "01 Intro.mp3"

    print("Metadata save rehydration checks passed.")


if __name__ == "__main__":
    main()
