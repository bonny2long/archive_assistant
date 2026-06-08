"""Check the batch detail includes JSON copy and fallback behavior."""

from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SOURCE = PROJECT_ROOT / "frontend" / "src" / "components" / "BatchDetail.tsx"


def check(label: str, condition: bool) -> int:
    print(f"{'PASS' if condition else 'FAIL'} {label}")
    return 0 if condition else 1


def main() -> int:
    content = SOURCE.read_text(encoding="utf-8")
    failures = 0
    failures += check(
        "copy debug JSON button uses clipboard API",
        "Copy debug JSON" in content
        and "navigator.clipboard.writeText(JSON.stringify(batch, null, 2))" in content,
    )
    failures += check(
        "clipboard failure opens debug JSON",
        'setShowJson(true)' in content
        and "Copy failed. JSON opened instead." in content,
    )
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
