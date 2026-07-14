"""Regression checks for encoding-safe dashboard display labels."""

from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = PROJECT_ROOT / "backend"
sys.path.insert(0, str(BACKEND_ROOT))

from app.services.batch_display import build_batch_display_fields


def _batch(detected_type: str, metadata: dict) -> SimpleNamespace:
    return SimpleNamespace(
        detected_type=detected_type,
        metadata_json=metadata,
        source_path="",
    )


def _assert_encoding_safe(value: str) -> None:
    for marker in ("\u00c3", "\u00c2", "\u00e2"):
        assert marker not in value, f"Mojibake marker {marker!r} found in {value!r}"


def main() -> int:
    book = build_batch_display_fields(
        _batch("book", {"title": "Dune", "author": "Frank Herbert", "year": 1965})
    )
    assert book["secondary_name"] == "Frank Herbert | 1965"
    _assert_encoding_safe(book["secondary_name"])

    tv = build_batch_display_fields(
        _batch(
            "video_tv_show",
            {"show_title": "Severance", "season_count": 1, "episode_count": 9, "video_file_count": 9},
        )
    )
    assert tv["secondary_name"] == "1 season | 9 episodes"
    _assert_encoding_safe(tv["secondary_name"])

    audiobook = build_batch_display_fields(
        _batch(
            "audiobook",
            {
                "title": "Star Wars: The Old Republic: Revan",
                "author": "Drew Karpyshyn",
                "narrator": "Marc Thompson",
                "year": 2011,
            },
        )
    )
    assert audiobook["secondary_name"] == (
        "Star Wars: The Old Republic: Revan | Narrated by Marc Thompson | 2011"
    )
    _assert_encoding_safe(audiobook["secondary_name"])

    print("PASS: book, TV, and audiobook display labels are encoding-safe")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
