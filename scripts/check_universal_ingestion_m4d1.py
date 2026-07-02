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
    FragmentReconstructionDecision,
    MediaIdentityCandidate,
    MixedMediaFlag,
    SourceFragment,
)
from app.services.universal_ingestion import (  # noqa: E402
    classify_media_file,
    snapshot_universal_ingestion_boundary,
)


def music_meta(artist="Artist", album="Album", title="Song", track="1", disc=None):
    fields = {
        "artist": artist,
        "album_artist": artist,
        "albumartist": artist,
        "album": album,
        "title": title,
        "track_number": track,
        "tracknumber": track,
    }
    if disc is not None:
        fields["disc_number"] = disc
        fields["discnumber"] = disc
    return {"embedded_metadata_fields": fields, **fields}


def audio_book_meta(author="Author", title="Book", chapter="1", disc=None):
    fields = {
        "author": author,
        "album_artist": author,
        "album": title,
        "title": f"Chapter {chapter}",
        "track_number": chapter,
    }
    if disc is not None:
        fields["disc_number"] = disc
    return {"embedded_metadata_fields": fields, **fields}


def add_file(batch, relative_path, metadata=None, size=1000):
    name = Path(relative_path).name
    batch.files.append(IngestFile(
        file_path=str(Path(batch.source_path) / relative_path),
        file_name=name,
        extension=Path(name).suffix.lower(),
        size_bytes=size,
        checksum=f"sha-{batch.id}-{relative_path}",
        detected_role="unknown",
        metadata_json=metadata or {},
    ))


def make_batch(db, source_name, detected_type="unknown"):
    batch = IngestBatch(
        source_kind="manual-drop",
        source_path=str(PROJECT_ROOT / ".tmp" / source_name),
        detected_type=detected_type,
        status="pending_review",
        confidence=0.5,
        metadata_json={},
    )
    db.add(batch)
    db.flush()
    return batch


def decisions(db, batch):
    return [row.decision for row in db.query(FragmentReconstructionDecision).filter(FragmentReconstructionDecision.batch_id == batch.id).all()]


def flags(db, batch):
    return {row.flag_type for row in db.query(MixedMediaFlag).filter(MixedMediaFlag.batch_id == batch.id).all()}


def candidate_types(db, batch):
    return {row.candidate_media_type for row in db.query(MediaIdentityCandidate).filter(MediaIdentityCandidate.batch_id == batch.id).all()}


def main():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    db = Session()
    try:
        assert classify_media_file(IngestFile(file_path="x", file_name="song.mp3", extension=".mp3", size_bytes=1))[0] == "music_audio"
        assert classify_media_file(IngestFile(file_path="x", file_name="book.m4b", extension=".m4b", size_bytes=1))[0] == "audiobook_audio"
        assert classify_media_file(IngestFile(file_path="x", file_name="book.epub", extension=".epub", size_bytes=1))[0] == "ebook"
        assert classify_media_file(IngestFile(file_path="x", file_name="comic.cbz", extension=".cbz", size_bytes=1))[0] == "comic"
        assert classify_media_file(IngestFile(file_path="x", file_name="movie.srt", extension=".srt", size_bytes=1))[0] == "subtitle"
        assert classify_media_file(IngestFile(file_path="x", file_name="cover.jpg", extension=".jpg", size_bytes=1))[0] == "artwork"
        assert classify_media_file(IngestFile(file_path="x", file_name="movie.nfo", extension=".nfo", size_bytes=1))[0] == "sidecar_metadata"
        assert classify_media_file(IngestFile(file_path="x", file_name="playlist.m3u", extension=".m3u", size_bytes=1))[0] == "playlist"
        assert classify_media_file(IngestFile(file_path="x", file_name="chunk.zip", extension=".zip", size_bytes=1))[0] == "archive_file"
        assert classify_media_file(IngestFile(file_path="x", file_name="blob.bin", extension=".bin", size_bytes=1))[0] == "unknown"

        split = make_batch(db, "m4d1-split-drive")
        for folder, start in [("drive-download-20260628T012539Z-3-001", 1), ("drive-download-20260628T012539Z-3-002", 5), ("drive-download-20260628T012539Z-3-003", 9)]:
            for offset in range(4):
                track = start + offset
                add_file(split, f"{folder}/{track:02d}.mp3", music_meta(album="One Album", title=f"Track {track}", track=str(track)))
        snapshot_universal_ingestion_boundary(db, split)
        db.commit()
        assert db.query(MediaIdentityCandidate).filter(MediaIdentityCandidate.batch_id == split.id).count() == 1
        assert db.query(SourceFragment).filter(SourceFragment.batch_id == split.id, SourceFragment.fragment_group_key.isnot(None)).count() == 3
        assert "merge_recommended" in decisions(db, split)
        assert "source_fragment_group_detected" in flags(db, split)

        multidisc = make_batch(db, "m4d1-multidisc")
        for disc in (1, 2):
            for track in (1, 2, 3):
                add_file(multidisc, f"Artist/Album/CD{disc}/{track:02d}.flac", music_meta(album="Disc Album", title=f"D{disc}T{track}", track=str(track), disc=str(disc)))
        snapshot_universal_ingestion_boundary(db, multidisc)
        db.commit()
        assert db.query(MediaIdentityCandidate).filter(MediaIdentityCandidate.batch_id == multidisc.id).count() == 1
        assert "merge_recommended" in decisions(db, multidisc)
        assert "track_number_conflict" not in flags(db, multidisc)

        conflict = make_batch(db, "m4d1-disc-conflict")
        for disc in ("CD1", "CD2"):
            for track in (1, 2):
                add_file(conflict, f"Artist/Album/{disc}/{track:02d}.flac", music_meta(album="Conflict Album", title=f"{disc}T{track}", track=str(track), disc=None))
        snapshot_universal_ingestion_boundary(db, conflict)
        db.commit()
        assert "review_required" in decisions(db, conflict)
        assert {"disc_number_missing", "track_number_conflict"}.issubset(flags(db, conflict))

        mixed = make_batch(db, "m4d1-mixed")
        for track in range(1, 4):
            add_file(mixed, f"Messy/{track:02d}.mp3", music_meta(album="Messy Album", title=f"Song {track}", track=str(track)))
        add_file(mixed, "Messy/Novel.epub")
        add_file(mixed, "Messy/Comic.cbz")
        add_file(mixed, "Messy/Movie.2021.mkv", size=5_000_000)
        add_file(mixed, "Messy/cover.jpg")
        snapshot_universal_ingestion_boundary(db, mixed)
        db.commit()
        assert {"music", "ebook", "comic", "movie"}.issubset(candidate_types(db, mixed))
        assert "split_recommended" in decisions(db, mixed)
        assert "mixed_media_source" in flags(db, mixed)
        assert "artwork_without_owner" in flags(db, mixed)

        book_in_music = make_batch(db, "m4d1-book-in-music")
        add_file(book_in_music, "Artist/Album/01.mp3", music_meta(album="Album", title="Song", track="1"))
        add_file(book_in_music, "Artist/Album/Book.pdf")
        snapshot_universal_ingestion_boundary(db, book_in_music)
        db.commit()
        assert {"music", "ebook"}.issubset(candidate_types(db, book_in_music))
        assert "ambiguous_pdf_role" in flags(db, book_in_music)
        assert "split_recommended" in decisions(db, book_in_music) or "review_required" in decisions(db, book_in_music)

        audiobook = make_batch(db, "m4d1-audiobook")
        for folder, disc in (("Part1", "1"), ("Part2", "2")):
            for chapter in (1, 2):
                add_file(audiobook, f"Audiobooks/My Book/{folder}/{chapter:02d}.mp3", audio_book_meta(title="My Book", chapter=str(chapter), disc=disc))
        snapshot_universal_ingestion_boundary(db, audiobook)
        db.commit()
        assert "audiobook" in candidate_types(db, audiobook)
        assert "merge_recommended" in decisions(db, audiobook)

        video = make_batch(db, "m4d1-video")
        add_file(video, "Video Dump/Unknown Video.mkv", size=5_000_000)
        add_file(video, "Video Dump/Show.S02E03.mkv", size=2_000_000)
        snapshot_universal_ingestion_boundary(db, video)
        db.commit()
        assert {"movie", "tv"}.issubset(candidate_types(db, video))
        assert "movie_tv_ambiguous" in flags(db, video)
        assert "review_required" in decisions(db, video)

        print("AA-M4D.1 Universal Media Ingestion Boundary + Fragment Reconstruction checks passed.")
    finally:
        db.close()


if __name__ == "__main__":
    main()