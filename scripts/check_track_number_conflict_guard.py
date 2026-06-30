import os
import sys
from pathlib import Path
from types import SimpleNamespace

PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = PROJECT_ROOT / "backend"
os.environ["DEBUG"] = "true"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.services.music_metadata import (  # noqa: E402
    apply_track_number_conflict_warnings,
    find_music_track_number_conflicts,
    music_track_filename,
    music_track_numbers,
    normalize_track_title_for_destination,
    sort_music_tracks,
    track_number_evidence,
)


def file(name: str, metadata: dict) -> SimpleNamespace:
    metadata = dict(metadata)
    metadata.setdefault("source_filename", name)
    return SimpleNamespace(file_name=name, metadata_json=metadata, id=0)


def main() -> None:
    bad = file("04 - Skew It On The Bar-B.mp3", {"tracknumber": "13", "title": "Skew It On The Bar-B"})
    duplicate = file("13 - Y'All Scared.mp3", {"tracknumber": "13", "title": "Y'All Scared"})
    clean = file("01 - Return of the G.mp3", {"tracknumber": "1", "title": "Return of the G"})
    metadata = {"metadata_warnings": []}
    apply_track_number_conflict_warnings(metadata, [bad, duplicate, clean])

    summary = metadata["track_number_conflicts"]
    assert 13 in summary["duplicate_embedded_track_numbers"]
    assert summary["filename_embedded_mismatch_count"] == 1
    assert "track_number_conflict_detected" in metadata["metadata_warnings"]

    evidence = bad.metadata_json["track_number_evidence"]
    assert evidence["filename_track"] == 4
    assert evidence["embedded_track"] == 13
    assert evidence["resolved_track"] == 4
    assert evidence["preferred_source"] == "filename_prefix"
    assert "filename_embedded_tracknumber_mismatch" in evidence["warnings"]

    assert music_track_numbers(bad.metadata_json, bad.file_name) == (1, 4)
    assert music_track_filename(
        bad.metadata_json,
        ".mp3",
        1,
        bad.file_name,
    ) == "04 - Skew It On The Bar-B.mp3"
    assert normalize_track_title_for_destination("04 - Skew It On The Bar-B", 4) == "Skew It On The Bar-B"

    clean_album = [
        file("song-a.mp3", {"tracknumber": "2", "title": "Song A"}),
        file("song-b.mp3", {"tracknumber": "1", "title": "Song B"}),
    ]
    clean_meta = {"metadata_warnings": []}
    apply_track_number_conflict_warnings(clean_meta, clean_album)
    assert clean_meta["track_number_conflicts"]["conflict_count"] == 0
    assert [item.metadata_json["title"] for item in sort_music_tracks(clean_album)] == ["Song B", "Song A"]

    missing = track_number_evidence({"title": "Intro"}, "01 - Intro.mp3")
    assert missing["resolved_track"] == 1
    assert "missing_tracknumber_but_filename_available" in missing["warnings"]

    ambiguous_meta = {"metadata_warnings": []}
    ambiguous_files = [
        file("alpha.mp3", {"tracknumber": "7", "title": "Alpha"}),
        file("beta.mp3", {"tracknumber": "7", "title": "Beta"}),
    ]
    apply_track_number_conflict_warnings(ambiguous_meta, ambiguous_files)
    assert "track_order_ambiguous" in ambiguous_meta["metadata_warnings"]
    assert find_music_track_number_conflicts(ambiguous_files)["ambiguous_count"] == 2

    print("Track number conflict guard checks passed.")


if __name__ == "__main__":
    main()