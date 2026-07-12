from __future__ import annotations

import os
import sys
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = PROJECT_ROOT / "backend"
os.environ["DEBUG"] = "true"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.db.session import Base
from app.models.archive import IngestBatch, IngestFile
from app.models.media_metadata import CandidateMember, MediaIdentityCandidate, SourceFragment
from app.services.approved_candidate_materialization import materialize_approved_candidates
from app.services.batch_split import execute_split_candidate
from app.services.candidate_move_plan_preview import build_candidate_move_plan_preview
from app.services.media_type_correction import (
    correct_batch_media_type,
    inspect_batch_media_type_recovery,
    repair_batch_media_type_from_audit,
)
from app.services.parent_candidate_materialization import build_parent_candidate_summary, is_parent_container_batch
from app.services.universal_ingestion import build_candidate_drafts, classify_batch_files
from app.services.universal_ingestion_review import create_or_update_review_action


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def file_row(path: str, album: str, source_folder: str) -> IngestFile:
    return IngestFile(
        file_path=path,
        file_name=path.rsplit("\\", 1)[-1],
        extension=".flac",
        size_bytes=100,
        detected_role="discography_track",
        metadata_json={
            "artist": "Wrong Embedded Artist",
            "albumartist": "Wrong Embedded Artist",
            "album": album,
            "_discography_album": {"source_folder": source_folder},
        },
    )


def main() -> None:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine, expire_on_commit=False)

    with session_factory() as db:
        batch = IngestBatch(
            source_path=r"C:\ready\drive-001",
            detected_type="music_album",
            status="pending_review",
            metadata_json={
                "artist": "Drew Karpyshyn",
                "album": "Star Wars The Old Republic Revan",
                "year": "2003",
                "review_origin": "multi_artist_discography_split",
            },
        )
        db.add(batch)
        db.flush()
        audio = [
            IngestFile(
                batch_id=batch.id,
                file_path=rf"C:\ready\drive-001\Star Wars The Old Republic Revan\Disc 1\{number:02d}.mp3",
                file_name=f"{number:02d}.mp3",
                extension=".mp3",
                size_bytes=100,
                detected_role="discography_track",
                metadata_json={
                    "artist": "Drew Karpyshyn",
                    "album": "Star Wars The Old Republic Revan",
                    "_discography_album": {"source_folder": "Star Wars The Old Republic Revan"},
                },
            )
            for number in (1, 2)
        ]
        db.add_all(audio)
        db.flush()
        db.commit()

        correct_batch_media_type(db, batch.id, "audiobook", confirmed=True)
        db.refresh(batch)
        require(batch.detected_type == "audiobook", "The batch type should persist as audiobook")
        require("Audiobooks" in str(batch.suggested_destination), "Audiobook destination should be rebuilt")
        require(all(item.detected_role == "audiobook_audio" for item in audio), "Audio roles should become audiobook roles")
        require(bool((batch.metadata_json or {}).get("media_type_correction_audit")), "Media correction must retain an audit entry")
        inspection = inspect_batch_media_type_recovery(db, batch.id)
        require(inspection["current_detected_type"] == "audiobook", "Recovery inspection should report the current type")
        repaired = repair_batch_media_type_from_audit(db, batch.id, confirmed=True)
        require(repaired.detected_type == "music_album", "Audit recovery should restore the previous batch type")
        require(bool((repaired.metadata_json or {}).get("media_type_recovery_audit")), "Recovery must append an audit entry")

    with session_factory() as db:
        mixed = IngestBatch(
            source_path=r"C:\ready\drive-002",
            detected_type="music_album",
            status="pending_review",
            metadata_json={"review_origin": "approved_candidate_materialization"},
        )
        mixed.files = [
            file_row(
                r"C:\ready\drive-002\Lil Wayne - Discography 1999-2023 [FLAC]\2013 - I Am Not a Human Being II\01.flac",
                "I Am Not A Human Being II",
                "Lil Wayne - Discography 1999-2023 [FLAC]",
            ),
            file_row(
                r"C:\ready\drive-003\Lil Wayne - Discography 1999-2023 [FLAC]\2000 - Lights Out\01.flac",
                "I Am Not A Human Being II",
                "Lil Wayne - Discography 1999-2023 [FLAC]",
            ),
        ]
        drafts = build_candidate_drafts(classify_batch_files(mixed))
        titles = {draft.title for draft in drafts.values()}
        require(titles == {"I Am Not a Human Being II", "Lights Out"}, "Physical release folders must override stale shared album tags for grouping")

        audiobook = IngestBatch(
            source_path=r"C:\ready\drive-004",
            detected_type="music_album",
            status="pending_review",
            metadata_json={"review_origin": "multi_artist_discography_split"},
        )
        audiobook.files = [
            IngestFile(
                file_path=rf"C:\ready\drive-004\Star Wars The Old Republic Revan\Disc {disc}\01.mp3",
                file_name="01.mp3",
                extension=".mp3",
                size_bytes=100,
                detected_role="discography_track",
                metadata_json={
                    "artist": "Drew Karpyshyn",
                    "album": "Star Wars The Old Republic Revan",
                    "_discography_album": {"source_folder": "Star Wars The Old Republic Revan"},
                },
            )
            for disc in (1, 2, 3)
        ]
        drafts = build_candidate_drafts(classify_batch_files(audiobook))
        require(len(drafts) == 1, "Disc folders must not be mistaken for separate releases")

        repaired_child = IngestBatch(
            source_path=r"C:\ready\drive-005",
            detected_type="music_album",
            status="pending_review",
            metadata_json={
                "source_parent_batch_id": 12,
                "materialization_history": [{"candidate_id": 99, "child_batch_id": 100}],
            },
        )
        require(
            is_parent_container_batch(repaired_child),
            "A child with its own materialization history must become a nested repair container",
        )

    with session_factory() as db:
        parent = IngestBatch(
            source_path=r"C:\ready\mixed-parent",
            detected_type="music_discography",
            status="pending_review",
            metadata_json={"type": "music_discography", "review_type": "music_discography"},
        )
        db.add(parent)
        db.flush()

        revan_audio = [
            IngestFile(
                batch_id=parent.id,
                file_path=rf"C:\ready\mixed-parent\Revan\Disc 1\{number:02d}.mp3",
                file_name=f"{number:02d}.mp3",
                extension=".mp3",
                size_bytes=100,
                detected_role="audiobook_audio",
                metadata_json={"author": "Drew Karpyshyn", "title": "Star Wars: The Old Republic - Revan"},
            )
            for number in (1, 2)
        ]
        music_audio = [
            IngestFile(
                batch_id=parent.id,
                file_path=rf"C:\ready\mixed-parent\Album\{number:02d}.flac",
                file_name=f"{number:02d}.flac",
                extension=".flac",
                size_bytes=100,
                detected_role="discography_track",
                metadata_json={"artist": "Test Artist", "album": "Test Album"},
            )
            for number in (1, 2)
        ]
        revan_cover = IngestFile(
            batch_id=parent.id,
            file_path=r"C:\ready\mixed-parent\Revan\cover.jpg",
            file_name="cover.jpg",
            extension=".jpg",
            size_bytes=20,
            detected_role="artwork",
            metadata_json={},
        )
        music_cover = IngestFile(
            batch_id=parent.id,
            file_path=r"C:\ready\mixed-parent\Album\cover.jpg",
            file_name="cover.jpg",
            extension=".jpg",
            size_bytes=20,
            detected_role="artwork",
            metadata_json={},
        )
        unowned_sidecar = IngestFile(
            batch_id=parent.id,
            file_path=r"C:\ready\mixed-parent\readme.nfo",
            file_name="readme.nfo",
            extension=".nfo",
            size_bytes=10,
            detected_role="metadata_sidecar",
            metadata_json={},
        )
        all_files = revan_audio + music_audio + [revan_cover, music_cover, unowned_sidecar]
        db.add_all(all_files)
        db.flush()

        fragment = SourceFragment(
            batch_id=parent.id,
            source_root=parent.source_path,
            relative_fragment_path=".",
            fragment_group_key="mixed-parent",
            file_count=len(all_files),
            media_class_counts_json={"audiobook": 3, "unknown": 3},
        )
        revan = MediaIdentityCandidate(
            batch_id=parent.id,
            candidate_key="audiobook:drew-karpyshyn:revan",
            candidate_media_type="audiobook",
            candidate_title="Star Wars: The Old Republic - Revan",
            candidate_primary_creator="Drew Karpyshyn",
            candidate_year="2011",
            candidate_confidence=0.95,
            identity_evidence_json={"source_folder": "Revan"},
        )
        music = MediaIdentityCandidate(
            batch_id=parent.id,
            candidate_key="unknown:test-artist:test-album",
            candidate_media_type="unknown",
            candidate_title="Test Album",
            candidate_primary_creator="Test Artist",
            candidate_year="2020",
            candidate_confidence=0.9,
            identity_evidence_json={"source_folder": "Album"},
        )
        db.add_all([fragment, revan, music])
        db.flush()
        for ingest_file in revan_audio:
            db.add(CandidateMember(
                candidate_id=revan.id,
                batch_file_id=ingest_file.id,
                relative_path=f"Revan/{ingest_file.file_name}",
                media_class="audiobook_audio",
                role_in_candidate="primary",
            ))
        db.add(CandidateMember(
            candidate_id=revan.id,
            batch_file_id=revan_cover.id,
            relative_path="Revan/cover.jpg",
            media_class="artwork",
            role_in_candidate="support",
        ))
        for ingest_file in music_audio:
            db.add(CandidateMember(
                candidate_id=music.id,
                batch_file_id=ingest_file.id,
                relative_path=f"Album/{ingest_file.file_name}",
                media_class="unknown",
                role_in_candidate="primary",
            ))
        db.add(CandidateMember(
            candidate_id=music.id,
            batch_file_id=music_cover.id,
            relative_path="Album/cover.jpg",
            media_class="artwork",
            role_in_candidate="support",
        ))
        db.commit()

        original_owners = {item.id: item.batch_id for item in all_files}
        original_roles = {item.id: item.detected_role for item in all_files}
        create_or_update_review_action(db, parent.id, {
            "action_type": "override_media_class",
            "candidate_id": music.id,
            "target_media_class": "music_audio",
        })
        db.refresh(parent)
        db.refresh(revan)
        db.refresh(music)
        require(parent.detected_type == "music_discography", "Candidate override must not change the parent type")
        require(revan.candidate_media_type == "audiobook", "Revan must remain an audiobook candidate")
        require(music.candidate_media_type == "unknown", "Candidate override must not rewrite stored candidate classification")
        require({item.id: item.batch_id for item in all_files} == original_owners, "Candidate override must not change file ownership")
        require({item.id: item.detected_role for item in all_files} == original_roles, "Candidate override must not change file roles")
        require(len(db.query(MediaIdentityCandidate).filter(MediaIdentityCandidate.batch_id == parent.id).all()) == 2, "Both candidates must remain visible")

        inspection = inspect_batch_media_type_recovery(db, parent.id)
        effective_classes = {row["candidate_id"]: row["effective_media_class"] for row in inspection["candidate_media_classes"]}
        require(effective_classes[music.id] == "music_audio", "Recovery inspection should expose the candidate override")
        preview = build_candidate_move_plan_preview(db, parent.id)
        preview_types = {row["candidate_id"]: row["candidate_media_type"] for row in preview["preview_groups"]}
        require(preview_types[revan.id] == "audiobook", "Move preview must retain the Revan audiobook type")
        require(preview_types[music.id] == "music", "Move preview must consume the music candidate override")

        for candidate in (revan, music):
            create_or_update_review_action(db, parent.id, {
                "action_type": "approve_candidate",
                "candidate_id": candidate.id,
            })
        result = materialize_approved_candidates(db, parent.id)
        require(result["created_count"] == 2, "Materialization should create both scoped children")
        children = [db.get(IngestBatch, child_id) for child_id in result["created_child_batch_ids"]]
        child_types = {child.detected_type for child in children if child is not None}
        require(child_types == {"audiobook", "music_album"}, "Materialization must create audiobook and music children")
        audiobook_child = next(child for child in children if child and child.detected_type == "audiobook")
        music_child = next(child for child in children if child and child.detected_type == "music_album")
        require(revan_cover.batch_id == audiobook_child.id, "Owned audiobook artwork should follow Revan")
        require(music_cover.batch_id == music_child.id, "Owned music artwork should follow its album")
        require(unowned_sidecar.batch_id == parent.id, "Unowned support files must remain on the parent for Cleaner")
        db.refresh(parent)
        require(parent.status == "split_complete", "Parent should become processed after every primary file is extracted")
        require((parent.metadata_json or {}).get("parent_media_extraction_complete") is True, "Parent must record primary media extraction completion")
        summary = build_parent_candidate_summary(db, parent)
        require(summary["remaining_primary_file_count"] == 0, "No primary files should remain on the parent")
        require(summary["remaining_support_file_count"] == 1, "The unowned sidecar should remain visible as support")
        require(len(db.query(MediaIdentityCandidate).filter(MediaIdentityCandidate.batch_id == parent.id).all()) == 2, "Materialization must preserve candidate evidence")
        direct_parent = IngestBatch(
            source_path=r"C:\ready\direct-split-parent",
            detected_type="music_discography",
            status="pending_review",
            metadata_json={"type": "music_discography"},
        )
        db.add(direct_parent)
        db.flush()
        direct_audio = IngestFile(
            batch_id=direct_parent.id,
            file_path=r"C:\ready\direct-split-parent\Revan\01.mp3",
            file_name="01.mp3",
            extension=".mp3",
            size_bytes=100,
            detected_role="discography_track",
            metadata_json={},
        )
        direct_candidate = MediaIdentityCandidate(
            batch_id=direct_parent.id,
            candidate_key="unknown:revan-repair",
            candidate_media_type="unknown",
            candidate_title="Star Wars: The Old Republic - Revan",
            candidate_primary_creator="Drew Karpyshyn",
            candidate_confidence=0.9,
            identity_evidence_json={"source_folder": "Revan"},
        )
        db.add_all([direct_audio, direct_candidate])
        db.flush()
        db.add(CandidateMember(
            candidate_id=direct_candidate.id,
            batch_file_id=direct_audio.id,
            relative_path="Revan/01.mp3",
            media_class="unknown",
            role_in_candidate="primary",
        ))
        db.commit()
        create_or_update_review_action(db, direct_parent.id, {
            "action_type": "override_media_class",
            "candidate_id": direct_candidate.id,
            "target_media_class": "audiobook_audio",
        })
        direct_result = execute_split_candidate(db, direct_parent.id, direct_candidate.id)
        require(direct_result["child_detected_type"] == "audiobook", "Direct child creation must consume the candidate override")
        db.refresh(direct_parent)
        require(direct_parent.detected_type == "music_discography", "Direct child creation must not reclassify the parent")
    print("PASS: media type correction and nested release repair")


if __name__ == "__main__":
    main()
