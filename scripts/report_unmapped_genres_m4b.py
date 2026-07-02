import argparse
import json
import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = PROJECT_ROOT / "backend"
os.environ["DEBUG"] = "true"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.db.session import SessionLocal  # noqa: E402
from app.services.metadata_database import unmapped_genre_rows  # noqa: E402


def recommended_action(row: dict) -> str:
    flags = set(row.get("review_flags") or [])
    genre = str(row.get("normalized_genre") or "")
    if "possible_broad_genre" in flags and genre == "world":
        return "review broad genre; possible Afrobeats / African, Latin / Caribbean, Reggae, or Folk"
    if "unknown_genre" in flags:
        return "review / unknown"
    if "unmapped_genre" in flags:
        return "map"
    return "ignore"


def print_report(rows: list[dict]) -> None:
    print("AA-M4B Unmapped Genre Report")
    print("============================")
    print()
    if not rows:
        print("No unmapped, unknown, or broad low-specificity genres found.")
        return
    print(f"UNMAPPED GENRES: {len(rows)}")
    print()
    for index, row in enumerate(rows, start=1):
        print(f"{index}. Raw genre: \"{row['raw_genre']}\"")
        print(f"   Normalized: {row['normalized_genre']}")
        print(f"   Count: {row['count']}")
        print(f"   Current family: {row.get('genre_family') or 'None'}")
        if row.get("review_flags"):
            print(f"   Review flags: {', '.join(row['review_flags'])}")
        examples = row.get("examples") or []
        if examples:
            print("   Examples:")
            for example in examples:
                artist = example.get("artist") or "-"
                album = example.get("album") or "-"
                title = example.get("title") or "-"
                print(f"   - Artist: {artist} | Album: {album} | Title: {title}")
        print(f"   Recommended action: {recommended_action(row)}")
        print()


def main() -> None:
    parser = argparse.ArgumentParser(description="Report unmapped AA music genres.")
    parser.add_argument("--out", type=Path, help="Optional JSON output path.")
    args = parser.parse_args()

    with SessionLocal() as db:
        rows = unmapped_genre_rows(db)
    print_report(rows)
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(rows, indent=2), encoding="utf-8")
        print(f"Wrote JSON report: {args.out}")


if __name__ == "__main__":
    main()
