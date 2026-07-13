from __future__ import annotations

import os
import sys
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = PROJECT_ROOT / "backend"
os.environ["DEBUG"] = "true"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.db.session import Base
from app.models.archive import IngestBatch, IngestFile
from app.models.media_metadata import (
    CandidateMember,
    MediaIdentityCandidate,
    MixedMediaFlag,
    UniversalIngestionReviewAction,
)
from app.services.audiobook_candidate_repair import repair_audiobook_candidate_grouping
from app.services.parent_candidate_materialization import build_parent_candidate_summary
from app.services.universal_ingestion import build_candidate_drafts, classify_batch_files
from app.services.universal_review_routing import get_batch_routing_decision

DISC_COUNTS = [15, 16, 17, 18, 20, 19, 18, 19, 19]
GENERIC_ALBUMS = [
    "Unknown Album (11/19/2011 3:04:25 PM)",
    "Unknown Album (11/19/2011 3:09:44 PM)",
    "Unknown Album (11/19/2011 3:14:38 PM)",
    "Unknown Album (11/19/2011 3:20:51 PM)",
    "Unknown Album (11/19/2011 3:30:58 PM)",
    "Unknown Album (11/19/2011 3:36:12 PM)",
    "Unknown Album (11/19/2011 3:40:42 PM)",
    "Unknown Album (11/19/2011 3:44:49 PM)",
    "Unknown Album (11/19/2011 3:49:15 PM)",
]
BOOK_TITLE = "Star Wars The Old Republic Revan"
AUTHOR = "Drew Karpyshyn"


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def audiobook_file(disc: int, track: int, generic_album: str) -> IngestFile:
    name = f"{track:02d} Track {track}.mp3"
    path = rf"C:\ready\drive-download-20260628T012539Z-3-{disc:03d}\{BOOK_TITLE}\Disc {disc}\{name}"
    return IngestFile(
        file_path=path,
        file_name=name,
        extension=".mp3",
        size_bytes=100,
        detected_role="audiobook_audio",
        metadata_json={
            "author": AUTHOR,
            "artist": AUTHOR,
            "album": BOOK_TITLE,
            "title": f"Track {track}",
            "tracknumber": str(track),
            "discnumber": disc,
            "date": "2003",
            "embedded_metadata_fields": {
                "album": generic_album,
                "title": f"Track {track}",
                "track_number": str(track),
            },
        },
    )


def main() -> None:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, expire_on_commit=False)

    with Session() as db:
        batch = IngestBatch(
            source_kind="manual-drop",
            source_path=r"C:\ready",
            detected_type="audiobook",
            status="needs_metadata_review",
            metadata_json={
                "author": AUTHOR,
                "artist": AUTHOR,
                "title": BOOK_TITLE,
                "album": BOOK_TITLE,
                "year": "2003",
                "disc_count": 9,
            },
            suggested_metadata={"author": AUTHOR, "title": BOOK_TITLE, "year": "2003"},
        )
        db.add(batch)
        db.flush()
        for disc, count in enumerate(DISC_COUNTS, start=1):
            for track in range(1, count + 1):
                item = audiobook_file(disc, track, GENERIC_ALBUMS[disc - 1])
                item.batch_id = batch.id
                db.add(item)
        db.add(IngestFile(
            batch_id=batch.id,
            file_path=rf"C:\ready\drive-download-20260628T012539Z-3-001\{BOOK_TITLE}\{BOOK_TITLE}.jpg",
            file_name=f"{BOOK_TITLE}.jpg",
            extension=".jpg",
            size_bytes=50,
            detected_role="artwork",
            metadata_json={},
        ))
        db.flush()
        require(sum(DISC_COUNTS) == 161, "Fixture must contain 161 audiobook files")
        require(len(batch.files) == 162, "Fixture must contain 161 audio files and one cover")

        old_candidates = []
        for index, generic_album in enumerate(GENERIC_ALBUMS, start=1):
            candidate = MediaIdentityCandidate(
                batch_id=batch.id,
                candidate_key=f"audiobook:{index}",
                candidate_media_type="audiobook",
                candidate_title=generic_album,
                candidate_primary_creator=AUTHOR,
                candidate_confidence=0.82,
                identity_evidence_json={},
            )
            db.add(candidate)
            old_candidates.append(candidate)
        db.flush()
        db.add(UniversalIngestionReviewAction(
            batch_id=batch.id,
            candidate_id=old_candidates[0].id,
            action_type="mark_review_later",
            decision_status="active",
        ))
        db.commit()

        parent_summary = build_parent_candidate_summary(db, batch)
        require(parent_summary["active_parent_file_count"] == 162, "Multi-candidate summary must report attached inventory")
        before_owners = {item.id: item.batch_id for item in batch.files}
        result = repair_audiobook_candidate_grouping(db, batch.id)
        require(result["previous_candidate_count"] == 9, "Repair should replace nine false candidates")
        require(result["candidate_count"] == 1, "Repair must produce one audiobook candidate")
        require(result["primary_file_count"] == 161, "All audiobook files must remain primary members")
        require(result["support_file_count"] == 1, "The cover must remain a support file")
        require(result["disc_count"] == 9, "Disc evidence must retain all nine discs")
        require(result["file_ownership_preserved"], "Repair must verify file ownership")

        candidate = db.query(MediaIdentityCandidate).filter_by(batch_id=batch.id).one()
        require(candidate.candidate_media_type == "audiobook", "Candidate must remain audiobook")
        require(candidate.candidate_title == BOOK_TITLE, "Candidate must use the real book title")
        require(candidate.candidate_primary_creator == AUTHOR, "Candidate must use the real author")
        members = db.query(CandidateMember).filter_by(candidate_id=candidate.id).all()
        require(len(members) == 162, "One candidate must expose all audio and cover members")
        require(len([member for member in members if member.role_in_candidate == "primary"]) == 161, "All audio files must be primary")
        require(len([member for member in members if member.role_in_candidate == "support"]) == 1, "Cover must attach as support")
        identity = (candidate.identity_evidence_json or {}).get("identity") or {}
        require(identity.get("generic_embedded_values") == GENERIC_ALBUMS, "Generic timestamps must remain evidence")
        require(identity.get("single_book_multidisc_collapse") is True, "Candidate must record the collapse proof")

        flags = {row[0] for row in db.query(MixedMediaFlag.flag_type).filter_by(batch_id=batch.id).all()}
        forbidden = {
            "multiple_candidate_groups", "multiple_embedded_album_values", "audiobook_in_music_batch",
            "non_music_candidate_present", "mixed_media_detected", "artwork_without_owner",
            "split_release_candidate",
        }
        require(not (flags & forbidden), f"Stale flags remain: {sorted(flags & forbidden)}")
        routing = get_batch_routing_decision(db, batch.id)
        require(routing["decision"] == "audiobook_editor_allowed", "One book must route to the audiobook editor")
        require(routing["allowed_editors"] == ["audiobook", "universal"], "Audiobook and universal editors must be allowed")
        require(routing["summary"]["embedded_album_value_count"] == 1, "Generic timestamps must not count as releases")
        after_owners = {item.id: item.batch_id for item in db.query(IngestFile).filter(IngestFile.id.in_(before_owners)).all()}
        require(after_owners == before_owners, "No file owner may change")
        action = db.query(UniversalIngestionReviewAction).filter_by(batch_id=batch.id).one()
        require(action.decision_status == "cleared" and action.candidate_id is None, "Stale action must remain as cleared audit")
        require(bool((batch.metadata_json or {}).get("audiobook_candidate_repair_audit")), "Repair audit must persist")

    with Session() as db:
        mixed = IngestBatch(
            source_kind="manual-drop",
            source_path=r"C:\ready",
            detected_type="audiobook",
            status="pending_review",
            metadata_json={"author": AUTHOR, "title": BOOK_TITLE},
        )
        mixed.files = [
            IngestFile(
                file_path=rf"C:\ready\chunk-001\{BOOK_TITLE}\Disc 1\01.mp3",
                file_name="01.mp3", extension=".mp3", size_bytes=100,
                detected_role="audiobook_audio",
                metadata_json={"author": AUTHOR, "album": BOOK_TITLE, "tracknumber": "1", "discnumber": "1"},
            ),
            IngestFile(
                file_path=r"C:\ready\chunk-002\A Different Book\Disc 1\01.mp3",
                file_name="01.mp3", extension=".mp3", size_bytes=100,
                detected_role="audiobook_audio",
                metadata_json={"author": "Another Author", "album": "A Different Book", "tracknumber": "1", "discnumber": "1"},
            ),
        ]
        drafts = build_candidate_drafts(classify_batch_files(mixed), mixed)
        require(len(drafts) == 2, "Unrelated audiobook roots must remain separate candidates")

    repair_source = (BACKEND_ROOT / "app/services/audiobook_candidate_repair.py").read_text(encoding="utf-8")
    require("scan_ingest" not in repair_source and "scan_ready" not in repair_source, "Repair must not invoke intake scanning")
    print("audiobook multidisc candidate collapse checks passed")


if __name__ == "__main__":
    main()