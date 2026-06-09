"""Dev-only cleanup for zero-byte video test artifacts in _INGEST.

Update 035B. This is NOT a production deletion feature. It only finds video
files of size exactly 0 bytes inside ``data/_INGEST`` and, when explicitly
asked, moves them into a dev quarantine folder (never deletes them).

Usage:
    python scripts/cleanup_zero_byte_tv_test_artifacts.py --dry-run
    python scripts/cleanup_zero_byte_tv_test_artifacts.py --move-to-quarantine

Safety rules enforced here:
  - Only touches files under ``data/_INGEST``.
  - Only touches known video extensions.
  - Only touches files whose size is exactly 0 bytes.
  - Never deletes. ``--move-to-quarantine`` relocates files, preserving the
    relative path under ``_INGEST`` so the user can inspect what was moved.
  - Default behavior is a dry run that changes nothing.
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from datetime import datetime
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = PROJECT_ROOT / "backend"
sys.path.insert(0, str(BACKEND_ROOT))

from app.core.config import settings  # noqa: E402


# Known video extensions per Update 035B.
VIDEO_EXTENSIONS = {
    ".mkv",
    ".mp4",
    ".m4v",
    ".avi",
    ".mov",
    ".wmv",
    ".flv",
    ".webm",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Find (and optionally quarantine) zero-byte video test artifacts "
            "in data/_INGEST. Dry run by default; never deletes."
        )
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--dry-run",
        action="store_true",
        help="List zero-byte video files without moving anything (default).",
    )
    mode.add_argument(
        "--move-to-quarantine",
        action="store_true",
        help="Move zero-byte video files to the dev quarantine folder.",
    )
    return parser.parse_args()


def find_zero_byte_videos(ingest_root: Path) -> list[Path]:
    if not ingest_root.exists():
        return []
    found: list[Path] = []
    for path in ingest_root.rglob("*"):
        if not path.is_file():
            continue
        if path.suffix.lower() not in VIDEO_EXTENSIONS:
            continue
        try:
            if path.stat().st_size == 0:
                found.append(path)
        except OSError:
            continue
    return sorted(found)


def main() -> int:
    args = parse_args()
    move = bool(args.move_to_quarantine)
    mode = "move-to-quarantine" if move else "dry-run"

    ingest_root = settings.ingest_root
    data_root = settings.data_root
    timestamp = datetime.now().strftime("%Y-%m-%d-%H%M%S")
    quarantine_root = (
        data_root
        / "_QUARANTINE"
        / "dev-zero-byte-video-artifacts"
        / timestamp
    )
    reports_dir = data_root / "_REPORTS"

    artifacts = find_zero_byte_videos(ingest_root)

    items: list[dict] = []
    moved_count = 0
    for source in artifacts:
        relative = source.relative_to(ingest_root)
        destination: Path | None = None
        action = "would_move"
        if move:
            destination = quarantine_root / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(source), str(destination))
            action = "moved"
            moved_count += 1
        items.append(
            {
                "source_path": str(source),
                "relative_path": str(relative),
                "size_bytes": 0,
                "action": action,
                "destination_path": str(destination) if destination else None,
            }
        )

    report = {
        "mode": mode,
        "root": str(ingest_root),
        "artifact_count": len(artifacts),
        "total_bytes": 0,
        "items": items,
    }
    reports_dir.mkdir(parents=True, exist_ok=True)
    report_path = (
        reports_dir
        / f"dev-cleanup-zero-byte-video-artifacts-{timestamp}.json"
    )
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")

    print(f"Mode: {mode}")
    print(f"Scanned: {ingest_root}")
    print(f"Zero-byte video artifacts found: {len(artifacts)}")
    for item in items:
        verb = "MOVED " if item["action"] == "moved" else "WOULD MOVE"
        print(f"  {verb}  {item['relative_path']}")
    if move:
        print(f"Moved {moved_count} file(s) to: {quarantine_root}")
    else:
        print("Dry run only. No files were moved.")
        print("Re-run with --move-to-quarantine to relocate them.")
    print(f"Report written: {report_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
