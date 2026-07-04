#!/usr/bin/env python3
"""AA-QA1 all-media Archive Assistant acceptance gate."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / "docs"
SCRIPTS = ROOT / "scripts"
BACKEND = ROOT / "backend"

QA1_DOC = DOCS / "Archive_Assistant_AA-QA1_All-Media_Acceptance_Gate_2026-07-03.md"
QA1_REPORT = DOCS / "AA-QA1_Manual_Test_Report_Template_2026-07-03.md"
SYSTEM1_DOC = DOCS / "Archive_Assistant_AA-SYSTEM1_Media-Wide_Scoped_Object_Contract_2026-07-03.md"
ARCHITECTURE = DOCS / "ARCHITECTURE.md"
CORE_REGRESSION = SCRIPTS / "check_core_v1_regression.py"
BATCH_SPLIT = BACKEND / "app" / "services" / "batch_split.py"
ROUTES = BACKEND / "app" / "api" / "routes.py"
MOVER = BACKEND / "app" / "services" / "mover.py"

REQUIRED_SCRIPTS = [
    "check_universal_review_contract.py",
    "check_scan_runtime_contract.py",
    "check_movie_final_polish.py",
    "check_movie_collection_split_review.py",
    "check_movie_collection_approval_fix.py",
    "check_tv_review_contract_no_regression.py",
    "check_tv_final_polish.py",
    "check_discography_album_editor.py",
    "check_discography_singles_bucket.py",
    "check_multi_artist_split_m4d5.py",
    "check_split_child_metadata_scope_m4d5_2.py",
    "check_books_parse_and_collection_review.py",
    "check_audiobook_detection_and_review_display.py",
    "check_bulk_approve.py",
    "check_system1_scoped_object_contract.py",
    "check_qa1_all_media_acceptance_gate.py",
    "check_parent_candidate_materialization_state.py",
]

OLD_MODAL_FALLBACKS = [
    "frontend/src/components/MediaReviewRouter.tsx",
    "frontend/src/components/DiscographyEditor.tsx",
    "frontend/src/components/MetadataEditor.tsx",
    "frontend/src/components/TvMetadataEditor.tsx",
    "frontend/src/components/TvEpisodeReviewPanel.tsx",
    "frontend/src/components/MovieMetadataEditor.tsx",
    "frontend/src/components/MovieCollectionEditor.tsx",
    "frontend/src/components/BookMetadataEditor.tsx",
    "frontend/src/components/BookCollectionEditor.tsx",
    "frontend/src/components/AudiobookMetadataEditor.tsx",
]

MEDIA_CLASSES = [
    "music_album",
    "music_discography",
    "split_child_music_album",
    "audiobook",
    "multi_disc_audiobook",
    "audiobook_series_or_collection",
    "ebook",
    "pdf_book",
    "book_collection",
    "comic_or_cbz_cbr",
    "movie",
    "movie_collection",
    "tv_show",
    "tv_episode",
    "tv_special_or_anime_special",
    "artwork",
    "subtitle",
    "sidecar_metadata",
    "unknown",
    "mixed_media_folder",
    "quarantine_review_item",
]

STATUS_BUCKETS = [
    "covered_by_workspace",
    "covered_by_old_modal_fallback",
    "covered_by_regression_only",
    "known_gap_not_yet_implemented",
]


def read(path: Path) -> str:
    if not path.exists():
        raise AssertionError(f"Missing required file: {path}")
    return path.read_text(encoding="utf-8")


def assert_contains(path: Path, needle: str) -> None:
    text = read(path)
    if needle not in text:
        raise AssertionError(f"Missing required text in {path}: {needle}")


def assert_file(path: Path) -> None:
    if not path.exists():
        raise AssertionError(f"Missing required file: {path}")


def assert_no_tokens(path: Path, tokens: list[str]) -> None:
    text = read(path).casefold()
    for token in tokens:
        if token.casefold() in text:
            raise AssertionError(f"Forbidden token {token!r} found in {path}")


def assert_production_deletion_absent() -> None:
    destructive_tokens = [".unlink(", "rmtree", "os.remove", "send2trash"]
    production_service_files = [
        path
        for path in (BACKEND / "app" / "services").glob("*.py")
        if path.name not in {"dev_reset.py"}
    ]
    for path in production_service_files:
        assert_no_tokens(path, destructive_tokens)


def main() -> None:
    for path in [SYSTEM1_DOC, QA1_DOC, QA1_REPORT, ARCHITECTURE, CORE_REGRESSION, BATCH_SPLIT, ROUTES, MOVER]:
        assert_file(path)

    core = read(CORE_REGRESSION)
    for script_name in REQUIRED_SCRIPTS:
        assert_file(SCRIPTS / script_name)
        if f"scripts/{script_name}" not in core:
            raise AssertionError(f"Core regression must include scripts/{script_name}")

    for fallback in OLD_MODAL_FALLBACKS:
        assert_file(ROOT / fallback)

    for phrase in [
        "Parent metadata is evidence, not truth",
        "Cleaner is the only production deletion authority",
        "Old modals remain until replaced type-by-type",
    ]:
        assert_contains(SYSTEM1_DOC, phrase)

    for phrase in [
        "All-Media Acceptance Gate",
        "No deletion",
        "No embedded tag mutation",
        "No removal of old modals",
    ]:
        assert_contains(QA1_DOC, phrase)

    for media_class in MEDIA_CLASSES:
        assert_contains(QA1_DOC, media_class)
        assert_contains(QA1_REPORT, media_class)

    for bucket in STATUS_BUCKETS:
        assert_contains(QA1_DOC, bucket)

    assert_contains(ARCHITECTURE, "AA-QA1")
    assert_contains(ARCHITECTURE, QA1_DOC.name)
    assert_contains(ARCHITECTURE, QA1_REPORT.name)
    assert_contains(ARCHITECTURE, "Media-Wide Scoped Object Contract")

    split_source = read(BATCH_SPLIT)
    if "metadata = deepcopy(album)" in split_source:
        raise AssertionError("Split children must not deep-copy parent album metadata")
    for phrase in [
        "def _partition_child_files",
        "audio_files",
        "artwork_files",
        "sidecar_files",
        "tracks = [_track_from_audio_file(file) for file in audio_files]",
        "suggested_destination=_library_album_destination(album_metadata)",
        "suggested_metadata=_suggested_metadata(album_metadata)",
    ]:
        if phrase not in split_source:
            raise AssertionError(f"Missing split child scoped metadata phrase: {phrase}")

    routes_source = read(ROUTES)
    mover_source = read(MOVER)
    if '@router.post("/move/approved"' not in routes_source:
        raise AssertionError("Move endpoint must remain explicit and approved-only")
    if 'IngestBatch.status == "approved"' not in routes_source:
        raise AssertionError("Move route must select approved batches only")
    if 'move_approved_batches' not in mover_source:
        raise AssertionError("Move implementation must remain approval-scoped")
    assert_no_tokens(MOVER, ["overwrite=True", "dirs_exist_ok=True", "mutagen", ".save("])
    assert_production_deletion_absent()

    print("PASS - AA-QA1 all-media acceptance gate verified")


if __name__ == "__main__":
    main()
