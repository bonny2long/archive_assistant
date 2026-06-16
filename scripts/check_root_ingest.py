"""Check deterministic classification of direct root ingest items."""

from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path
from tempfile import mkdtemp


PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = PROJECT_ROOT / "backend"
os.environ["DEBUG"] = "true"
sys.path.insert(0, str(BACKEND_ROOT))

from app.services.scanner import classify_ingest_item  # noqa: E402


def check(label: str, condition: bool) -> int:
    print(f"{'PASS' if condition else 'FAIL'} {label}")
    return 0 if condition else 1


def touch(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"root-ingest-check")


def main() -> int:
    failures = 0
    root = Path(mkdtemp(prefix="archive-root-ingest-", dir=r"C:\tmp"))
    try:
        album = root / "Artist - Album"
        touch(album / "01.mp3")

        discography = root / "Artist Discography"
        touch(discography / "2001 - First" / "01.flac")
        touch(discography / "2003 - Second" / "01.flac")

        multi_disc = root / "Artist - Double Album"
        touch(multi_disc / "CD1" / "01.mp3")
        touch(multi_disc / "CD2" / "01.mp3")

        unknown = root / "notes.txt"
        unknown.write_text("not media", encoding="utf-8")

        sidecar_only = root / "Severance Season 1 Mp4 1080p"
        sidecar_only.mkdir()
        (sidecar_only / "Read Me.txt").write_text("source note", encoding="utf-8")

        legacy = root / "music"
        touch(legacy / "Old Album" / "01.mp3")

        failures += check(
            "root-level album classifies as music_album",
            classify_ingest_item(album) == "music_album",
        )
        failures += check(
            "root-level discography classifies as music_discography",
            classify_ingest_item(discography) == "music_discography",
        )
        failures += check(
            "multi-disc release remains music_album",
            classify_ingest_item(multi_disc) == "music_album",
        )
        failures += check(
            "unknown file is skipped safely",
            classify_ingest_item(unknown) == "unknown_type",
        )
        failures += check(
            "sidecar-only folder is skipped without quarantine",
            classify_ingest_item(sidecar_only) == "ignored_sidecar_only_folder",
        )
        failures += check(
            "legacy music container is not the scan target",
            classify_ingest_item(legacy) == "ignored_system_folder",
        )
    finally:
        shutil.rmtree(root, ignore_errors=True)

    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
