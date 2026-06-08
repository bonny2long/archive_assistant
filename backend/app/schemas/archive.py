from datetime import datetime
from typing import Generic, Literal, TypeVar
from pydantic import BaseModel, Field, field_serializer
from app.core.time import serialize_utc

T = TypeVar("T")

class IngestFileOut(BaseModel):
    id: int
    file_name: str
    extension: str
    size_bytes: int
    detected_role: str
    metadata_json: dict | None = None

    class Config:
        from_attributes = True

class BatchSummary(BaseModel):
    id: int
    detected_type: str
    status: str
    artist: str | None = None
    album: str | None = None
    year: str | None = None
    primary_genre: str | None = None
    format: str | None = None
    track_count: int = 0
    album_count: int = 0
    albums: list[dict] = Field(default_factory=list)
    disc_count: int = 0
    confidence: float
    metadata_quality: str
    metadata_warnings: list[str]
    suggested_destination: str | None = None
    suggested_metadata: dict | None = None
    metadata_confirmed: bool = False
    action_message: str | None = None
    created_at: datetime

    @field_serializer("created_at")
    def serialize_created_at(self, value: datetime) -> str:
        return serialize_utc(value)

    class Config:
        from_attributes = True

class IngestBatchOut(BaseModel):
    id: int
    source_kind: str
    source_path: str
    detected_type: str
    status: str
    confidence: float
    suggested_destination: str | None = None
    suggested_metadata: dict | None = None
    metadata_json: dict | None = None
    metadata_confirmed: bool = False
    created_at: datetime
    approved_at: datetime | None = None
    files: list[IngestFileOut] = []

    @field_serializer("created_at", "approved_at")
    def serialize_timestamps(self, value: datetime | None) -> str | None:
        return serialize_utc(value) if value else None

    class Config:
        from_attributes = True

class BatchMetadataUpdate(BaseModel):
    artist: str = Field(min_length=1)
    album: str = Field(min_length=1)
    year: str = Field(pattern=r"^(19|20)\d{2}$")
    primary_genre: str | None = None
    format: str | None = None


class DiscographyAlbumUpdate(BaseModel):
    source_folder: str = Field(min_length=1)
    album: str = Field(min_length=1)
    year: str | None = Field(default=None, pattern=r"^(19|20)\d{2}$")
    release_type: Literal[
        "album",
        "single",
        "ep",
        "compilation",
        "live",
        "other",
        "exclude",
    ] = "album"
    include: bool = True


class DiscographyMetadataUpdate(BaseModel):
    artist: str = Field(min_length=1)
    albums: list[DiscographyAlbumUpdate] | None = None

class PaginatedResponse(BaseModel, Generic[T]):
    items: list[T]
    page: int
    page_size: int
    total: int
    total_pages: int

class ApproveResponse(BaseModel):
    batch_id: int
    status: str
    message: str
    metadata_quality: str | None = None
    metadata_warnings: list[str] | None = None


class BulkApproveRequest(BaseModel):
    batch_ids: list[int] = Field(min_length=1, max_length=100)


class BulkApproveError(BaseModel):
    batch_id: int
    reason: str


class BulkApproveResponse(BaseModel):
    approved: list[int]
    skipped: list[int]
    errors: list[BulkApproveError]


class MoveResponse(BaseModel):
    moved: int
    errors: list[str]


class ScanMusicResponse(BaseModel):
    created: int
    skipped_duplicates: int
    batches: list[IngestBatchOut]


class DevResetResponse(BaseModel):
    status: str
    restored_tracks: int
    removed_reports: int
    removed_move_logs: int
    removed_empty_dirs: int
    cleared_batches: int
    message: str


class LibrarySummary(BaseModel):
    moved_albums: int
    moved_tracks: int
    failed_moves: int
    approved_waiting: int
    needs_metadata: int


class MoveActionOut(BaseModel):
    id: int
    source_path: str
    destination_path: str
    file_name: str | None = None
    status: str
    error_message: str | None = None
    created_at: datetime
    completed_at: datetime | None = None

    @field_serializer("created_at", "completed_at")
    def serialize_timestamps(self, value: datetime | None) -> str | None:
        return serialize_utc(value) if value else None

    class Config:
        from_attributes = True


class BatchMoveSummary(BaseModel):
    batch_id: int
    total: int
    completed: int
    failed: int
    moves: list[MoveActionOut]


class BatchReviewTrack(BaseModel):
    position: int
    disc: int
    track: int | None = None
    title: str
    source_filename: str
    destination_filename: str
    artist: str | None = None
    album: str | None = None
    warnings: list[str] = Field(default_factory=list)


class BatchReview(BaseModel):
    batch_id: int
    artist: str | None = None
    album: str | None = None
    year: str | None = None
    genre: str | None = None
    format: str
    status: str
    confidence: float
    track_count: int
    disc_count: int
    warnings: list[str]
    source_path: str
    destination_preview: str | None = None
    tracks: list[BatchReviewTrack]
