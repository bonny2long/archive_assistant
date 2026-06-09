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
    artwork_count: int = 0
    ignored_sidecar_count: int = 0
    subtitle_count: int = 0
    video_file_count: int = 0
    title: str | None = None
    edition: str | None = None
    original_release_name: str | None = None
    primary_video_file: str | None = None
    artwork_files: list[str] = Field(default_factory=list)
    subtitle_files: list[str] = Field(default_factory=list)
    ignored_sidecar_files: list[str] = Field(default_factory=list)
    release_tags_removed: list[str] = Field(default_factory=list)
    show_title: str | None = None
    season_count: int = 0
    episode_count: int = 0
    seasons: list[dict] = Field(default_factory=list)
    name: str | None = None
    reason: str | None = None
    file_count: int = 0
    folder_count: int = 0
    size_bytes: int = 0
    recommended_action: str | None = None
    release_count: int = 0
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
    media_category: str | None = None
    media_label: str | None = None
    primary_name: str | None = None
    secondary_name: str | None = None
    item_label: str | None = None
    item_count: int = 0
    edit_kind: str | None = None
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


class MovieMetadataUpdate(BaseModel):
    title: str = Field(min_length=1)
    year: str | None = Field(default=None, pattern=r"^(19|20)\d{2}$")
    edition: str | None = None
    format: str | None = None


class TvMetadataUpdate(BaseModel):
    show_title: str = Field(min_length=1)
    season_number: int | None = Field(default=None, ge=0, le=99)
    year: str | None = Field(default=None, pattern=r"^(19|20)\d{2}$")
    season_title: str | None = None


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
    music_albums_found: int = 0
    discographies_found: int = 0
    unknown_items: int = 0
    unsupported_files: int = 0
    ignored_system_files: int = 0
    artwork_files_found: int = 0
    movie_batches_found: int = 0
    tv_shows_found: int = 0
    tv_episodes_found: int = 0
    subtitle_files_found: int = 0


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
    moved_batches: int
    moved_files: int
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
