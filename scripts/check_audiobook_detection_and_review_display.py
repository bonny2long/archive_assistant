from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


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
    require(
        review_source,
        "non_blocking.append(_item(\n                \"audiobook_year_missing\"",
        "non-blocking audiobook year warning",
    )
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
