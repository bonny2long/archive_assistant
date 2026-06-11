"""Check safe bulk approval behavior."""

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

from app.api.routes import approve_selected_batches  # noqa: E402
from app.db.session import Base  # noqa: E402
from app.models.archive import IngestBatch  # noqa: E402
from app.schemas.archive import BulkApproveRequest  # noqa: E402


def batch(status: str, quality: str = "good", warnings: list[str] | None = None) -> IngestBatch:
    return IngestBatch(
        source_path="test",
        detected_type="music_album",
        status=status,
        confidence=1.0,
        metadata_json={
            "artist": "Artist",
            "album": "Album",
            "year": "2001",
            "format": "MP3",
            "metadata_quality": quality,
            "metadata_warnings": warnings or [],
        },
    )


def check(label: str, condition: bool) -> int:
    print(f"{'PASS' if condition else 'FAIL'} {label}")
    return 0 if condition else 1


def main() -> int:
    failures = 0
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)

    with Session(engine) as db:
        good = batch("pending_review")
        needs = batch("needs_metadata_review", "weak")
        moved = batch("moved")
        blocked = batch("pending_review", warnings=["possible_duplicate_destination"])
        db.add_all([good, needs, moved, blocked])
        db.commit()

        result = approve_selected_batches(
            BulkApproveRequest(batch_ids=[good.id, needs.id, moved.id, blocked.id, 999]),
            db,
        )
        reasons = {error.batch_id: error.reason for error in result.errors}
        db.refresh(good)

        failures += check(
            "only pending clean batch is approved",
            result.approved == [good.id] and good.status == "approved",
        )
        failures += check(
            "needs metadata batch is skipped",
            reasons.get(needs.id) == "metadata_not_confirmed",
        )
        failures += check(
            "moved batch is skipped",
            reasons.get(moved.id) == "invalid_status:moved",
        )
        failures += check(
            "blocking review item batch is skipped",
            blocked.id in result.skipped
            and blocked.id not in result.approved
            and reasons.get(blocked.id) in {
                "blocking_review_items",
                "metadata_not_confirmed",
            },
        )
        failures += check("missing batch is reported", reasons.get(999) == "not_found")

    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
