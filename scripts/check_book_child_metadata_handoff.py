#!/usr/bin/env python3
"""Verify reviewed collection metadata survives book child materialization."""

from __future__ import annotations

import os
import sys
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = PROJECT_ROOT / "backend"
os.environ["DEBUG"] = "true"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.db.session import Base  # noqa: E402
from app.models.archive import IngestBatch, IngestFile  # noqa: E402
from app.models.media_metadata import (  # noqa: E402
    CandidateMember,
    MediaIdentityCandidate,
    UniversalIngestionReviewAction,
)
from app.services.approved_candidate_materialization import (  # noqa: E402
    materialize_approved_candidates,
    repair_materialized_book_children,
)
from app.services.universal_ingestion import (  # noqa: E402
    ClassifiedFile,
    build_candidate_drafts,
)


BOOKS = [
    {
        "source_file": "1 - Dune - Frank Herbert (1965).epub",
        "title": "Dune",
        "author": "Frank Herbert",
        "year": "1965",
        "series": "Dune",
        "series_index": "1",
    },
    {
        "source_file": "6 - Chapter House Dune - Frank Herbert (1985).epub",
        "title": "Chapter House Dune",
        "author": "Frank Herbert",
        "year": "1985",
        "series": "Dune",
        "series_index": "6",
    },
]


def add_parent(db) -> tuple[IngestBatch, list[IngestFile]]:
    items = []
    for book in BOOKS:
        items.append({
            **book,
            "source_key": book["source_file"],
            "include": True,
            "format": "EPUB",
            "metadata_candidates": {
                "title": [{"value": book["title"], "source": "epub_package_title"}],
                "author": [{"value": book["author"], "source": "epub_package_author"}],
                "year": [{"value": book["year"], "source": "epub_package_year"}],
            },
            "candidate_notes": [],
            "candidate_runtime": {},
            "matched_artwork": None,
            "alternate_formats": [],
        })
    parent = IngestBatch(
        source_kind="manual-drop",
        source_path=str(PROJECT_ROOT / ".tmp" / "Dune Collection"),
        detected_type="book",
        status="pending_review",
        confidence=0.9,
        metadata_json={
            "review_type": "book_collection",
            "review_mode": "item_list",
            "book_items": items,
            "collection_title": "Dune",
            "keep_collection_together": False,
        },
    )
    db.add(parent)
    db.flush()
    files = []
    for index, book in enumerate(BOOKS, start=1):
        ingest_file = IngestFile(
            batch_id=parent.id,
            file_path=str(Path(parent.source_path) / book["source_file"]),
            file_name=book["source_file"],
            extension=".epub",
            size_bytes=4096 * index,
            checksum=f"book-{index}",
            detected_role="book_file",
            metadata_json=None,
        )
        db.add(ingest_file)
        files.append(ingest_file)
    db.flush()
    return parent, files


def add_weak_candidates(db, parent: IngestBatch, files: list[IngestFile]) -> None:
    for index, ingest_file in enumerate(files, start=1):
        candidate = MediaIdentityCandidate(
            batch_id=parent.id,
            candidate_key=f"ebook:unknown:{index}",
            candidate_media_type="ebook",
            candidate_title=Path(ingest_file.file_name).stem,
            candidate_primary_creator=None,
            candidate_year=None,
            candidate_confidence=0.58,
            identity_evidence_json={"identity_source": "filename"},
        )
        db.add(candidate)
        db.flush()
        db.add(CandidateMember(
            candidate_id=candidate.id,
            batch_file_id=ingest_file.id,
            relative_path=ingest_file.file_name,
            media_class="ebook",
            role_in_candidate="primary",
            sort_key=ingest_file.file_name,
            evidence_json={},
        ))
        db.add(UniversalIngestionReviewAction(
            batch_id=parent.id,
            candidate_id=candidate.id,
            action_type="approve_candidate",
            decision_status="active",
            reason="book metadata handoff regression",
        ))
    db.commit()


def test_candidate_identity_uses_parent_item(
    parent: IngestBatch,
    ingest_file: IngestFile,
) -> None:
    classified = ClassifiedFile(
        ingest_file=ingest_file,
        relative_path=ingest_file.file_name,
        fragment_path="Dune Collection",
        media_class="ebook",
        evidence={},
    )
    drafts = build_candidate_drafts([classified], parent)
    draft = next(iter(drafts.values()))
    assert draft.title == "Dune"
    assert draft.primary_creator == "Frank Herbert"
    assert draft.year == "1965"
    assert draft.series == "Dune"
    assert draft.series_index == "1"
    assert draft.evidence["identity"]["identity_source"] == "parent_book_item"


def test_materialization_and_repair(db) -> None:
    parent, files = add_parent(db)
    test_candidate_identity_uses_parent_item(parent, files[0])
    add_weak_candidates(db, parent, files)

    result = materialize_approved_candidates(db, parent.id)
    assert result["created_count"] == 2
    children = [
        db.get(IngestBatch, child_id)
        for child_id in result["created_child_batch_ids"]
    ]
    assert all(child is not None for child in children)
    children_by_file = {
        child.metadata_json["primary_book_file"]: child
        for child in children
    }
    for expected in BOOKS:
        child = children_by_file[expected["source_file"]]
        metadata = child.metadata_json
        assert child.detected_type == "book"
        assert metadata["title"] == expected["title"]
        assert metadata["author"] == expected["author"]
        assert metadata["year"] == expected["year"]
        assert metadata["series"] == expected["series"]
        assert metadata["series_index"] == expected["series_index"]
        assert metadata["format"] == "EPUB"
        assert metadata["review_type"] == "book"
        assert metadata["metadata_candidates"]["title"]
        assert child.suggested_metadata["title"] == expected["title"]
        assert child.suggested_metadata["author"] == expected["author"]
        assert child.suggested_metadata["format"] == "EPUB"
        destination = child.suggested_destination.replace("\\", "/")
        assert "/Books/EPUB/Frank Herbert/" in destination
        assert f"{expected['year']} - {expected['title']}" in destination
        assert child.metadata_confirmed is False

    stale = children_by_file[BOOKS[1]["source_file"]]
    stale_metadata = dict(stale.metadata_json)
    stale_metadata.update({
        "title": Path(BOOKS[1]["source_file"]).stem,
        "author": "Unknown Creator",
        "year": None,
        "format": None,
        "primary_book_file": None,
    })
    stale.metadata_json = stale_metadata
    stale.suggested_metadata = {
        "title": Path(BOOKS[1]["source_file"]).stem,
        "author": "Unknown Creator",
        "year": None,
    }
    stale.suggested_destination = "Books/MP3/Unknown Creator/Unknown Year"
    db.commit()

    dry_run = repair_materialized_book_children(
        db,
        parent_batch_id=parent.id,
        apply=False,
    )
    assert dry_run["repairable_child_batch_ids"] == [stale.id]
    assert db.get(IngestBatch, stale.id).metadata_json["author"] == "Unknown Creator"

    repaired = repair_materialized_book_children(
        db,
        parent_batch_id=parent.id,
        apply=True,
    )
    assert repaired["repaired_child_batch_ids"] == [stale.id]
    db.refresh(stale)
    assert stale.metadata_json["title"] == "Chapter House Dune"
    assert stale.metadata_json["author"] == "Frank Herbert"
    assert stale.metadata_json["year"] == "1985"
    assert stale.metadata_json["format"] == "EPUB"
    assert stale.metadata_json["primary_book_file"] == BOOKS[1]["source_file"]
    assert stale.metadata_json["book_child_metadata_repair_audit"]
    assert "/Books/EPUB/Frank Herbert/1985 - Chapter House Dune" in (
        stale.suggested_destination.replace("\\", "/")
    )

    second = repair_materialized_book_children(
        db,
        parent_batch_id=parent.id,
        apply=True,
    )
    assert second["repaired_count"] == 0


def main() -> None:
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    db = Session()
    try:
        test_materialization_and_repair(db)
        print("PASS - reviewed book metadata survives child materialization")
    finally:
        db.close()


if __name__ == "__main__":
    main()
