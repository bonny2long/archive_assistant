import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.services.review_state import build_review_state


def require(source: str, needle: str, label: str) -> None:
    if needle not in source:
        raise AssertionError(f"Missing {label}: {needle}")


def main() -> None:
    audiobook_source = (
        ROOT / "backend/app/services/audiobook_metadata.py"
    ).read_text(encoding="utf-8")
    review_source = (
        ROOT / "backend/app/services/review_state.py"
    ).read_text(encoding="utf-8")
    detail_source = (
        ROOT / "frontend/src/components/BatchDetail.tsx"
    ).read_text(encoding="utf-8")

    require(
        audiobook_source,
        "def looks_like_generic_multidisc_audiobook_source",
        "generic multidisc detector",
    )
    require(
        audiobook_source,
        "if looks_like_generic_multidisc_audiobook_source(path):",
        "generic detector call",
    )
    review_state = build_review_state(
        "audiobook",
        {
            "review_type": "audiobook",
            "author": "Frank Herbert",
            "title": "Dune",
            "metadata_warnings": ["audiobook_year_missing"],
        },
    )
    non_blocking_types = {
        item.get("type")
        for item in review_state.get("non_blocking_review_items", [])
    }
    blocking_types = {
        item.get("type")
        for item in review_state.get("blocking_review_items", [])
    }
    if "audiobook_year_missing" not in non_blocking_types:
        raise AssertionError("audiobook_year_missing was not non-blocking")
    if "audiobook_year_missing" in blocking_types:
        raise AssertionError("audiobook_year_missing should not be blocking")
    require(
        detail_source,
        "isFinalStatus(batch.status) && isMetadataConfirmed(batch)",
        "final confirmed review-card suppression",
    )
    require(
        detail_source,
        'audiobook: "Review audiobook metadata"',
        "audiobook review action",
    )
    print("audiobook detection and review display checks passed")


if __name__ == "__main__":
    main()
