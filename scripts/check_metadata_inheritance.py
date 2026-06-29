import os
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = PROJECT_ROOT / "backend"
os.environ["DEBUG"] = "true"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.services.embedded_metadata_reader import EmbeddedMetadataResult, apply_embedded_metadata_evidence  # noqa: E402
from app.services.metadata_contract import approve_field, field_value, metadata_manifest_header  # noqa: E402
from app.services.metadata_inheritance import (  # noqa: E402
    apply_discography_inheritance,
    apply_track_inheritance,
    resolve_release_profile,
    resolve_track_profile,
)


def main() -> None:
    artist_metadata = {
        "artist": "Nipsey Hussle",
        "primary_genre": "Hip-Hop",
        "subgenres": ["West Coast Rap", "Street Rap"],
        "moods": ["street", "reflective", "confident"],
        "energy": "medium-high",
        "era": "2010s",
        "region": "West Coast / Los Angeles",
        "related_artists": ["Kendrick Lamar", "YG"],
        "albums": [
            {
                "source_folder": "2013 - Crenshaw",
                "album": "Crenshaw",
                "year": "2013",
                "release_type": "mixtape",
                "include": True,
            }
        ],
    }
    inherited = apply_discography_inheritance(dict(artist_metadata))
    artist_profile = inherited["artist_profile"]
    assert artist_profile["primary_genre"]["approved"] is True
    assert field_value(artist_profile["primary_genre"]) == "Hip-Hop"

    release = inherited["albums"][0]
    release_profile = release["release_profile"]
    assert field_value(release_profile["primary_genre"]) == "Hip-Hop"
    assert release_profile["primary_genre"]["source"] == "artist_profile"
    assert release["inheritance_summary"]["inherited_field_count"] >= 1

    release_override, explanations = resolve_release_profile(
        {
            "album": "Victory Lap",
            "primary_genre": approve_field(
                "Rap",
                approved_by="local_admin",
                reason="release override",
            ),
        },
        artist_profile,
    )
    assert field_value(release_override["primary_genre"]) == "Rap"
    assert any(item["field"] == "primary_genre" for item in explanations)

    track_metadata = {"title": "Dedication"}
    track_profile, track_explanations = resolve_track_profile(
        track_metadata,
        release_profile,
    )
    assert field_value(track_profile["primary_genre"]) == "Hip-Hop"
    assert track_profile["primary_genre"]["source"] == "release_profile"
    assert any(item["inherited"] for item in track_explanations)

    manual_track = {
        "title": "Remix",
        "track_profile": {
            "primary_genre": approve_field(
                "R&B",
                approved_by="local_admin",
                reason="track override",
            )
        },
    }
    manual_profile, _ = resolve_track_profile(manual_track, release_profile)
    assert field_value(manual_profile["primary_genre"]) == "R&B"

    embedded = EmbeddedMetadataResult(
        path="track.flac",
        media_type="music_audio",
        fields={"genre": "Rap"},
        technical={"duration_seconds": 120.0},
        warnings=[],
        read_ok=True,
    )
    evidence_metadata = {
        "metadata_contract": {
            "version": "aa-m0.1",
            "fields": {
                "genre": approve_field(
                    "Hip-Hop",
                    approved_by="local_admin",
                    reason="approved release genre",
                )
            },
        }
    }
    apply_embedded_metadata_evidence(evidence_metadata, embedded)
    assert field_value(evidence_metadata["metadata_contract"]["fields"]["genre"]) == "Hip-Hop"
    assert field_value(evidence_metadata["metadata_contract"]["fields"]["embedded_genre"]) == "Rap"
    assert evidence_metadata["metadata_conflicts"]

    applied_track = apply_track_inheritance({"title": "Blue Laces"}, release_profile)
    assert applied_track["inheritance_summary"]["explanations"]

    header = metadata_manifest_header(
        manifest_type="metadata_inheritance_check",
        manifest_version="v1",
        sources_summary={"artist_profile": 1, "release_profile": 1},
    )
    assert header["metadata_contract_version"] == "aa-m0.1"
    print("Metadata inheritance checks passed.")


if __name__ == "__main__":
    main()
