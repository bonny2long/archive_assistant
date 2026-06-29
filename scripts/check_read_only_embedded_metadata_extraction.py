import os
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = PROJECT_ROOT / "backend"
os.environ["DEBUG"] = "true"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.services.embedded_metadata_reader import (  # noqa: E402
    EmbeddedMetadataResult,
    apply_embedded_metadata_evidence,
    embedded_field_envelopes,
    read_embedded_metadata,
)
from app.services.metadata_contract import (  # noqa: E402
    approve_field,
    metadata_manifest_header,
)


def main() -> None:
    fixture_dir = PROJECT_ROOT / ".tmp"
    fixture_dir.mkdir(exist_ok=True)
    unsupported = fixture_dir / "embedded-reader-unsupported.txt"
    unsupported.write_bytes(b"not audio")
    before = unsupported.read_bytes()
    result = read_embedded_metadata(unsupported, media_type="unknown")
    after = unsupported.read_bytes()
    assert before == after
    assert result.read_ok is False
    assert "unsupported_embedded_metadata_type" in result.warnings

    fake = EmbeddedMetadataResult(
        path=str(unsupported),
        media_type="music_album",
        fields={"artist": "Embedded Artist", "album": "Embedded Album"},
        technical={"duration_seconds": 123.4},
        warnings=[],
        read_ok=True,
    )
    envelopes = embedded_field_envelopes(fake)
    assert envelopes["artist"]["source"] == "embedded_tag"
    assert envelopes["artist"]["approved"] is False
    assert envelopes["duration_seconds"]["confidence"] == 0.95

    metadata = {
        "metadata_contract": {
            "version": "aa-m0.1",
            "fields": {
                "artist": approve_field(
                    "Manual Artist",
                    approved_by="local_admin",
                    reason="test approval",
                )
            },
        }
    }
    apply_embedded_metadata_evidence(metadata, fake)
    fields = metadata["metadata_contract"]["fields"]
    assert fields["artist"]["value"] == "Manual Artist"
    assert fields["artist"]["approved"] is True
    assert fields["embedded_artist"]["value"] == "Embedded Artist"
    assert metadata["metadata_conflicts"][0]["field"] == "artist"

    header = metadata_manifest_header(
        manifest_type="embedded_metadata_check",
        manifest_version="v1",
        sources_summary={"embedded_tag": 2},
    )
    assert header["metadata_contract_version"] == "aa-m0.1"
    assert header["metadata_version"]

    print("Read-only embedded metadata extraction checks passed.")


if __name__ == "__main__":
    main()
