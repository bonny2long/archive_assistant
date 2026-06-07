"""Check canonical destination conflicts without touching the project database."""

from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path
from uuid import uuid4

from sqlalchemy import create_engine
from sqlalchemy.orm import Session


PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = PROJECT_ROOT / "backend"
os.environ["DEBUG"] = "true"
sys.path.insert(0, str(BACKEND_ROOT))

from app.core.config import settings  # noqa: E402
from app.db.session import Base  # noqa: E402
from app.models.archive import IngestBatch, IngestFile  # noqa: E402
from app.services.mover import (  # noqa: E402
    _destination_filename_conflicts,
    find_possible_existing_destination,
    resolve_confirmed_destination_alias,
)


def check(label: str, condition: bool) -> int:
    print(f"{'PASS' if condition else 'FAIL'} {label}")
    return 0 if condition else 1


def batch(destination: Path, status: str = "approved") -> IngestBatch:
    return IngestBatch(
        source_path="test",
        status=status,
        confidence=1.0,
        suggested_destination=str(destination),
        metadata_json={
            "artist": "DJ Cinema - Lil Wayne",
            "album": "Starring In Mardi Gras Bootleg",
            "year": "2008",
            "format": "MP3",
        },
    )


def main() -> int:
    failures = 0
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)

    original_mp3 = settings.music_mp3_dir
    original_flac = settings.music_flac_dir
    check_root = PROJECT_ROOT / "data" / "_CHECKS" / f"destination-guard-{uuid4().hex}"
    check_root.mkdir(parents=True, exist_ok=True)
    try:
        with Session(engine) as db:
            library = check_root
            settings.music_mp3_dir = library / "MP3"
            settings.music_flac_dir = library / "FLAC"

            target_path = (
                settings.music_mp3_dir
                / "DJ Cinema - Lil Wayne"
                / "2008 - Starring In Mardi Gras Bootleg"
            )
            target = batch(target_path)
            db.add(target)
            db.flush()

            existing = batch(
                settings.music_mp3_dir
                / "DJ Cinema & Lil Wayne"
                / "2008 - Starring In Mardi Gras Bootleg",
                status="moved",
            )
            db.add(existing)
            db.commit()

            conflict = find_possible_existing_destination(db, target)
            failures += check(
                "moved canonical destination blocks a different batch",
                conflict is not None
                and conflict.get("type") == "possible_duplicate_destination",
            )

            db.delete(existing)
            db.commit()
            alias_folder = settings.music_mp3_dir / "DJ Cinema & Lil Wayne"
            alias_folder.mkdir(parents=True)
            conflict = find_possible_existing_destination(db, target)
            failures += check(
                "existing canonical artist alias is detected",
                conflict is not None
                and conflict.get("type") == "possible_artist_alias",
            )
            target.metadata_confirmed = True
            resolved = resolve_confirmed_destination_alias(db, target)
            failures += check(
                "confirmed alias reuses existing canonical artist folder",
                resolved is not None
                and resolved.parent == alias_folder
                and resolved.name == "2008 - Starring In Mardi Gras Bootleg",
            )
            target.files.append(
                IngestFile(
                    file_path="ingest/01.mp3",
                    file_name="01.mp3",
                    extension=".mp3",
                    size_bytes=1,
                    metadata_json={
                        "title": "Intro",
                        "tracknumber": "1",
                        "discnumber": 1,
                    },
                )
            )
            resolved.mkdir(parents=True)
            (resolved / "01 - Intro.mp3").write_bytes(b"existing")
            failures += check(
                "existing target filename blocks overwrite",
                bool(_destination_filename_conflicts(target, resolved, 1)),
            )

            flac_target = batch(
                settings.music_flac_dir
                / "DJ Cinema - Lil Wayne"
                / "2008 - Starring In Mardi Gras Bootleg"
            )
            db.add(flac_target)
            db.commit()
            failures += check(
                "MP3 aliases do not block a FLAC destination",
                find_possible_existing_destination(db, flac_target) is None,
            )
    finally:
        settings.music_mp3_dir = original_mp3
        settings.music_flac_dir = original_flac
        shutil.rmtree(check_root, ignore_errors=True)

    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
