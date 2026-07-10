from datetime import datetime
from typing import Any, Generic, Literal, TypeVar
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


class MetadataQualityDecisionOut(BaseModel):
    media_file_id: int
    ingest_file_id: int | None = None
    file_name: str
    relative_path: str | None = None
    decision: str
    severity: str
    score: float | None = None
    reasons: list[str] = Field(default_factory=list)
    blocking_flags: list[str] = Field(default_factory=list)
    warning_flags: list[str] = Field(default_factory=list)
    profile: dict | None = None
    review_flags: list[dict] = Field(default_factory=list)


class BatchMetadataQualityOut(BaseModel):
    batch_id: int
    total_files: int = 0
    approved_ready_count: int = 0
    review_recommended_count: int = 0
    review_required_count: int = 0
    blocked_count: int = 0
    worst_decision: str = "approved_ready"
    flag_counts: dict[str, int] = Field(default_factory=dict)
    items: list[MetadataQualityDecisionOut] = Field(default_factory=list)



class UniversalIngestionReviewActionOut(BaseModel):
    id: int
    batch_id: int
    candidate_id: int | None = None
    source_fragment_id: int | None = None
    media_file_id: int | None = None
    action_type: str
    target_media_class: str | None = None
    target_candidate_id: int | None = None
    override_title: str | None = None
    override_primary_creator: str | None = None
    override_year: str | None = None
    override_series: str | None = None
    override_series_index: str | None = None
    override_release_type: str | None = None
    override_genre_family: str | None = None
    override_destination_root: str | None = None
    decision_status: str = "active"
    reason: str | None = None
    note: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None
    applied_at: datetime | None = None
    created_by: str | None = "local_user"

    @field_serializer("created_at", "updated_at", "applied_at")
    def serialize_action_time(self, value: datetime | None) -> str | None:
        return serialize_utc(value) if value else None


class UniversalIngestionReviewActionUpdate(BaseModel):
    action_type: str
    candidate_id: int | None = None
    source_fragment_id: int | None = None
    media_file_id: int | None = None
    target_media_class: str | None = None
    target_candidate_id: int | None = None
    override_title: str | None = None
    override_primary_creator: str | None = None
    override_year: str | None = None
    override_series: str | None = None
    override_series_index: str | None = None
    override_release_type: str | None = None
    override_genre_family: str | None = None
    override_destination_root: str | None = None
    reason: str | None = None
    note: str | None = None
    created_by: str | None = "local_user"

class UniversalIngestionSummaryOut(BaseModel):
    source_fragment_count: int = 0
    candidate_count: int = 0
    member_count: int = 0
    mixed_media_flag_count: int = 0
    decision_counts: dict[str, int] = Field(default_factory=dict)
    media_class_counts: dict[str, int] = Field(default_factory=dict)
    worst_decision: str = "safe_group"
    action_summary: dict = Field(default_factory=dict)
    source_origin_count: int = 0
    resolved_source_origin_count: int = 0
    source_origins_resolved: bool = False


class SourceFragmentOut(BaseModel):
    id: int
    batch_id: int
    fragment_group_key: str | None = None
    source_root: str
    source_path: str
    fragment_label: str | None = None
    file_count: int = 0
    media_class_counts: dict[str, int] = Field(default_factory=dict)
    created_at: datetime | None = None
    updated_at: datetime | None = None
    active_actions: list[UniversalIngestionReviewActionOut] = Field(default_factory=list)

    @field_serializer("created_at", "updated_at")
    def serialize_fragment_time(self, value: datetime | None) -> str | None:
        return serialize_utc(value) if value else None


class CandidateMemberOut(BaseModel):
    id: int
    candidate_id: int
    media_file_id: int | None = None
    ingest_file_id: int | None = None
    relative_path: str
    filename: str
    extension: str | None = None
    media_class: str
    size_bytes: int | None = None
    duration_seconds: str | None = None
    track_number: str | None = None
    disc_number: str | None = None
    season_number: str | None = None
    episode_number: str | None = None
    title: str | None = None
    artist_or_author: str | None = None
    album_or_series: str | None = None
    member_role: str
    confidence: float | None = None
    reason: str | None = None
    active_actions: list[UniversalIngestionReviewActionOut] = Field(default_factory=list)


class MediaIdentityCandidateOut(BaseModel):
    id: int
    batch_id: int
    candidate_key: str
    candidate_media_type: str
    candidate_title: str | None = None
    candidate_primary_creator: str | None = None
    candidate_secondary_creator: str | None = None
    candidate_year: str | None = None
    candidate_series: str | None = None
    candidate_series_index: str | None = None
    candidate_confidence: float = 0.0
    candidate_confidence_label: str = "Unknown"
    member_count: int = 0
    source_fragment_count: int = 0
    recommended_action: str | None = None
    summary_reason: str | None = None
    members: list[CandidateMemberOut] = Field(default_factory=list)
    active_actions: list[UniversalIngestionReviewActionOut] = Field(default_factory=list)


class FragmentReconstructionDecisionOut(BaseModel):
    id: int
    batch_id: int
    candidate_id: int | None = None
    source_fragment_id: int | None = None
    decision: str
    severity: str
    reason: str | None = None
    recommended_action: str | None = None
    conflict_flags: list[str] = Field(default_factory=list)
    created_at: datetime | None = None

    @field_serializer("created_at")
    def serialize_decision_time(self, value: datetime | None) -> str | None:
        return serialize_utc(value) if value else None


class MixedMediaFlagOut(BaseModel):
    id: int
    batch_id: int
    source_fragment_id: int | None = None
    candidate_id: int | None = None
    flag_type: str
    severity: str
    message: str
    media_classes_involved: list[str] = Field(default_factory=list)
    example_paths: list[str] = Field(default_factory=list)
    recommended_action: str | None = None
    created_at: datetime | None = None

    @field_serializer("created_at")
    def serialize_flag_time(self, value: datetime | None) -> str | None:
        return serialize_utc(value) if value else None


class BatchUniversalIngestionOut(BaseModel):
    batch_id: int
    phase: str
    analysis_status: str = "not_analyzed"
    summary: UniversalIngestionSummaryOut
    source_fragments: list[SourceFragmentOut] = Field(default_factory=list)
    candidates: list[MediaIdentityCandidateOut] = Field(default_factory=list)
    reconstruction_decisions: list[FragmentReconstructionDecisionOut] = Field(default_factory=list)
    mixed_media_flags: list[MixedMediaFlagOut] = Field(default_factory=list)
    review_actions: list[UniversalIngestionReviewActionOut] = Field(default_factory=list)


class RoutingCandidateSummaryOut(BaseModel):
    candidate_id: int
    candidate_title: str | None = None
    candidate_media_type: str | None = None
    candidate_key: str | None = None
    chunk_identity_risk: bool = False


class RoutingDecisionSummaryOut(BaseModel):
    candidate_count: int = 0
    media_types: list[str] = Field(default_factory=list)
    media_class_counts: dict[str, int] = Field(default_factory=dict)
    mixed_media_flag_count: int = 0
    source_fragment_group_count: int = 0
    source_fragment_count: int = 0
    embedded_album_value_count: int = 0
    source_identity_risk: bool = False
    reconstruction_decision_count: int = 0
    blocked_conflict_count: int = 0
    review_required_count: int = 0
    chunk_identity_candidate_count: int = 0


class RoutingDecisionOut(BaseModel):
    batch_id: int
    decision: str
    allowed_editors: list[str] = Field(default_factory=list)
    blocked_editors: list[str] = Field(default_factory=list)
    reasons: list[str] = Field(default_factory=list)
    universal_ingestion_available: bool = False
    requires_snapshot: bool = False
    summary: RoutingDecisionSummaryOut
    candidate_route_summaries: list[RoutingCandidateSummaryOut] = Field(default_factory=list)


class CandidateMovePreviewSummaryOut(BaseModel):
    candidate_count: int = 0
    source_fragment_count: int = 0
    member_count: int = 0
    media_class_counts: dict[str, int] = Field(default_factory=dict)
    decision_counts: dict[str, int] = Field(default_factory=dict)
    active_action_count: int = 0
    mixed_media: bool = False
    music_only_fragmented: bool = False
    blocked_conflict_count: int = 0
    review_required_count: int = 0


class CandidateMovePreviewGroupOut(BaseModel):
    candidate_id: int
    candidate_media_type: str | None = None
    candidate_title: str | None = None
    candidate_primary_creator: str | None = None
    candidate_year: str | int | None = None
    confidence: str | None = None
    member_count: int = 0
    source_fragment_count: int = 0
    active_action: dict[str, Any] | None = None
    decision: str | None = None
    recommended_action: str | None = None
    target_library: str
    destination_preview: str
    source_fragment_names: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    blocked: bool = False
    requires_review: bool = False


class CandidateMovePreviewOut(BaseModel):
    batch_id: int
    status: str
    summary: CandidateMovePreviewSummaryOut
    preview_groups: list[CandidateMovePreviewGroupOut] = Field(default_factory=list)
    global_warnings: list[str] = Field(default_factory=list)
    next_actions: list[str] = Field(default_factory=list)

class SplitCandidateRequest(BaseModel):
    candidate_id: int


class SplitCandidateResponse(BaseModel):
    parent_batch_id: int
    child_batch_id: int
    moved_file_count: int
    remaining_parent_file_count: int
    parent_status: str
    child_detected_type: str
    child_status: str
    suggested_destination: str | None = None
    artist: str | None = None
    album: str | None = None


class MaterializeApprovedCandidatesResponse(BaseModel):
    parent_batch_id: int
    created_child_batch_ids: list[int] = Field(default_factory=list)
    created_count: int
    skipped_count: int
    materialized_child_count: int = 0
    unresolved_candidate_count: int = 0
    blocked_candidate_count: int = 0
    excluded_candidate_count: int = 0
    review_later_candidate_count: int = 0
    parent_review_state: str
    message: str


class SplitDiscographyReleasesResponse(BaseModel):
    parent_batch_id: int
    created_child_batch_ids: list[int] = Field(default_factory=list)
    existing_child_batch_ids: list[int] = Field(default_factory=list)
    created_count: int = 0
    skipped_count: int = 0
    remaining_parent_file_count: int = 0
    parent_status: str
    parent_review_state: str
    message: str



class DuplicateFragmentBatchOut(BaseModel):
    batch_id: int
    title: str
    creator: str | None = None
    year: str | None = None
    item_count: int = 0
    file_count: int = 0
    file_formats: list[str] = Field(default_factory=list)
    file_ownership_status: str = "verified"
    file_ownership_warning: str | None = None
    suggested_destination: str | None = None
    source_path: str | None = None
    status: str
    detected_type: str


class DuplicateFragmentClusterOut(BaseModel):
    cluster_id: str
    review_type: str
    media_type: str
    confidence: str
    reason: str
    has_file_ownership_warnings: bool = False
    mixed_file_formats: bool = False
    file_formats: list[str] = Field(default_factory=list)
    canonical_batch_id: int | None = None
    append_plan: dict[str, Any] | None = None
    batches: list[DuplicateFragmentBatchOut] = Field(default_factory=list)


class DuplicateFragmentReviewOut(BaseModel):
    active_cluster: bool = False
    message: str | None = None
    clusters: list[DuplicateFragmentClusterOut] = Field(default_factory=list)


class DuplicateFragmentResolutionRequest(BaseModel):
    action: str
    canonical_batch_id: int | None = None
    duplicate_batch_ids: list[int] = Field(default_factory=list)
    confirm_distinct_destinations: bool = False


class DuplicateFragmentResolutionResponse(BaseModel):
    cluster_id: str
    action: str
    canonical_batch_id: int | None = None
    resolved_batch_ids: list[int] = Field(default_factory=list)
    collapsed_batch_ids: list[int] = Field(default_factory=list)
    blocked_batch_ids: list[int] = Field(default_factory=list)
    message: str
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
    embedded_artwork_count: int = 0
    embedded_artwork_files: list[str] = Field(default_factory=list)
    ignored_sidecar_count: int = 0
    subtitle_count: int = 0
    video_file_count: int = 0
    video_files: list[str] = Field(default_factory=list)
    title: str | None = None
    edition: str | None = None
    resolution: str | None = None
    source: str | None = None
    original_release_name: str | None = None
    primary_video_file: str | None = None
    artwork_files: list[str] = Field(default_factory=list)
    subtitle_files: list[str] = Field(default_factory=list)
    ignored_sidecar_files: list[str] = Field(default_factory=list)
    release_tags_removed: list[str] = Field(default_factory=list)
    show_title: str | None = None
    season_count: int = 0
    episode_count: int = 0
    special_episode_count: int = 0
    special_episodes: list[dict] = Field(default_factory=list)
    seasons: list[dict] = Field(default_factory=list)
    ignored_corrupt_video_count: int = 0
    ignored_corrupt_video_files: list[str] = Field(default_factory=list)
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
    blocking_review_items: list[dict] = Field(default_factory=list)
    non_blocking_review_items: list[dict] = Field(default_factory=list)
    review_confirmed: bool = False
    review_type: str | None = None
    review_mode: str | None = None
    movie_items: list[dict] = Field(default_factory=list)
    collection_title: str | None = None
    keep_collection_together: bool | None = None
    collection_destination_root: str | None = None
    author: str | None = None
    book_file_count: int = 0
    book_files: list[str] = Field(default_factory=list)
    primary_book_file: str | None = None
    book_items: list[dict] = Field(default_factory=list)
    collection_summary: dict = Field(default_factory=dict)
    narrator: str | None = None
    series: str | None = None
    series_index: str | None = None
    audiobook_file_count: int = 0
    audio_files: list[str] = Field(default_factory=list)
    primary_audio_file: str | None = None
    chapter_count: int = 0
    metadata_candidates: dict[str, list[dict]] = Field(default_factory=dict)
    chapter_candidates: list[dict] = Field(default_factory=list)
    artwork_candidates: list[dict] = Field(default_factory=list)
    generic_audio_tag_count: int = 0
    detected_disc_count: int = 0
    candidate_warning_count: int = 0
    audiobook_collection_type: str | None = None
    contained_books: list[dict] = Field(default_factory=list)
    accepted_unknown_author: bool = False
    accepted_unknown_year: bool = False
    accepted_unknown_narrator: bool = False
    accepted_unknown_album_artist: bool = False
    accepted_unknown_album_title: bool = False
    accepted_unknown_discography_artist: bool = False
    accepted_unknown_title: bool = False
    lookup_later: bool = False
    move_manifest: dict | None = None
    metadata_assist_version: str | None = None
    suggested_destination: str | None = None
    suggested_metadata: dict | None = None
    metadata_confirmed: bool = False
    music_review_summary: dict | None = None
    action_message: str | None = None
    candidate_group_count: int = 0
    approved_candidate_count: int = 0
    excluded_candidate_count: int = 0
    blocked_candidate_count: int = 0
    review_later_candidate_count: int = 0
    unresolved_candidate_count: int = 0
    materialized_child_count: int = 0
    child_candidate_count: int = 0
    remaining_candidate_count: int = 0
    needs_materialization: bool = False
    parent_review_state: str | None = None
    parent_container_state: str | None = None
    is_parent_review_container: bool = False
    parent_is_drained: bool = False
    display_state: str | None = None
    approval_allowed: bool = True
    move_ready: bool = False
    requires_review: bool = False
    active_parent_file_count: int = 0
    active_file_count: int = 0
    child_batch_count: int = 0
    parent_has_remaining_files: bool = False
    historical_scan_snapshot: bool = False
    possible_duplicate_group_id: str | None = None
    possible_duplicate_count: int = 0
    possible_fragment_group_id: str | None = None
    possible_fragment_count: int = 0
    duplicate_fragment_review_state: str = "none"
    requires_duplicate_review: bool = False
    media_category: str | None = None
    media_label: str | None = None
    primary_name: str | None = None
    secondary_name: str | None = None
    item_label: str | None = None
    item_count: int = 0
    edit_kind: str | None = None
    review_origin: str | None = None
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
    year: str | None = Field(default=None, pattern=r"^(19|20)\d{2}$")
    primary_genre: str | None = None
    format: str | None = None
    note: str | None = None
    accepted_unknown_album_artist: bool = False
    accepted_unknown_album_title: bool = False
    accepted_unknown_year: bool = False
    lookup_later: bool = False


class MetadataEnrichmentTrackMatch(BaseModel):
    file_id: int
    file_name: str
    score: float
    disc_number: int | None = None
    track_number: str | None = None
    title: str
    recording_id: str | None = None
    release_id: str | None = None


class MetadataEnrichmentCandidate(BaseModel):
    provider: str
    release_id: str
    release_group_id: str | None = None
    artist: str
    title: str
    year: str | None = None
    release_type: str | None = None
    genres: list[str] = []
    provider_score: float = 0.0
    match_score: float = 0.0
    match_confidence: float = 0.0
    matched_track_count: int = 0
    local_track_count: int = 0
    unmatched_track_count: int = 0
    tracks: list[dict] = []
    track_matches: list[MetadataEnrichmentTrackMatch] = []


class MetadataEnrichmentPreview(BaseModel):
    batch_id: int
    provider: str
    query: dict
    candidates: list[MetadataEnrichmentCandidate] = []
    message: str


class MetadataEnrichmentApplyRequest(BaseModel):
    release_id: str = Field(min_length=1)


class MetadataEnrichmentApplyResponse(BaseModel):
    batch_id: int
    provider: str
    release_id: str
    artist: str
    album: str
    year: str | None = None
    release_type: str | None = None
    genre: str | None = None
    match_confidence: float
    applied_track_count: int
    matched_track_count: int
    local_track_count: int
    filename_previews: list[dict] = []
    suggested_destination: str | None = None
    message: str


class MovieMetadataUpdate(BaseModel):
    title: str = Field(min_length=1)
    year: str | None = Field(default=None, pattern=r"^(19|20)\d{2}$")
    edition: str | None = None
    format: str | None = None
    accepted_unknown_title: bool = False
    accepted_unknown_year: bool = False
    lookup_later: bool = False


class TvMetadataUpdate(BaseModel):
    show_title: str = Field(min_length=1)
    season_number: int | None = Field(default=None, ge=0, le=99)
    year: str | None = Field(default=None, pattern=r"^(19|20)\d{2}$")
    season_title: str | None = None


class TvEpisodeReviewPatch(BaseModel):
    source_file: str
    relative_source: str | None = None

    include: bool = True

    # Normal episode fields
    season_number: int | None = None
    episode_number: int | None = None

    # Special handling
    is_special: bool = False
    special_label: str | None = None
    destination_group: str | None = None
    # Allowed values: None | "season" | "specials" | "oad" | "ova" | "extras"

    episode_title: str | None = None
    preserve_source_filename: bool = False


class TvEpisodeReviewUpdate(BaseModel):
    show_title: str | None = None
    year: str | None = None
    patches: list[TvEpisodeReviewPatch] = Field(default_factory=list)
    confirm_non_blocking_warnings: bool = False


class MovieCollectionItemUpdate(BaseModel):
    source_file: str = Field(min_length=1)
    include: bool = True
    title: str = ""
    year: str | None = Field(default=None, pattern=r"^(19|20)\d{2}$")
    edition: str | None = None
    format: str | None = None
    accepted_unknown_title: bool = False
    accepted_unknown_year: bool = False
    lookup_later: bool = False


class MovieCollectionReviewUpdate(BaseModel):
    collection_title: str | None = None
    movies: list[MovieCollectionItemUpdate] = Field(min_length=1)
    confirm_non_blocking_warnings: bool = False


class BookMetadataUpdate(BaseModel):
    title: str = Field(min_length=1)
    author: str = Field(min_length=1)
    year: str | None = Field(default=None, pattern=r"^(19|20)\d{2}$")
    format: str | None = None
    note: str | None = None


class BookCollectionItemUpdate(BaseModel):
    source_file: str = Field(min_length=1)
    include: bool = True
    title: str = ""
    author: str = ""
    year: str | None = Field(default=None, pattern=r"^(19|20)\d{2}$")
    format: str | None = None
    series: str | None = None
    series_index: str | None = None
    accepted_unknown_author: bool = False
    accepted_unknown_year: bool = False
    lookup_later: bool = False


class BookCollectionReviewUpdate(BaseModel):
    collection_title: str | None = None
    keep_collection_together: bool = False
    books: list[BookCollectionItemUpdate] = Field(min_length=1)
    confirm_non_blocking_warnings: bool = False


class AudiobookMetadataUpdate(BaseModel):
    author: str = Field(min_length=1)
    title: str = Field(min_length=1)
    year: str | None = Field(default=None, pattern=r"^(19|20)\d{2}$")
    narrator: str | None = None
    series: str | None = None
    series_index: str | None = None
    format: str | None = None
    note: str | None = None
    accepted_unknown_author: bool = False
    accepted_unknown_year: bool = False
    accepted_unknown_narrator: bool = False
    lookup_later: bool = False


class ReviewConfirmationUpdate(BaseModel):
    confirmed: bool
    accept_non_blocking_warnings: bool = False
    note: str | None = None


class DiscographyAlbumUpdate(BaseModel):
    source_folder: str = Field(min_length=1)
    album: str = Field(min_length=1)
    year: str | None = Field(default=None, pattern=r"^(19|20)\d{2}$")
    genre: str | None = None
    release_type: Literal[
        "album",
        "single",
        "ep",
        "compilation",
        "live",
        "other",
        "exclude",
    ] = "album"
    release_decision: Literal[
        "extract_as_child",
        "review_later",
        "exclude",
        "blocked",
        "unresolved",
    ] = "extract_as_child"
    include: bool = True
    accepted_unknown_album_artist: bool = False
    accepted_unknown_album_title: bool = False
    accepted_unknown_year: bool = False
    lookup_later: bool = False


class DiscographyMetadataUpdate(BaseModel):
    artist: str = Field(min_length=1)
    primary_genre: str | None = None
    albums: list[DiscographyAlbumUpdate] | None = None
    accepted_unknown_discography_artist: bool = False
    lookup_later: bool = False

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
    files_moved: int = 0
    failed_moves: int = 0
    manifests: list[dict] = Field(default_factory=list)
    audit_records: list[str] = Field(default_factory=list)
    notices: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class ScanMusicResponse(BaseModel):
    created: int
    skipped_duplicates: int
    batches: list[IngestBatchOut]
    music_albums_found: int = 0
    discographies_found: int = 0
    unknown_items: int = 0
    unsupported_files: int = 0
    ignored_system_files: int = 0
    ignored_sidecar_only_folders: int = 0
    artwork_files_found: int = 0
    movie_batches_found: int = 0
    tv_shows_found: int = 0
    tv_episodes_found: int = 0
    subtitle_files_found: int = 0
    book_batches_found: int = 0
    book_files_found: int = 0
    audiobook_batches_found: int = 0
    audiobook_files_found: int = 0


class DevResetResponse(BaseModel):
    status: str
    restored_tracks: int
    restored_files: int
    recovered_media_files: int = 0
    untracked_library_media_files: int = 0
    removed_reports: int
    removed_move_logs: int
    removed_library_metadata: int
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
    manifest: dict | None = None


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
