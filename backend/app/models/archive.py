from datetime import datetime
from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Text, JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.db.session import Base


class IngestBatch(Base):
    __tablename__ = "ingest_batches"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    source_kind: Mapped[str] = mapped_column(String(50), default="manual-drop")
    source_path: Mapped[str] = mapped_column(Text)
    detected_type: Mapped[str] = mapped_column(String(50), default="music_album")
    status: Mapped[str] = mapped_column(String(50), default="pending_review")
    confidence: Mapped[float] = mapped_column(Float, default=0.0)
    suggested_destination: Mapped[str | None] = mapped_column(Text, nullable=True)
    suggested_metadata: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    metadata_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    metadata_confirmed: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    approved_by: Mapped[str | None] = mapped_column(String(100), nullable=True)

    files: Mapped[list["IngestFile"]] = relationship(back_populates="batch", cascade="all, delete-orphan")


class IngestFile(Base):
    __tablename__ = "ingest_files"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    batch_id: Mapped[int] = mapped_column(ForeignKey("ingest_batches.id"))
    file_path: Mapped[str] = mapped_column(Text)
    file_name: Mapped[str] = mapped_column(Text)
    extension: Mapped[str] = mapped_column(String(20))
    size_bytes: Mapped[int] = mapped_column(Integer)
    checksum: Mapped[str | None] = mapped_column(String(128), nullable=True)
    detected_role: Mapped[str] = mapped_column(String(50), default="audio_track")
    metadata_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    batch: Mapped[IngestBatch] = relationship(back_populates="files")


class MoveAction(Base):
    __tablename__ = "move_actions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    batch_id: Mapped[int] = mapped_column(ForeignKey("ingest_batches.id"))
    source_path: Mapped[str] = mapped_column(Text)
    destination_path: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(50), default="pending")
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class ArchiveItem(Base):
    __tablename__ = "archive_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    media_type: Mapped[str] = mapped_column(String(50), default="music")
    title: Mapped[str] = mapped_column(Text)
    creator: Mapped[str | None] = mapped_column(Text, nullable=True)
    year: Mapped[str | None] = mapped_column(String(20), nullable=True)
    primary_genre: Mapped[str | None] = mapped_column(String(100), nullable=True)
    source_kind: Mapped[str] = mapped_column(String(50), default="manual-drop")
    final_path: Mapped[str] = mapped_column(Text)
    metadata_status: Mapped[str] = mapped_column(String(50), default="basic")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
