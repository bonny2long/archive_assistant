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
