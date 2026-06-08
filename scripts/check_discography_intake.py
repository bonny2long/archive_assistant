"""Check deterministic discography detection, movement, and reset behavior."""

from __future__ import annotations

import shutil
import sys
import os
from pathlib import Path
from tempfile import mkdtemp

from sqlalchemy import create_engine
from sqlalchemy.orm import Session


PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = PROJECT_ROOT / "backend"
os.environ["DEBUG"] = "true"
sys.path.insert(0, str(BACKEND_ROOT))

from app.core.config import settings  # noqa: E402
from app.db.session import Base  # noqa: E402
from app.services.dev_reset import reset_music_test_data  # noqa: E402
from app.services.mover import move_approved_batches  # noqa: E402
from app.services.music_metadata import (  # noqa: E402
    looks_like_discography_parent,
    parse_discography_parent_folder,
    parse_music_folder_name,
)
from app.services.scanner import _create_discography_batch  # noqa: E402


def check(label: str, condition: bool) -> int:
    print(f"{'PASS' if condition else 'FAIL'} {label}")
    return 0 if condition else 1


def track_metadata(
    artist: str,
    album: str,
    title: str,
    track: int,
    extension: str,
) -> dict:
    return {
        "albumartist": artist,
        "artist": artist,
        "album": album,
        "title": title,
        "tracknumber": str(track),
        "discnumber": 1,
        "date": "2000",
        "genre": "Hip-Hop",
        "extension": extension,
    }


def main() -> int:
    failures = 0
    checks_root = Path(r"C:\tmp")
    checks_root.mkdir(parents=True, exist_ok=True)
    root = Path(mkdtemp(prefix="archive-discography-", dir=checks_root))
    original_paths = {
        "ingest_root": settings.ingest_root,
        "reports_dir": settings.reports_dir,
        "music_discographies_dir": settings.music_discographies_dir,
    }

    try:
        ingest = root / "_INGEST"
        reports = root / "_REPORTS" / "ingest-reports"
        discographies = root / "Music" / "Discographies"
        settings.ingest_root = ingest
        settings.reports_dir = reports
        settings.music_discographies_dir = discographies

        parent = ingest / "Nas Discography"
        album_one = parent / "1994 - Illmatic"
        album_two = parent / "1996 - It Was Written"
        first = album_one / "01 - Genesis.mp3"
        second = album_two / "01 - Album Intro.flac"
        first.parent.mkdir(parents=True, exist_ok=True)
        second.parent.mkdir(parents=True, exist_ok=True)
        first.write_bytes(b"discography-test-mp3")
        second.write_bytes(b"discography-test-flac")

        metadata = {
            str(first): track_metadata("Nas", "Illmatic", "Genesis", 1, ".mp3"),
            str(second): track_metadata(
                "Nas",
                "It Was Written",
                "Album Intro",
                1,
                ".flac",
            ),
        }
        child_metadata = {
            str(album_one): [metadata[str(first)]],
            str(album_two): [metadata[str(second)]],
        }
        failures += check(
            "discography parent token detects child albums",
            looks_like_discography_parent(
                parent,
                [album_one, album_two],
                child_metadata,
            ),
        )

        multi_disc = ingest / "Kendrick Lamar - Mr. Morale"
        cd_one = multi_disc / "CD1"
        cd_two = multi_disc / "Disc 2"
        failures += check(
            "multi-disc album is not classified as a discography",
            not looks_like_discography_parent(
                multi_disc,
                [cd_one, cd_two],
                {str(cd_one): [], str(cd_two): []},
            ),
        )
        kanye = parse_discography_parent_folder(
            "Kanye West - Discography [FLAC Songs] [PMEDIA] ⭐️"
        )
        weeknd = parse_discography_parent_folder(
            "The Weeknd Discography 2012-2022 (FLAC) vtwin88cube"
        )
        failures += check(
            "Kanye release-pack noise is removed from collection artist",
            kanye["artist"] == "Kanye West"
            and kanye["format_hint"] == "FLAC"
            and "[PMEDIA]" in kanye["removed_tokens"],
        )
        failures += check(
            "Weeknd year range and source username are removed",
            weeknd["artist"] == "The Weeknd"
            and weeknd["year_range"] == "2012-2022"
            and "vtwin88cube" in weeknd["removed_tokens"],
        )
        failures += check(
            "normal album title parentheses are preserved",
            parse_music_folder_name("(2018) The Weeknd - My Dear Melancholy (EP)")["album"]
            == "My Dear Melancholy (EP)",
        )

        engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(engine)
        with Session(engine) as db:
            batch = _create_discography_batch(
                db,
                parent,
                {album_one: [first], album_two: [second]},
                metadata,
                {str(first): "checksum-one", str(second): "checksum-two"},
            )
            failures += check(
                "scanner creates one mixed-format discography batch",
                batch is not None
                and batch.detected_type == "music_discography"
                and batch.status == "pending_review"
                and batch.metadata_json["album_count"] == 2
                and batch.metadata_json["format_summary"] == ["FLAC", "MP3"],
            )

            assert batch is not None
            batch.status = "approved"
            db.commit()
            moved, errors = move_approved_batches(db)
            destination = discographies / "Nas"
            failures += check(
                "move preserves child album folders under discography root",
                moved == 1
                and not errors
                and (destination / "1994 - Illmatic" / "01 - Genesis.mp3").exists()
                and (
                    destination
                    / "1996 - It Was Written"
                    / "01 - Album Intro.flac"
                ).exists(),
            )
            failures += check(
                "discography parent move log is written",
                (destination / "metadata" / "discography-move-log.json").exists(),
            )

            reset = reset_music_test_data(db, apply=True)
            failures += check(
                "dev reset restores discography tracks and clears the batch",
                reset.restored_tracks == 2
                and reset.cleared_batches == 1
                and first.exists()
                and second.exists(),
            )
    finally:
        for name, value in original_paths.items():
            setattr(settings, name, value)
        shutil.rmtree(root, ignore_errors=True)

    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
