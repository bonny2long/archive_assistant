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
from app.models.media_metadata import UniversalIngestionReviewAction  # noqa: E402
from app.services.candidate_move_plan_preview import build_candidate_move_plan_preview  # noqa: E402
from app.services.universal_ingestion import snapshot_universal_ingestion_boundary  # noqa: E402

failures = []


def check(description, func):
    try:
        func()
        print(f"PASS: {description}")
    except Exception as exc:
        failures.append((description, str(exc)))
        print(f"FAIL: {description} - {exc}")


def add_file(batch, relative_path, metadata=None):
    name = Path(relative_path).name
    batch.files.append(IngestFile(
        file_path=str(Path(batch.source_path) / relative_path),
        file_name=name,
        extension=Path(name).suffix.lower(),
        size_bytes=1234,
        checksum=f"sha-{batch.id}-{relative_path}",
        detected_role="unknown",
        metadata_json=metadata or {},
    ))


def music_meta(album="Album", artist="Artist", title="Song", track="1"):
    fields = {"artist": artist, "album_artist": artist, "album": album, "title": title, "track_number": track, "year": "2001"}
    return {"embedded_metadata_fields": fields, **fields}


def book_meta(title="Book", author="Author"):
    fields = {"title": title, "author": author, "year": "1999"}
    return {"embedded_metadata_fields": fields, **fields}


def batch(db, name, analyzed=True):
    row = IngestBatch(source_kind="manual-drop", source_path=str(PROJECT_ROOT / ".tmp" / name), detected_type="unknown", status="pending_review", confidence=0.5, metadata_json={})
    db.add(row)
    db.flush()
    if analyzed:
        add_file(row, "Album/01.mp3", music_meta())
        snapshot_universal_ingestion_boundary(db, row)
        db.commit()
    return row


def first_group(preview):
    assert preview["preview_groups"]
    return preview["preview_groups"][0]


def main():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    db = Session()
    try:
        def music_clean():
            b = batch(db, "m4d5-clean")
            p = build_candidate_move_plan_preview(db, b.id)
            g = first_group(p)
            assert p["status"] == "ready"
            assert g["target_library"] == "Music/Library"
            assert "Music/Library" in g["destination_preview"]

        def music_fragmented():
            b = IngestBatch(source_kind="manual-drop", source_path=str(PROJECT_ROOT / ".tmp" / "m4d5-frag"), detected_type="unknown", status="pending_review", confidence=0.5, metadata_json={})
            db.add(b); db.flush()
            add_file(b, "drive-download-20260702T010101Z-1-001/01.mp3", music_meta(track="1"))
            add_file(b, "drive-download-20260702T010101Z-1-002/02.mp3", music_meta(track="2"))
            snapshot_universal_ingestion_boundary(db, b); db.commit()
            p = build_candidate_move_plan_preview(db, b.id)
            assert p["summary"]["music_only_fragmented"] is True

        def mixed_music_ebook():
            b = IngestBatch(source_kind="manual-drop", source_path=str(PROJECT_ROOT / ".tmp" / "m4d5-mixed"), detected_type="unknown", status="pending_review", confidence=0.5, metadata_json={})
            db.add(b); db.flush()
            add_file(b, "Mixed/01.mp3", music_meta())
            add_file(b, "Mixed/Book.epub", book_meta())
            snapshot_universal_ingestion_boundary(db, b); db.commit()
            p = build_candidate_move_plan_preview(db, b.id)
            assert p["summary"]["mixed_media"] is True

        def candidate_routes(ext, expected):
            b = IngestBatch(source_kind="manual-drop", source_path=str(PROJECT_ROOT / ".tmp" / f"m4d5-{ext}"), detected_type="unknown", status="pending_review", confidence=0.5, metadata_json={})
            db.add(b); db.flush()
            if ext == "m4b": add_file(b, "Book/Book.m4b", {"embedded_metadata_fields": {"author": "Author", "album": "Audio Book", "title": "Chapter 1"}})
            elif ext == "epub": add_file(b, "Book/Book.epub", book_meta())
            elif ext == "cbz": add_file(b, "Comic/Comic.cbz")
            elif ext == "mkv": add_file(b, "Movie.2020/Movie.2020.mkv")
            elif ext == "tv": add_file(b, "Show/Show.S01E01.mkv")
            snapshot_universal_ingestion_boundary(db, b); db.commit()
            p = build_candidate_move_plan_preview(db, b.id)
            assert any(group["target_library"] == expected for group in p["preview_groups"])

        def weak_identity():
            b = IngestBatch(source_kind="manual-drop", source_path=str(PROJECT_ROOT / ".tmp" / "m4d5-weak"), detected_type="unknown", status="pending_review", confidence=0.5, metadata_json={})
            db.add(b); db.flush()
            add_file(b, "drive-download-20260628T012539Z-3-001/01.mp3", music_meta(album="drive-download-20260628T012539Z-3-001"))
            snapshot_universal_ingestion_boundary(db, b); db.commit()
            p = build_candidate_move_plan_preview(db, b.id)
            g = first_group(p)
            assert g["requires_review"] is True
            assert g["target_library"] == "_REVIEW/Weak Identity"

        def with_action(action_type, expected_target=None, override=None):
            b = batch(db, f"m4d5-action-{action_type}")
            p = build_candidate_move_plan_preview(db, b.id)
            cid = first_group(p)["candidate_id"]
            row = UniversalIngestionReviewAction(batch_id=b.id, candidate_id=cid, action_type=action_type, decision_status="active", **(override or {}))
            db.add(row); db.commit()
            p = build_candidate_move_plan_preview(db, b.id)
            g = first_group(p)
            if expected_target:
                assert g["target_library"] == expected_target
            return g

        def exclude_action():
            assert with_action("exclude_from_move_plan", "_EXCLUDED_FROM_MOVE_PLAN")["destination_preview"] == "_EXCLUDED_FROM_MOVE_PLAN"

        def override_class():
            assert with_action("override_media_class", "Books/Library", {"target_media_class": "ebook"})["target_library"] == "Books/Library"

        def override_identity():
            g = with_action("override_identity", None, {"override_title": "New Title", "override_primary_creator": "New Artist", "override_year": "1984"})
            assert "New Title" in g["destination_preview"]
            assert "New Artist" in g["destination_preview"]

        def block_action():
            assert with_action("block_candidate", None)["blocked"] is True

        def no_analysis():
            b = batch(db, "m4d5-no-analysis", analyzed=False)
            p = build_candidate_move_plan_preview(db, b.id)
            assert p["status"] == "not_analyzed"

        check("Music-only clean candidate returns music preview", music_clean)
        check("Music-only fragmented batch is identified", music_fragmented)
        check("Mixed music + ebook batch is mixed media", mixed_music_ebook)
        check("Audiobook routes to Audiobooks/Library", lambda: candidate_routes("m4b", "Audiobooks/Library"))
        check("Ebook routes to Books/Library", lambda: candidate_routes("epub", "Books/Library"))
        check("Comic routes to Comics/Library", lambda: candidate_routes("cbz", "Comics/Library"))
        check("Movie routes to Movies/Library", lambda: candidate_routes("mkv", "Movies/Library"))
        check("TV routes to TV/Library", lambda: candidate_routes("tv", "TV/Library"))
        check("Source chunk identity routes to weak identity review", weak_identity)
        check("Exclude action changes target", exclude_action)
        check("Media class override changes target", override_class)
        check("Identity override changes destination", override_identity)
        check("Blocked action marks group blocked", block_action)
        check("No analysis returns not_analyzed", no_analysis)
    finally:
        db.close()
    if failures:
        raise SystemExit(1)


if __name__ == "__main__":
    main()