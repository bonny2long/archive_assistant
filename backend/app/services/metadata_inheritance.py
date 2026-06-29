from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from app.services.metadata_contract import (
    METADATA_CONTRACT_VERSION,
    field_value,
    inherit_field,
    is_field_envelope,
    metadata_field,
    resolve_approval_actor,
)


MUSIC_INHERITABLE_FIELDS = (
    "primary_genre",
    "genre",
    "subgenres",
    "moods",
    "energy",
    "era",
    "region",
    "scene",
    "language",
    "release_type",
    "secondary_types",
    "is_compilation",
    "is_mixtape",
    "is_live",
    "is_remix",
    "is_demo",
    "is_instrumental",
    "is_deluxe",
    "is_bonus_track",
    "related_artists",
)

CORE_ARCHIVE_FIELDS = (
    "artist",
    "album_artist",
    "albumartist",
    "release_title",
    "album",
    "track_title",
    "title",
    "year",
    "release_date",
    "date",
    "track_number",
    "tracknumber",
    "disc_number",
    "discnumber",
    "format",
    "codec",
    "duration_seconds",
    "bitrate",
    "sample_rate",
    "file_path",
    "final_path",
)


def _profile_fields(profile: Mapping[str, Any] | None) -> dict[str, Any]:
    if not isinstance(profile, Mapping):
        return {}
    fields = profile.get("fields")
    if isinstance(fields, Mapping):
        return dict(fields)
    return dict(profile)


def _approved_envelope(value: Any, *, reason: str) -> dict[str, Any]:
    return metadata_field(
        value,
        source="manual",
        confidence=1.0,
        reason=reason,
        approval_state="approved",
        approved=True,
        approved_by=resolve_approval_actor(),
    )


def _ensure_envelope(
    value: Any,
    *,
    source: str,
    confidence: float,
    reason: str,
    approved: bool = False,
) -> dict[str, Any]:
    if is_field_envelope(value):
        return dict(value)
    return metadata_field(
        value,
        source=source,
        confidence=confidence,
        reason=reason,
        approval_state="approved" if approved else "pending",
        approved=approved,
        approved_by=resolve_approval_actor() if approved else None,
    )


def _has_value(value: Any) -> bool:
    raw = field_value(value)
    if raw is None:
        return False
    if isinstance(raw, str):
        return raw.strip().casefold() not in {"", "unknown", "unknown year"}
    if isinstance(raw, (list, tuple, set, dict)):
        return bool(raw)
    return True


def _is_approved(value: Any) -> bool:
    return is_field_envelope(value) and bool(value.get("approved"))


def resolve_inherited_field(
    field_name: str,
    *,
    current: Any = None,
    release: Any = None,
    artist: Any = None,
    fallback: Any = None,
) -> tuple[Any, dict[str, Any]]:
    explanation = {
        "field": field_name,
        "source": "missing",
        "reason": "No approved or usable value was available.",
        "inherited": False,
    }
    if _is_approved(current) or (_has_value(current) and not is_field_envelope(current)):
        explanation.update({
            "source": "manual" if _is_approved(current) else "current_value",
            "reason": "Existing field value is stronger than inheritance.",
            "inherited": False,
        })
        return current, explanation
    if _has_value(release):
        if _is_approved(release):
            inherited = inherit_field(
                release,
                source="release_profile",
                confidence=0.97,
                reason=f"Inherited {field_name} from approved release profile.",
            )
            inherited["approved"] = True
            inherited["approved_by"] = release.get("approved_by")
            inherited["approved_at"] = release.get("approved_at")
            explanation.update({
                "source": "release_profile",
                "reason": inherited["reason"],
                "inherited": True,
            })
            return inherited, explanation
        if is_field_envelope(release) and release.get("source") == "embedded_tag":
            explanation.update({
                "source": "embedded_tag",
                "reason": "Embedded evidence is preserved but not promoted without approval.",
                "inherited": False,
            })
            return release, explanation
    if _has_value(artist):
        if _is_approved(artist):
            inherited = inherit_field(
                artist,
                source="artist_profile",
                confidence=0.95,
                reason=f"Inherited {field_name} from approved artist profile.",
            )
            inherited["approved"] = True
            inherited["approved_by"] = artist.get("approved_by")
            inherited["approved_at"] = artist.get("approved_at")
            explanation.update({
                "source": "artist_profile",
                "reason": inherited["reason"],
                "inherited": True,
            })
            return inherited, explanation
    if _has_value(fallback):
        explanation.update({
            "source": "fallback",
            "reason": "Used existing fallback evidence because no approved profile value exists.",
            "inherited": False,
        })
        return fallback, explanation
    return None, explanation


def resolve_artist_profile(metadata: Mapping[str, Any]) -> dict[str, Any]:
    existing = _profile_fields(metadata.get("artist_profile"))
    fields: dict[str, Any] = dict(existing)
    if "artist" not in fields and metadata.get("artist"):
        fields["artist"] = _approved_envelope(
            metadata.get("artist"),
            reason="Approved discography artist profile value.",
        )
    for field_name in MUSIC_INHERITABLE_FIELDS:
        if field_name in fields:
            continue
        value = metadata.get(field_name)
        if _has_value(value):
            fields[field_name] = _approved_envelope(
                value,
                reason=f"Approved discography artist profile {field_name}.",
            )
    return fields


def resolve_release_profile(
    release_metadata: Mapping[str, Any],
    artist_profile: Mapping[str, Any] | None = None,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    existing = _profile_fields(release_metadata.get("release_profile"))
    fields: dict[str, Any] = dict(existing)
    explanations: list[dict[str, Any]] = []
    if "release_title" not in fields and release_metadata.get("album"):
        fields["release_title"] = _ensure_envelope(
            release_metadata.get("album"),
            source="folder_inference",
            confidence=0.9,
            reason="Release title inferred from folder/review metadata.",
        )
    if "year" not in fields and release_metadata.get("year"):
        fields["year"] = _ensure_envelope(
            release_metadata.get("year"),
            source="folder_inference",
            confidence=0.85,
            reason="Release year inferred from folder/review metadata.",
        )
    if "release_type" not in fields and release_metadata.get("release_type"):
        fields["release_type"] = _ensure_envelope(
            release_metadata.get("release_type"),
            source="folder_inference",
            confidence=0.8,
            reason="Release type inferred from release grouping.",
        )
    artist_fields = _profile_fields(artist_profile)
    for field_name in MUSIC_INHERITABLE_FIELDS:
        current = fields.get(field_name)
        direct_value = release_metadata.get(field_name)
        if not _has_value(current) and _has_value(direct_value):
            current = _ensure_envelope(
                direct_value,
                source="manual" if release_metadata.get(f"{field_name}_source") == "manual correction" else "folder_inference",
                confidence=1.0 if release_metadata.get(f"{field_name}_source") == "manual correction" else 0.8,
                reason=f"Release-level {field_name} from review metadata.",
                approved=release_metadata.get(f"{field_name}_source") == "manual correction",
            )
        resolved, explanation = resolve_inherited_field(
            field_name,
            current=current,
            artist=artist_fields.get(field_name),
        )
        if resolved is not None:
            fields[field_name] = resolved
        explanations.append(explanation)
    return fields, explanations


def resolve_track_profile(
    track_metadata: Mapping[str, Any],
    release_profile: Mapping[str, Any] | None = None,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    existing = _profile_fields(track_metadata.get("track_profile"))
    fields: dict[str, Any] = dict(existing)
    explanations: list[dict[str, Any]] = []
    if "track_title" not in fields and track_metadata.get("title"):
        fields["track_title"] = _ensure_envelope(
            track_metadata.get("title"),
            source="embedded_tag" if (track_metadata.get("embedded_metadata") or {}).get("read_ok") else "filename_inference",
            confidence=0.88,
            reason="Track title preserved from track metadata.",
        )
    release_fields = _profile_fields(release_profile)
    for field_name in MUSIC_INHERITABLE_FIELDS:
        current = fields.get(field_name)
        if not _has_value(current) and _has_value(track_metadata.get(field_name)):
            current = _ensure_envelope(
                track_metadata.get(field_name),
                source="embedded_tag",
                confidence=0.78,
                reason=f"Track-level {field_name} preserved as evidence.",
            )
        resolved, explanation = resolve_inherited_field(
            field_name,
            current=current,
            release=release_fields.get(field_name),
        )
        if resolved is not None:
            fields[field_name] = resolved
        explanations.append(explanation)
    return fields, explanations


def explain_inheritance_chain(explanations: list[dict[str, Any]]) -> dict[str, Any]:
    inherited = [item for item in explanations if item.get("inherited")]
    missing = [item for item in explanations if item.get("source") == "missing"]
    conflicts = [item for item in explanations if item.get("source") == "embedded_tag"]
    return {
        "inherited_field_count": len(inherited),
        "missing_field_count": len(missing),
        "embedded_evidence_field_count": len(conflicts),
        "explanations": explanations,
    }


def apply_music_inheritance(metadata: dict[str, Any]) -> dict[str, Any]:
    artist_profile = resolve_artist_profile(metadata)
    release_profile, release_explanations = resolve_release_profile(
        metadata,
        artist_profile,
    )
    metadata["artist_profile"] = artist_profile
    metadata["release_profile"] = release_profile
    metadata["inheritance_summary"] = explain_inheritance_chain(
        release_explanations,
    )
    return metadata


def apply_discography_inheritance(metadata: dict[str, Any]) -> dict[str, Any]:
    artist_profile = resolve_artist_profile(metadata)
    release_explanations: list[dict[str, Any]] = []
    albums = []
    for album in metadata.get("albums") or []:
        if not isinstance(album, dict):
            albums.append(album)
            continue
        album_copy = dict(album)
        release_profile, explanations = resolve_release_profile(
            album_copy,
            artist_profile,
        )
        album_copy["release_profile"] = release_profile
        album_copy["inheritance_summary"] = explain_inheritance_chain(
            explanations,
        )
        release_explanations.extend(explanations)
        albums.append(album_copy)
    metadata["artist_profile"] = artist_profile
    metadata["albums"] = albums
    metadata["inheritance_summary"] = explain_inheritance_chain(
        release_explanations,
    )
    return metadata


def apply_track_inheritance(
    track_metadata: dict[str, Any],
    release_profile: Mapping[str, Any] | None,
) -> dict[str, Any]:
    track_profile, explanations = resolve_track_profile(
        track_metadata,
        release_profile,
    )
    track_metadata["track_profile"] = track_profile
    track_metadata["inheritance_summary"] = explain_inheritance_chain(
        explanations,
    )
    return track_metadata


MUSIC_ALBUM_PROFILE_FIELD_MAP = {
    "artist": "artist",
    "albumartist": "album_artist",
    "album_artist": "album_artist",
    "album": "release_title",
    "year": "year",
    "date": "release_date",
    "genre": "genre",
    "primary_genre": "primary_genre",
    "format": "format",
}


def _contract_fields(metadata: Mapping[str, Any]) -> dict[str, Any]:
    contract = metadata.get("metadata_contract")
    if not isinstance(contract, Mapping):
        return {}
    fields = contract.get("fields")
    return dict(fields) if isinstance(fields, Mapping) else {}


def _approved_contract_value(
    metadata: Mapping[str, Any],
    *field_names: str,
) -> Any:
    fields = _contract_fields(metadata)
    for field_name in field_names:
        value = fields.get(field_name)
        if _is_approved(value) and _has_value(value):
            return value
    return None


def _approved_or_top_level(
    metadata: Mapping[str, Any],
    field_name: str,
    *aliases: str,
) -> dict[str, Any] | None:
    approved = _approved_contract_value(metadata, field_name, *aliases)
    if approved is not None:
        return dict(approved)
    for name in (field_name, *aliases):
        if _has_value(metadata.get(name)):
            return _approved_envelope(
                metadata.get(name),
                reason=f"Rehydrated approved {field_name} from saved review metadata.",
            )
    return None


def validate_music_profile_consistency(metadata: Mapping[str, Any]) -> list[str]:
    warnings: list[str] = []
    artist_profile = _profile_fields(metadata.get("artist_profile"))
    release_profile = _profile_fields(metadata.get("release_profile"))
    comparisons = (
        ("artist", metadata.get("artist"), artist_profile.get("artist")),
        ("album", metadata.get("album"), release_profile.get("release_title")),
        ("year", metadata.get("year") or metadata.get("date"), release_profile.get("year")),
        ("genre", metadata.get("genre"), release_profile.get("genre")),
    )
    for field_name, top_value, profile_value in comparisons:
        approved = _approved_contract_value(metadata, field_name)
        if approved is None and field_name == "album":
            approved = _approved_contract_value(metadata, "album", "release_title")
        if approved is None:
            continue
        if str(field_value(profile_value) or "") != str(field_value(approved) or top_value or ""):
            warnings.append("profile_inheritance_stale")
            break
    return warnings


def rehydrate_music_review_metadata_after_manual_save(
    metadata: dict[str, Any],
    track_rows: list[Any] | None = None,
) -> dict[str, Any]:
    """Rebuild music album profiles and safe track metadata after manual save."""
    metadata = dict(metadata)
    warnings = [
        warning
        for warning in metadata.get("metadata_warnings", [])
        if warning != "profile_inheritance_stale"
    ]

    artist = _approved_or_top_level(metadata, "artist", "albumartist", "album_artist")
    album_artist = _approved_or_top_level(metadata, "albumartist", "album_artist", "artist")
    release_title = _approved_or_top_level(metadata, "album", "release_title")
    year = _approved_or_top_level(metadata, "year", "date", "release_date")
    genre = _approved_or_top_level(metadata, "genre", "primary_genre")
    primary_genre = _approved_or_top_level(metadata, "primary_genre", "genre")
    fmt = _approved_or_top_level(metadata, "format")

    artist_profile: dict[str, Any] = {}
    if artist is not None:
        artist_profile["artist"] = artist
    if primary_genre is not None:
        artist_profile["primary_genre"] = primary_genre
    elif genre is not None:
        artist_profile["primary_genre"] = genre
    for field_name in (
        "subgenres", "moods", "energy", "era", "region", "scene",
        "language", "related_artists",
    ):
        value = _approved_or_top_level(metadata, field_name)
        if value is not None:
            artist_profile[field_name] = value

    release_profile: dict[str, Any] = {}
    if release_title is not None:
        release_profile["release_title"] = release_title
    if year is not None:
        release_profile["year"] = year
        release_profile["release_date"] = year
    if genre is not None:
        release_profile["genre"] = genre
    if primary_genre is not None:
        release_profile["primary_genre"] = primary_genre
    elif genre is not None:
        release_profile["primary_genre"] = inherit_field(
            genre,
            source="artist_profile",
            confidence=0.95,
            reason="Primary genre rehydrated from approved manual genre.",
        )
        release_profile["primary_genre"]["approved"] = bool(genre.get("approved"))
        release_profile["primary_genre"]["approved_by"] = genre.get("approved_by")
        release_profile["primary_genre"]["approved_at"] = genre.get("approved_at")
    if fmt is not None:
        release_profile["format"] = fmt
    for field_name in MUSIC_INHERITABLE_FIELDS:
        if field_name in release_profile:
            continue
        value = _approved_or_top_level(metadata, field_name)
        if value is not None:
            release_profile[field_name] = value

    metadata["artist_profile"] = artist_profile
    metadata["release_profile"] = release_profile

    safe_values = {
        "albumartist": field_value(album_artist) if album_artist is not None else field_value(artist),
        "artist": field_value(artist),
        "album": field_value(release_title),
        "date": field_value(year),
        "year": field_value(year),
        "genre": field_value(genre),
        "format": field_value(fmt),
    }
    safe_values = {
        key: value for key, value in safe_values.items()
        if value is not None and str(value).strip() != ""
    }

    track_profiles = []
    track_explanations: list[dict[str, Any]] = []
    for row in track_rows or []:
        track_metadata = dict(getattr(row, "metadata_json", row) or {})
        track_contract_fields = _contract_fields(track_metadata)
        for key, value in safe_values.items():
            approved_track_value = track_contract_fields.get(key)
            if _is_approved(approved_track_value):
                continue
            track_metadata[key] = value
        apply_track_inheritance(track_metadata, release_profile)
        track_profiles.append({
            "file_name": getattr(row, "file_name", track_metadata.get("source_filename")),
            "track_profile": track_metadata.get("track_profile"),
            "inheritance_summary": track_metadata.get("inheritance_summary"),
        })
        track_explanations.extend(
            track_metadata.get("inheritance_summary", {}).get("explanations", [])
        )
        if hasattr(row, "metadata_json"):
            row.metadata_json = track_metadata

    metadata["track_profiles"] = track_profiles
    release_explanations = []
    for field_name, value in release_profile.items():
        release_explanations.append({
            "field": field_name,
            "source": value.get("source") if is_field_envelope(value) else "manual",
            "reason": value.get("reason") if is_field_envelope(value) else "Rehydrated from manual save.",
            "inherited": value.get("source") in {"artist_profile", "release_profile"} if is_field_envelope(value) else False,
        })
    metadata["inheritance_summary"] = explain_inheritance_chain(
        [*release_explanations, *track_explanations]
    )

    stale_warnings = validate_music_profile_consistency(metadata)
    metadata["metadata_warnings"] = list(dict.fromkeys([*warnings, *stale_warnings]))
    return metadata


OPTIONAL_RADIO_FIELDS = (
    "subgenres", "moods", "energy", "era", "region", "scene", "related_artists",
)
SETUP_WARNINGS = {"embedded_metadata_reader_unavailable", "mutagen_unavailable"}
NEEDS_REVIEW_WARNINGS = {
    "year_missing", "year_invalid", "genre_missing", "raw_folder_name_detected",
    "profile_inheritance_stale", "track_album_mismatch_detected",
    "track_artist_mismatch_detected",
}


def build_compact_music_review_summary(metadata: Mapping[str, Any]) -> dict[str, Any]:
    contract_fields = _contract_fields(metadata)
    artist_profile = _profile_fields(metadata.get("artist_profile"))
    release_profile = _profile_fields(metadata.get("release_profile"))
    track_profiles = list(metadata.get("track_profiles") or [])
    warnings = list(metadata.get("metadata_warnings") or [])
    extraction_warnings = list(metadata.get("extraction_warnings") or [])
    setup_warnings = sorted({warning for warning in [*warnings, *extraction_warnings] if warning in SETUP_WARNINGS})
    blocking_items = list(metadata.get("blocking_review_items") or [])
    non_blocking_items = list(metadata.get("non_blocking_review_items") or [])
    approved_core = [
        field for field in ("artist", "album", "year", "genre", "format")
        if _is_approved(contract_fields.get(field))
    ]
    inherited_fields = sorted({
        explanation.get("field")
        for explanation in (metadata.get("inheritance_summary") or {}).get("explanations", [])
        if explanation.get("inherited") and explanation.get("field")
    })
    inherited_track_count = sum(
        1 for item in track_profiles
        if (item.get("inheritance_summary") or {}).get("inherited_field_count", 0) > 0
    )
    missing_optional = [
        field for field in OPTIONAL_RADIO_FIELDS
        if not _has_value(release_profile.get(field)) and not _has_value(artist_profile.get(field))
    ]
    needs_review_warnings = sorted({warning for warning in warnings if warning in NEEDS_REVIEW_WARNINGS})
    info_warnings = sorted({warning for warning in [*warnings, *extraction_warnings] if warning not in NEEDS_REVIEW_WARNINGS})
    profile_consistency = "stale" if "profile_inheritance_stale" in warnings else "ok"
    return {
        "core_metadata_status": metadata.get("metadata_quality", "unknown"),
        "approved_core_fields": approved_core,
        "inherited_to_track_count": inherited_track_count,
        "inherited_fields": inherited_fields,
        "missing_optional_fields": missing_optional,
        "blocking_issue_count": len(blocking_items),
        "needs_review_issue_count": len(needs_review_warnings) or len(non_blocking_items),
        "info_issue_count": len(info_warnings),
        "setup_warnings": setup_warnings,
        "profile_consistency": profile_consistency,
        "artist_profile": artist_profile,
        "release_profile": release_profile,
        "track_profiles": track_profiles,
    }
