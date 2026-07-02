from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, JSON, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.time import now_utc
from app.db.session import Base


class MediaFile(Base):
    __tablename__ = "media_files"
    __table_args__ = (
        UniqueConstraint("ingest_file_id", name="uq_media_files_ingest_file_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    ingest_file_id: Mapped[int | None] = mapped_column(ForeignKey("ingest_files.id"), nullable=True, index=True)
    ingest_batch_id: Mapped[int | None] = mapped_column(ForeignKey("ingest_batches.id"), nullable=True, index=True)
    absolute_path: Mapped[str] = mapped_column(Text)
    relative_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    file_name: Mapped[str] = mapped_column(Text)
    extension: Mapped[str] = mapped_column(String(20))
    size_bytes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    checksum: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    media_type: Mapped[str] = mapped_column(String(50), default="music")
    detected_role: Mapped[str | None] = mapped_column(String(50), nullable=True)
    duration_seconds: Mapped[float | None] = mapped_column(Float, nullable=True)
    bitrate: Mapped[int | None] = mapped_column(Integer, nullable=True)
    sample_rate: Mapped[int | None] = mapped_column(Integer, nullable=True)
    codec: Mapped[str | None] = mapped_column(Text, nullable=True)
    container: Mapped[str | None] = mapped_column(String(50), nullable=True)
    embedded_artwork_count: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)

    raw_tags: Mapped[list["RawMediaTag"]] = relationship(back_populates="media_file", cascade="all, delete-orphan")
    music_profile: Mapped["NormalizedMusicProfile | None"] = relationship(back_populates="media_file", cascade="all, delete-orphan")
    review_flags: Mapped[list["MetadataReviewFlag"]] = relationship(back_populates="media_file", cascade="all, delete-orphan")
    quality_decision: Mapped["MetadataQualityDecision | None"] = relationship(back_populates="media_file", cascade="all, delete-orphan")


class RawMediaTag(Base):
    __tablename__ = "raw_media_tags"
    __table_args__ = (
        UniqueConstraint("media_file_id", "tag_source", name="uq_raw_media_tags_media_file_source"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    media_file_id: Mapped[int] = mapped_column(ForeignKey("media_files.id"), index=True)
    tag_source: Mapped[str] = mapped_column(String(80), default="mutagen")
    read_ok: Mapped[bool] = mapped_column(Boolean, default=False)
    raw_fields_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    raw_technical_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    raw_artwork_json: Mapped[list | None] = mapped_column(JSON, nullable=True)
    raw_payload_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    warnings_json: Mapped[list | None] = mapped_column(JSON, nullable=True)
    extracted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)

    media_file: Mapped[MediaFile] = relationship(back_populates="raw_tags")


class NormalizedMusicProfile(Base):
    __tablename__ = "normalized_music_profiles"
    __table_args__ = (
        UniqueConstraint("media_file_id", name="uq_normalized_music_profiles_media_file_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    media_file_id: Mapped[int] = mapped_column(ForeignKey("media_files.id"), index=True)
    artist: Mapped[str | None] = mapped_column(Text, nullable=True)
    album_artist: Mapped[str | None] = mapped_column(Text, nullable=True)
    album: Mapped[str | None] = mapped_column(Text, nullable=True)
    title: Mapped[str | None] = mapped_column(Text, nullable=True)
    track_number: Mapped[str | None] = mapped_column(String(30), nullable=True)
    disc_number: Mapped[str | None] = mapped_column(String(30), nullable=True)
    year: Mapped[str | None] = mapped_column(String(20), nullable=True)
    release_type: Mapped[str | None] = mapped_column(String(80), nullable=True)
    primary_genre: Mapped[str | None] = mapped_column(Text, nullable=True)
    genre_family: Mapped[str | None] = mapped_column(Text, nullable=True)
    subgenres_json: Mapped[list | None] = mapped_column(JSON, nullable=True)
    moods_json: Mapped[list | None] = mapped_column(JSON, nullable=True)
    energy: Mapped[str | None] = mapped_column(String(50), nullable=True)
    language: Mapped[str | None] = mapped_column(String(80), nullable=True)
    region: Mapped[str | None] = mapped_column(String(80), nullable=True)
    composer: Mapped[str | None] = mapped_column(Text, nullable=True)
    conductor: Mapped[str | None] = mapped_column(Text, nullable=True)
    orchestra: Mapped[str | None] = mapped_column(Text, nullable=True)
    ensemble: Mapped[str | None] = mapped_column(Text, nullable=True)
    soloist: Mapped[str | None] = mapped_column(Text, nullable=True)
    work: Mapped[str | None] = mapped_column(Text, nullable=True)
    movement: Mapped[str | None] = mapped_column(Text, nullable=True)
    metadata_status: Mapped[str] = mapped_column(String(50), default="snapshot")
    metadata_confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    metadata_source: Mapped[str | None] = mapped_column(String(100), nullable=True)
    approved: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)

    media_file: Mapped[MediaFile] = relationship(back_populates="music_profile")


class MetadataReviewFlag(Base):
    __tablename__ = "metadata_review_flags"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    media_file_id: Mapped[int | None] = mapped_column(ForeignKey("media_files.id"), nullable=True, index=True)
    ingest_batch_id: Mapped[int | None] = mapped_column(ForeignKey("ingest_batches.id"), nullable=True, index=True)
    flag_type: Mapped[str] = mapped_column(String(100), index=True)
    severity: Mapped[str] = mapped_column(String(30), default="warning")
    field_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    raw_value: Mapped[str | None] = mapped_column(Text, nullable=True)
    normalized_value: Mapped[str | None] = mapped_column(Text, nullable=True)
    message: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(30), default="open", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    media_file: Mapped[MediaFile | None] = relationship(back_populates="review_flags")


class GenreTaxonomy(Base):
    __tablename__ = "genre_taxonomy"
    __table_args__ = (
        UniqueConstraint("canonical_genre", name="uq_genre_taxonomy_canonical_genre"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    canonical_genre: Mapped[str] = mapped_column(String(160), index=True)
    display_genre: Mapped[str] = mapped_column(String(160))
    genre_family: Mapped[str] = mapped_column(String(160), index=True)
    display_family: Mapped[str] = mapped_column(String(160))
    aliases_json: Mapped[list | None] = mapped_column(JSON, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)


class ArtistProfileOverride(Base):
    __tablename__ = "artist_profile_overrides"
    __table_args__ = (
        UniqueConstraint("artist_key", name="uq_artist_profile_overrides_artist_key"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    artist_key: Mapped[str] = mapped_column(String(220), index=True)
    artist_display: Mapped[str] = mapped_column(Text)
    primary_genre: Mapped[str | None] = mapped_column(Text, nullable=True)
    genre_family: Mapped[str | None] = mapped_column(Text, nullable=True)
    subgenres_json: Mapped[list | None] = mapped_column(JSON, nullable=True)
    moods_json: Mapped[list | None] = mapped_column(JSON, nullable=True)
    energy: Mapped[str | None] = mapped_column(String(50), nullable=True)
    related_artists_json: Mapped[list | None] = mapped_column(JSON, nullable=True)
    source: Mapped[str | None] = mapped_column(String(100), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)


class MetadataQualityDecision(Base):
    __tablename__ = "metadata_quality_decisions"
    __table_args__ = (
        UniqueConstraint("media_file_id", name="uq_metadata_quality_decisions_media_file_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    media_file_id: Mapped[int] = mapped_column(ForeignKey("media_files.id"), index=True)
    normalized_music_profile_id: Mapped[int | None] = mapped_column(ForeignKey("normalized_music_profiles.id"), nullable=True, index=True)
    batch_id: Mapped[int | None] = mapped_column(ForeignKey("ingest_batches.id"), nullable=True, index=True)
    decision: Mapped[str] = mapped_column(String(50), index=True)
    severity: Mapped[str] = mapped_column(String(50), default="info")
    score: Mapped[float | None] = mapped_column(Float, nullable=True)
    reasons_json: Mapped[list | None] = mapped_column(JSON, nullable=True)
    blocking_flags_json: Mapped[list | None] = mapped_column(JSON, nullable=True)
    warning_flags_json: Mapped[list | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)

    media_file: Mapped[MediaFile] = relationship(back_populates="quality_decision")


class SourceFragment(Base):
    __tablename__ = "source_fragments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    batch_id: Mapped[int] = mapped_column(ForeignKey("ingest_batches.id"), index=True)
    source_root: Mapped[str] = mapped_column(Text)
    relative_fragment_path: Mapped[str] = mapped_column(Text)
    fragment_group_key: Mapped[str | None] = mapped_column(Text, nullable=True, index=True)
    fragment_label: Mapped[str | None] = mapped_column(Text, nullable=True)
    fragment_index: Mapped[int | None] = mapped_column(Integer, nullable=True)
    fragment_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    file_count: Mapped[int] = mapped_column(Integer, default=0)
    media_class_counts_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)


class MediaIdentityCandidate(Base):
    __tablename__ = "media_identity_candidates"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    batch_id: Mapped[int] = mapped_column(ForeignKey("ingest_batches.id"), index=True)
    candidate_key: Mapped[str] = mapped_column(Text, index=True)
    candidate_media_type: Mapped[str] = mapped_column(String(50), index=True)
    candidate_title: Mapped[str | None] = mapped_column(Text, nullable=True)
    candidate_primary_creator: Mapped[str | None] = mapped_column(Text, nullable=True)
    candidate_secondary_creator: Mapped[str | None] = mapped_column(Text, nullable=True)
    candidate_year: Mapped[str | None] = mapped_column(String(20), nullable=True)
    candidate_series: Mapped[str | None] = mapped_column(Text, nullable=True)
    candidate_series_index: Mapped[str | None] = mapped_column(String(50), nullable=True)
    candidate_release_type: Mapped[str | None] = mapped_column(String(80), nullable=True)
    candidate_confidence: Mapped[float] = mapped_column(Float, default=0.0)
    identity_evidence_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)


class CandidateMember(Base):
    __tablename__ = "candidate_members"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    candidate_id: Mapped[int] = mapped_column(ForeignKey("media_identity_candidates.id"), index=True)
    media_file_id: Mapped[int | None] = mapped_column(ForeignKey("media_files.id"), nullable=True, index=True)
    batch_file_id: Mapped[int | None] = mapped_column(ForeignKey("ingest_files.id"), nullable=True, index=True)
    relative_path: Mapped[str] = mapped_column(Text)
    media_class: Mapped[str] = mapped_column(String(50), index=True)
    role_in_candidate: Mapped[str] = mapped_column(String(80), default="primary")
    sort_key: Mapped[str | None] = mapped_column(Text, nullable=True)
    evidence_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)


class FragmentReconstructionDecision(Base):
    __tablename__ = "fragment_reconstruction_decisions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    batch_id: Mapped[int] = mapped_column(ForeignKey("ingest_batches.id"), index=True)
    candidate_id: Mapped[int | None] = mapped_column(ForeignKey("media_identity_candidates.id"), nullable=True, index=True)
    fragment_group_key: Mapped[str | None] = mapped_column(Text, nullable=True, index=True)
    decision: Mapped[str] = mapped_column(String(50), index=True)
    severity: Mapped[str] = mapped_column(String(30), default="info")
    score: Mapped[float | None] = mapped_column(Float, nullable=True)
    reasons_json: Mapped[list | None] = mapped_column(JSON, nullable=True)
    conflict_flags_json: Mapped[list | None] = mapped_column(JSON, nullable=True)
    recommended_action: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)


class MixedMediaFlag(Base):
    __tablename__ = "mixed_media_flags"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    batch_id: Mapped[int] = mapped_column(ForeignKey("ingest_batches.id"), index=True)
    source_fragment_id: Mapped[int | None] = mapped_column(ForeignKey("source_fragments.id"), nullable=True, index=True)
    candidate_id: Mapped[int | None] = mapped_column(ForeignKey("media_identity_candidates.id"), nullable=True, index=True)
    flag_type: Mapped[str] = mapped_column(String(100), index=True)
    severity: Mapped[str] = mapped_column(String(30), default="warning")
    message: Mapped[str] = mapped_column(Text)
    examples_json: Mapped[list | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)