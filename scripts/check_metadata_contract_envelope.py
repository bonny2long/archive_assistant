import os
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = PROJECT_ROOT / "backend"
os.environ["DEBUG"] = "true"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.services.metadata_contract import (  # noqa: E402
    METADATA_CONTRACT_VERSION,
    approve_field,
    field_source,
    field_value,
    metadata_field,
    metadata_manifest_header,
)


def main() -> None:
    field = metadata_field(
        "Nipsey Hussle",
        source="manual",
        confidence=1.5,
        reason="test",
    )
    assert field["value"] == "Nipsey Hussle"
    assert field["source"] == "manual"
    assert field["confidence"] == 1.0
    assert field["approval_state"] == "pending"
    assert field_value(field) == "Nipsey Hussle"
    assert field_value("scalar") == "scalar"
    assert field_source(metadata_field("x", source="bad-source")) == "unknown"

    approved = approve_field(field, approved_by="bonny", reason="accepted")
    assert approved["approval_state"] == "approved"
    assert approved["approved"] is True
    assert approved["approved_by"] == "bonny"
    assert approved["approved_at"]

    header = metadata_manifest_header(
        manifest_type="move",
        manifest_version="v1",
        sources_summary={"manual": 1},
    )
    assert header["metadata_contract_version"] == METADATA_CONTRACT_VERSION
    assert header["manifest_type"] == "move"
    assert header["manifest_version"] == "v1"
    assert header["metadata_version"]
    assert header["metadata_generated_at"]
    assert header["metadata_sources_summary"] == {"manual": 1}

    print("Metadata contract envelope checks passed.")


if __name__ == "__main__":
    main()
