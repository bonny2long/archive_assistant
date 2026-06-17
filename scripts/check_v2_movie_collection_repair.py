"""Bounded checks for v2.066a movie collection repair and approval."""

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.api.routes import approve_batch, update_movie_collection_review
from app.db.session import Base
from app.models.archive import IngestBatch
from app.schemas.archive import MovieCollectionItemUpdate
from app.schemas.archive import MovieCollectionReviewUpdate
from app.services.review_state import build_review_state
from app.services.video_metadata import parse_movie_name


FILES = [
    "A Very Harold And Kumar Christmas 2011 UNRATED 1080p BluRay HEVC x265 5.1 BONE.mkv",
    "Harold and Kumar Escape from Guantanamo Bay 2008 UNRATED 1080p BluRay HEVC x265 5.1 BONE.mkv",
    "Harold and Kumar Go to White Castle 2004 UNRATED 1080p BluRay HEVC x265 5.1 BONE.mkv",
]


def main() -> None:
    parsed = [parse_movie_name(name) for name in FILES]
    assert [item["title"] for item in parsed] == [
        "A Very Harold And Kumar Christmas",
        "Harold and Kumar Escape from Guantanamo Bay",
        "Harold and Kumar Go to White Castle",
    ]
    assert [item["year"] for item in parsed] == ["2011", "2008", "2004"]
    assert all(item["edition"] == "UNRATED" for item in parsed)

    movie_items = [
        {
            "source_file": name,
            "include": True,
            "title": item["title"],
            "year": item["year"],
            "edition": item["edition"],
            "format": "MKV",
            "accepted_unknown_title": False,
            "accepted_unknown_year": False,
            "lookup_later": False,
        }
        for name, item in zip(FILES, parsed, strict=True)
    ]
    state = build_review_state("video_movie", {
        "title": "Harold and Kumar Trilogy",
        "review_type": "movie_collection",
        "review_mode": "item_list",
        "video_file_count": 3,
        "movie_items": movie_items,
        "metadata_warnings": ["multiple_movie_candidates"],
    })
    assert state["blocking_review_items"] == []
    assert not any(
        item["type"] == "multiple_movie_candidates"
        for item in state["blocking_review_items"]
    )

    accepted = MovieCollectionItemUpdate(
        source_file="unparseable.mkv",
        title="",
        year=None,
        accepted_unknown_title=True,
        accepted_unknown_year=True,
        lookup_later=True,
    )
    state = build_review_state("video_movie", {
        "review_type": "movie_collection",
        "video_file_count": 1,
        "movie_items": [accepted.model_dump()],
        "metadata_warnings": [],
    })
    assert state["blocking_review_items"] == []
    warning_types = {
        item["type"] for item in state["non_blocking_review_items"]
    }
    assert "movie_collection_item_unknown_title_accepted" in warning_types
    assert "movie_collection_item_unknown_year_accepted" in warning_types

    rejected = accepted.model_copy(update={
        "accepted_unknown_title": False,
        "accepted_unknown_year": False,
    })
    state = build_review_state("video_movie", {
        "review_type": "movie_collection",
        "video_file_count": 1,
        "movie_items": [rejected.model_dump()],
        "metadata_warnings": [],
    })
    blocker_types = {item["type"] for item in state["blocking_review_items"]}
    assert "movie_collection_item_missing_title" in blocker_types
    assert "movie_collection_item_missing_year" in blocker_types

    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine)
    with session_factory() as db:
        batch = IngestBatch(
            source_path="C:/test/Harold and Kumar Trilogy",
            detected_type="video_movie",
            status="needs_metadata_review",
            confidence=0.7,
            suggested_destination="C:/test/Movies/Library",
            metadata_json={
                "title": "Harold and Kumar Trilogy",
                "review_type": "movie_collection",
                "review_mode": "item_list",
                "video_file_count": 3,
                "video_files": FILES,
                "movie_items": [],
                "metadata_warnings": ["multiple_movie_candidates"],
            },
        )
        db.add(batch)
        db.commit()
        db.refresh(batch)

        update = MovieCollectionReviewUpdate(
            collection_title="Harold and Kumar Trilogy",
            movies=[
                MovieCollectionItemUpdate(**item)
                for item in movie_items
            ],
        )
        summary = update_movie_collection_review(batch.id, update, db)
        assert summary.status == "pending_review"
        assert summary.metadata_confirmed is True
        assert summary.blocking_review_items == []

        approval = approve_batch(batch.id, db)
        assert approval.status == "approved"
        db.refresh(batch)
        assert batch.metadata_json["metadata_locked_for_move"] is True

    print("v2.066a movie collection repair checks passed")


if __name__ == "__main__":
    main()
