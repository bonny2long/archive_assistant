#!/usr/bin/env python3
"""Guardrail for the AA-SYSTEM1 media-wide scoped object contract."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DOC = ROOT / "docs" / "Archive_Assistant_AA-SYSTEM1_Media-Wide_Scoped_Object_Contract_2026-07-03.md"
ARCHITECTURE = ROOT / "docs" / "ARCHITECTURE.md"
BATCH_SPLIT = ROOT / "backend" / "app" / "services" / "batch_split.py"
CORE_REGRESSION = ROOT / "scripts" / "check_core_v1_regression.py"


def assert_contains(path: Path, needle: str) -> None:
    text = path.read_text(encoding="utf-8")
    if needle not in text:
        raise AssertionError(f"Missing required text in {path}: {needle}")


def main() -> None:
    if not DOC.exists():
        raise AssertionError(f"Missing AA-SYSTEM1 contract doc: {DOC}")

    for phrase in [
        "Archive Assistant is the NAS-wide ingestion",
        "file-scoped",
        "Parent metadata is evidence, not truth",
        "Cleaner is the only production deletion authority",
        "Old modals remain until replaced type-by-type",
    ]:
        assert_contains(DOC, phrase)

    assert_contains(ARCHITECTURE, "Media-Wide Scoped Object Contract")
    assert_contains(ARCHITECTURE, DOC.name)

    split_source = BATCH_SPLIT.read_text(encoding="utf-8")
    if "metadata = deepcopy(album)" in split_source:
        raise AssertionError("batch_split.py must not deep-copy parent album metadata into split children")
    for phrase in [
        "def _partition_child_files",
        "files_to_move: list[IngestFile]",
        "tracks = [_track_from_audio_file(file) for file in audio_files]",
        "suggested_destination=_library_album_destination(album_metadata)",
        "suggested_metadata=_suggested_metadata(album_metadata)",
    ]:
        if phrase not in split_source:
            raise AssertionError(f"Missing scoped split metadata guard in batch_split.py: {phrase}")

    assert_contains(CORE_REGRESSION, "scripts/check_system1_scoped_object_contract.py")
    print("PASS - AA-SYSTEM1 media-wide scoped object contract guard verified")


if __name__ == "__main__":
    main()