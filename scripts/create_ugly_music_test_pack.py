"""Create ugly local music ingest folders by copying existing audio files."""

from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATA_ROOT = PROJECT_ROOT / "data"
DEFAULT_INGEST_ROOT = DATA_ROOT / "_INGEST"
DEFAULT_SEARCH_ROOTS = [
    DATA_ROOT / "_INGEST",
    DATA_ROOT / "Music" / "Library",
]
AUDIO_EXTENSIONS = {".mp3", ".flac", ".m4a", ".aac", ".wav", ".ogg", ".opus"}
UGLY_FOLDERS = [
    "Nas_-_Illmatic_(1994)_[FLAC_24bit_Remaster_320kbps]",
    "2003 Get Rich Or Die Tryin",
    "Jay-Z_x_Kanye_West_-_Watch_The_Throne_2011_Deluxe_Edition",
    "Outkast - Aquemini",
    "VA_-_90s_Hip_Hop_Classics_1998",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Copy existing local audio files into intentionally ugly test folders "
            "under data/_INGEST. This never deletes files or overwrites targets."
        )
    )
    parser.add_argument(
        "--ingest-root",
        type=Path,
        default=DEFAULT_INGEST_ROOT,
        help="Destination ingest music root.",
    )
    parser.add_argument(
        "--source-root",
        type=Path,
        action="append",
        help="Additional source root to search for existing audio files.",
    )
    return parser.parse_args()


def is_inside(path: Path, parent: Path) -> bool:
    try:
        path.resolve().relative_to(parent.resolve())
        return True
    except ValueError:
        return False


def find_audio_files(search_roots: list[Path], ingest_root: Path) -> list[Path]:
    target_roots = [(ingest_root / folder).resolve() for folder in UGLY_FOLDERS]
    files: list[Path] = []
    seen: set[Path] = set()
    for root in search_roots:
        if not root.exists():
            continue
        for path in sorted(root.rglob("*")):
            if not path.is_file() or path.suffix.lower() not in AUDIO_EXTENSIONS:
                continue
            resolved = path.resolve()
            if resolved in seen:
                continue
            if any(is_inside(resolved, target_root) for target_root in target_roots):
                continue
            seen.add(resolved)
            files.append(path)
    return files


def main() -> int:
    args = parse_args()
    ingest_root = args.ingest_root.resolve()
    search_roots = [root.resolve() for root in DEFAULT_SEARCH_ROOTS]
    if args.source_root:
        search_roots.extend(root.resolve() for root in args.source_root)

    source_files = find_audio_files(search_roots, ingest_root)
    if len(source_files) < len(UGLY_FOLDERS):
        print(
            f"Need at least {len(UGLY_FOLDERS)} existing local audio files, found {len(source_files)}.",
            file=sys.stderr,
        )
        print("Run reset first or pass --source-root with local test audio.", file=sys.stderr)
        return 1

    ingest_root.mkdir(parents=True, exist_ok=True)
    copied = 0
    skipped = 0
    for index, folder_name in enumerate(UGLY_FOLDERS, start=1):
        source = source_files[index - 1]
        target_dir = ingest_root / folder_name
        target = target_dir / f"01 - copied-test-track{source.suffix.lower()}"
        target_dir.mkdir(parents=True, exist_ok=True)
        if target.exists():
            skipped += 1
            print(f"SKIP exists: {target}")
            continue
        shutil.copy2(source, target)
        copied += 1
        print(f"COPY {source} -> {target}")

    print(f"Ugly test pack ready. Copied {copied}, skipped {skipped}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
