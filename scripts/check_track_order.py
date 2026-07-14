"""Check resilient canonical music track ordering and filename generation."""

from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker


PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = PROJECT_ROOT / "backend"
sys.path.insert(0, str(BACKEND_ROOT))

from app.services.music_metadata import (  # noqa: E402
    music_track_filename,
    music_track_numbers,
    normalize_track_title_for_destination,
    sort_music_tracks,
    track_number_evidence,
)
from app.db.session import Base  # noqa: E402
from app.models.archive import IngestBatch, IngestFile  # noqa: E402
from app.services.track_metadata_repair import (  # noqa: E402
    rebuild_pending_music_track_metadata,
    repair_pending_music_batch_track_metadata,
)


def track(
    file_id: int,
    filename: str,
    tracknumber=None,
    discnumber=None,
    title: str | None = None,
):
    metadata = {"title": title or Path(filename).stem}
    if tracknumber is not None:
        metadata["tracknumber"] = tracknumber
    if discnumber is not None:
        metadata["discnumber"] = discnumber
    return SimpleNamespace(
        id=file_id,
        file_name=filename,
        extension=Path(filename).suffix,
        detected_role="music_track",
        metadata_json=metadata,
    )


def check(label: str, condition: bool) -> int:
    print(f"{'PASS' if condition else 'FAIL'} {label}")
    return 0 if condition else 1


def main() -> int:
    failures = 0

    merged_order = [
        track(2, "02 - Nothing Can Stop Me.mp3", "2/24"),
        track(99, "01 - Intro.mp3", "1/24"),
        track(3, "03 - The Rapper Eater.mp3", "03"),
    ]
    ordered = sort_music_tracks(merged_order)
    failures += check(
        "merged insertion order becomes canonical track order",
        [item.file_name for item in ordered]
        == [
            "01 - Intro.mp3",
            "02 - Nothing Can Stop Me.mp3",
            "03 - The Rapper Eater.mp3",
        ],
    )

    multi_disc = [
        track(4, "2-01 - Count Me Out.mp3", "1", None, "Count Me Out"),
        track(1, "1-02 - N95.mp3", "2", "1", "N95"),
        track(3, "1-01 - United In Grief.mp3", "1/9", "1", "United In Grief"),
    ]
    ordered = sort_music_tracks(multi_disc)
    failures += check(
        "multi-disc filename fallback preserves disc then track order",
        [item.file_name for item in ordered]
        == [
            "1-01 - United In Grief.mp3",
            "1-02 - N95.mp3",
            "2-01 - Count Me Out.mp3",
        ],
    )
    failures += check(
        "multi-disc destination filename is stable",
        music_track_filename(
            multi_disc[0].metadata_json,
            ".mp3",
            2,
            multi_disc[0].file_name,
        )
        == "2-01 - Count Me Out.mp3",
    )

    filename_fallback = track(7, "02 DJ Cinema - New York Minute.mp3")
    failures += check(
        "numeric filename prefix supplies missing track number",
        music_track_numbers(
            filename_fallback.metadata_json,
            filename_fallback.file_name,
        )
        == (1, 2),
    )

    malformed = track(8, "unknown.mp3", "side-a", "disc-x", "Unknown")
    failures += check(
        "malformed metadata does not crash",
        music_track_numbers(malformed.metadata_json, malformed.file_name) == (1, None)
        and music_track_filename(
            malformed.metadata_json,
            ".mp3",
            1,
            malformed.file_name,
        )
        == "01 - Unknown.mp3",
    )

    numeric_title_cases = [
        ("12 - 500 Degreez.flac", 1, 12, "500 Degreez"),
        ("1-02 - N95.mp3", 1, 2, "N95"),
        ("01 - 02 - Coeur D'Alene.flac", 1, 2, "Coeur D'Alene"),
        ("02 - 2000 Watts.flac", 1, 2, "2000 Watts"),
        ("05 - 405.flac", 1, 5, "405"),
        ("162 - Final Chapter.mp3", 1, 162, "Final Chapter"),
        ("1.02 - Dot Syntax.flac", 1, 2, "Dot Syntax"),
        ("1_02 - Underscore Syntax.flac", 1, 2, "Underscore Syntax"),
        ("Disc 1 Track 02 - Label Syntax.flac", 1, 2, "Label Syntax"),
    ]
    for filename, expected_disc, expected_track, expected_title in numeric_title_cases:
        evidence = track_number_evidence(
            {"tracknumber": str(expected_track), "discnumber": "1"},
            filename,
        )
        failures += check(
            f"numeric title disambiguation: {filename}",
            evidence["disc"] == expected_disc
            and evidence["filename_track"] == expected_track
            and evidence["resolved_track"] == expected_track
            and normalize_track_title_for_destination(
                Path(filename).stem,
                expected_track,
            ) == expected_title,
        )

    repair_files = [
        track(
            number,
            (
                "12 - 500 Degreez.flac"
                if number == 12
                else f"{number:02d} - Track {number:02d}.flac"
            ),
            str(number),
            "1",
            "500 Degreez" if number == 12 else f"Track {number:02d}",
        )
        for number in range(1, 22)
    ]
    repair_files[11].metadata_json["track_number_evidence"] = {
        "filename_track": 500,
        "embedded_track": 12,
        "resolved_track": 500,
        "disc": 12,
        "preferred_source": "combined_disc_track_filename_prefix",
        "warnings": ["filename_embedded_tracknumber_mismatch"],
    }
    repair_batch = SimpleNamespace(
        id=122,
        detected_type="music_album",
        status="pending_review",
        files=repair_files,
        metadata_json={
            "artist": "Lil Wayne",
            "albumartist": "Lil Wayne",
            "album": "500 Degreez",
            "year": "2002",
            "track_count": 21,
            "disc_count": 12,
            "metadata_warnings": [
                "track_number_conflict_detected",
                "partial_track_set",
            ],
        },
        updated_at=None,
    )
    repair_result = rebuild_pending_music_track_metadata(repair_batch)
    repaired_track_12 = next(
        row
        for row in repair_batch.metadata_json["tracks"]
        if row["track_number"] == 12
    )
    failures += check(
        "existing 500 Degreez batch repair rebuilds a complete single-disc track set",
        repair_result["track_count"] == 21
        and repair_result["disc_count"] == 1
        and repair_result["present_track_numbers"] == list(range(1, 22))
        and repair_result["missing_track_numbers"] == []
        and repair_result["duplicate_track_numbers"] == []
        and repair_result["track_number_conflicts"] == []
        and repair_result["completeness_status"] == "complete"
        and repaired_track_12["title"] == "500 Degreez",
    )
    failures += check(
        "repair replaces stale per-file evidence without changing file ownership",
        repair_files[11].metadata_json["track_number_evidence"]["disc"] == 1
        and repair_files[11].metadata_json["track_number_evidence"]["resolved_track"] == 12
        and all(item.id == number for number, item in enumerate(repair_files, start=1)),
    )

    vinyl_files = [
        track(
            index,
            f"{side}{side_track} Vinyl Track {side}{side_track}.flac",
            "1",
            "1",
            f"Vinyl Track {side}{side_track}",
        )
        for index, (side, side_track) in enumerate(
            [
                *(("A", number) for number in range(1, 6)),
                *(("B", number) for number in range(1, 7)),
            ],
            start=1,
        )
    ]
    vinyl_batch = SimpleNamespace(
        id=18,
        detected_type="music_album",
        status="pending_review",
        files=vinyl_files,
        metadata_json={
            "artist": "Death Cab for Cutie",
            "album": "Narrow Stairs",
            "year": "2008",
            "track_count": 11,
            "disc_count": 1,
            "metadata_warnings": ["track_number_conflict_detected"],
        },
        updated_at=None,
    )
    vinyl_result = rebuild_pending_music_track_metadata(vinyl_batch)
    failures += check(
        "vinyl A/B side positions do not conflict with each other",
        vinyl_result["track_count"] == 11
        and vinyl_result["disc_count"] == 2
        and len(vinyl_result["present_track_positions"]) == 11
        and vinyl_result["missing_track_positions"] == []
        and vinyl_result["duplicate_track_positions"] == []
        and vinyl_result["completeness_status"] == "complete"
        and vinyl_files[5].metadata_json["track_number_evidence"]["disc"] == 2
        and vinyl_files[5].metadata_json["track_number_evidence"]["resolved_track"] == 1,
    )

    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    TestSession = sessionmaker(bind=engine)
    with TestSession() as db:
        persisted_batch = IngestBatch(
            source_path="repair-persistence",
            detected_type="music_album",
            status="pending_review",
            metadata_json={
                "artist": "Lil Wayne",
                "albumartist": "Lil Wayne",
                "album": "500 Degreez",
                "year": "2002",
                "track_count": 2,
            },
        )
        persisted_batch.files = [
            IngestFile(
                file_path=f"repair-persistence/{filename}",
                file_name=filename,
                extension=".flac",
                size_bytes=1,
                detected_role="music_track",
                metadata_json={
                    "title": title,
                    "tracknumber": str(number),
                    "discnumber": "1",
                    "track_number_evidence": stale_evidence,
                },
            )
            for filename, title, number, stale_evidence in [
                (
                    "01 - Track 01.flac",
                    "Track 01",
                    1,
                    {"resolved_track": 1, "disc": 1},
                ),
                (
                    "12 - 500 Degreez.flac",
                    "500 Degreez",
                    12,
                    {"resolved_track": 500, "disc": 12},
                ),
            ]
        ]
        db.add(persisted_batch)
        db.commit()
        persisted_batch_id = persisted_batch.id
        repair_pending_music_batch_track_metadata(db, persisted_batch_id)
        db.expunge_all()
        repaired_batch = db.get(IngestBatch, persisted_batch_id)
        repaired_file = next(
            item
            for item in repaired_batch.files
            if item.file_name == "12 - 500 Degreez.flac"
        )
        persisted_evidence = repaired_file.metadata_json["track_number_evidence"]
        failures += check(
            "repaired file evidence survives database commit and reload",
            persisted_evidence["filename_track"] == 12
            and persisted_evidence["resolved_track"] == 12
            and persisted_evidence["disc"] == 1,
        )
    engine.dispose()

    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
