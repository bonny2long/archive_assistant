"""Bounded collection checks for v2.066 movie metadata assist."""

from app.services.review_state import build_review_state
from app.services.video_metadata import parse_movie_name


def main() -> None:
    names = [
        "Black.Panther.2018.1080p.BluRay.x265.mkv",
        "Black.Panther.Wakanda.Forever.2022.2160p.WEB-DL.mkv",
    ]
    items = []
    for name in names:
        parsed = parse_movie_name(name)
        items.append({
            "source_file": name,
            "include": True,
            "title": parsed["title"],
            "year": parsed["year"],
            "edition": parsed["edition"],
            "format": "MKV",
            "accepted_unknown_title": False,
            "accepted_unknown_year": False,
            "lookup_later": False,
        })
    state = build_review_state("video_movie", {
        "title": "Black Panther Collection",
        "collection_title": "Black Panther Collection",
        "review_type": "movie_collection",
        "review_mode": "item_list",
        "video_file_count": 2,
        "movie_items": items,
        "metadata_warnings": [],
    })
    assert state["review_type"] == "movie_collection"
    assert state["review_mode"] == "item_list"
    assert state["blocking_review_items"] == []
    assert [item["year"] for item in items] == ["2018", "2022"]

    items[1]["year"] = None
    items[1]["accepted_unknown_year"] = True
    items[1]["lookup_later"] = True
    state = build_review_state("video_movie", {
        "title": "Black Panther Collection",
        "review_type": "movie_collection",
        "video_file_count": 2,
        "movie_items": items,
        "metadata_warnings": [],
    })
    assert state["blocking_review_items"] == []
    assert any(
        item["type"] == "movie_collection_item_unknown_year_accepted"
        for item in state["non_blocking_review_items"]
    )

    items[1]["accepted_unknown_year"] = False
    state = build_review_state("video_movie", {
        "title": "Black Panther Collection",
        "review_type": "movie_collection",
        "video_file_count": 2,
        "movie_items": items,
        "metadata_warnings": [],
    })
    assert any(
        item["type"] == "movie_collection_item_missing_year"
        for item in state["blocking_review_items"]
    )
    print("v2.066 movie collection metadata assist checks passed")


if __name__ == "__main__":
    main()
