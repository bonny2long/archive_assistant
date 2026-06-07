"""Check deterministic manual-confirm duplicate batch merging."""

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

from app.db.session import Base  # noqa: E402
from app.models.archive import IngestBatch, IngestFile  # noqa: E402
from app.services.batch_merge import (  # noqa: E402
    find_archived_duplicate_candidate,
    find_merge_candidate_batches,
    merge_music_batches,
)


def check(label: str, condition: bool) -> int:
    print(f"{'PASS' if condition else 'FAIL'} {label}")
    return 0 if condition else 1


def make_batch(
    artist: str,
    album: str,
    year: str,
    track_count: int,
    *,
    format_bucket: str = "MP3",
    status: str = "pending_review",
    confirmed: bool = False,
) -> IngestBatch:
    batch = IngestBatch(
        source_path=f"ingest/{artist}/{album}/{track_count}",
        status=status,
        confidence=1.0,
        suggested_destination=f"library/{format_bucket}/{artist}/{year} - {album}",
        metadata_confirmed=confirmed,
        metadata_json={
            "artist": artist,
            "albumartist": artist,
            "album": album,
            "year": year,
            "date": year,
            "genre": "Mixtape",
            "format": format_bucket,
            "track_count": track_count,
            "disc_count": 1,
            "metadata_quality": "good",
            "metadata_warnings": [],
        },
        suggested_metadata={
            "artist": artist,
            "album": album,
            "year": year,
            "genre": "Mixtape",
        },
    )
    extension = ".mp3" if format_bucket == "MP3" else ".flac"
    for index in range(1, track_count + 1):
        batch.files.append(
            IngestFile(
                file_path=f"ingest/{artist}/{album}/{track_count}/{index:02d}{extension}",
                file_name=f"{index:02d}{extension}",
                extension=extension,
                size_bytes=1,
                checksum=f"{artist}-{album}-{track_count}-{index}",
                metadata_json={
                    "title": f"Track {index}",
                    "tracknumber": str(index),
                    "discnumber": 1,
                },
            )
        )
    return batch


def main() -> int:
    failures = 0
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)

    with Session(engine) as db:
        large = make_batch(
            "DJ Cinema & Lil Wayne",
            "Starring In Mardi Gras Bootleg",
            "2008",
            24,
        )
        small = make_batch(
            "DJ Cinema - Lil Wayne",
            "Starring In Mardi Gras Bootleg",
            "2008",
            1,
            confirmed=True,
        )
        db.add_all([large, small])
        db.commit()

        candidates = find_merge_candidate_batches(db, small)
        failures += check(
            "confirmed canonical duplicate finds pending merge candidate",
            [candidate.id for candidate in candidates] == [large.id],
        )
        result = merge_music_batches(db, small, candidates)
        db.commit()
        db.refresh(large)
        db.refresh(small)
        failures += check(
            "24 plus 1 tracks merge into largest batch",
            result.batch.id == large.id
            and large.metadata_json.get("track_count") == 25
            and db.query(IngestFile).filter(IngestFile.batch_id == large.id).count() == 25,
        )
        failures += check(
            "smaller source batch remains as merged audit row",
            small.status == "merged"
            and small.metadata_json.get("merged_into_batch_id") == large.id,
        )
        failures += check(
            "target records merge warning and source batch id",
            "manual_duplicate_batch_merge_performed"
            in large.metadata_json.get("metadata_warnings", [])
            and small.id in large.metadata_json.get("merged_batch_ids", []),
        )

        different_album = make_batch(
            "DJ Cinema & Lil Wayne",
            "Another Mixtape",
            "2008",
            1,
            confirmed=True,
        )
        different_format = make_batch(
            "DJ Cinema & Lil Wayne",
            "Starring In Mardi Gras Bootleg",
            "2008",
            1,
            format_bucket="FLAC",
            confirmed=True,
        )
        archived = make_batch(
            "Jay-Z",
            "Reasonable Doubt",
            "1996",
            14,
            format_bucket="FLAC",
            status="moved",
        )
        archived_duplicate = make_batch(
            "Jay Z",
            "reasonable doubt",
            "1996",
            1,
            format_bucket="FLAC",
            confirmed=True,
        )
        db.add_all([different_album, different_format, archived, archived_duplicate])
        db.commit()

        failures += check(
            "different album does not merge",
            find_merge_candidate_batches(db, different_album) == [],
        )
        failures += check(
            "different format bucket does not merge",
            find_merge_candidate_batches(db, different_format) == [],
        )
        archived_match = find_archived_duplicate_candidate(db, archived_duplicate)
        failures += check(
            "moved canonical release is reported but not merged",
            find_merge_candidate_batches(db, archived_duplicate) == []
            and archived_match is not None
            and archived_match.id == archived.id,
        )

    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
