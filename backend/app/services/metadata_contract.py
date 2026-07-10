from __future__ import annotations

from collections.abc import Mapping
import os
from datetime import datetime, timezone
from typing import Any


METADATA_CONTRACT_VERSION = "aa-m0.1"
DETAILED_FIELD_ENVELOPE_VERSION = 1

VALID_METADATA_SOURCES = {
    "embedded_tag",
    "folder_inference",
    "filename_inference",
    "path_context",
    "archive_assistant_rule",
    "artist_profile",
    "release_profile",
    "track_override",
    "series_profile",
    "show_profile",
    "movie_profile",
    "manual",
    "local_metadata_db",
    "local_audio_analysis",
    "musicbrainz_lookup",
    "local_ai_suggestion",
    "unknown",
}

VALID_APPROVAL_STATES = {
    "pending",
    "approved",
    "rejected",
    "needs_review",
    "inherited",
    "stale",
    "unknown",
}

PLACEHOLDER_METADATA_VALUES = {
    "",
    "missing",
    "n/a",
    "none",
    "null",
    "unkn",
    "unknown",
    "unknown album",
    "unknown artist",
    "unknown year",
    "unknown ye",
}

def now_metadata_timestamp() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def resolve_approval_actor(request=None, fallback: str = "local_admin") -> str:
    actor = os.getenv("APPROVAL_ACTOR", "").strip()
    return actor or fallback


def _normalize_source(source: str | None) -> str:
    if source in VALID_METADATA_SOURCES:
        return str(source)
    return "unknown"


def _normalize_approval_state(approval_state: str | None) -> str:
    if approval_state in VALID_APPROVAL_STATES:
        return str(approval_state)
    return "unknown"


def _clamp_confidence(confidence: float | int | str | None) -> float | None:
    if confidence is None:
        return None
    try:
        parsed = float(confidence)
    except (TypeError, ValueError):
        return None
    return max(0.0, min(1.0, parsed))


def metadata_field(
    value: Any,
    *,
    source: str = "unknown",
    confidence: float | None = None,
    reason: str | None = None,
    approval_state: str = "pending",
    approved: bool | None = None,
    approved_at: str | None = None,
    approved_by: str | None = None,
    updated_at: str | None = None,
) -> dict[str, Any]:
    normalized_state = _normalize_approval_state(approval_state)
    if approved is None:
        approved = normalized_state == "approved"
    return {
        "envelope_version": DETAILED_FIELD_ENVELOPE_VERSION,
        "value": value,
        "source": _normalize_source(source),
        "confidence": _clamp_confidence(confidence),
        "reason": reason,
        "approval_state": normalized_state,
        "approved": bool(approved),
        "approved_at": approved_at,
        "approved_by": approved_by,
        "updated_at": updated_at or now_metadata_timestamp(),
    }


def is_field_envelope(value: object) -> bool:
    return (
        isinstance(value, Mapping)
        and "value" in value
        and (
            value.get("envelope_version") == DETAILED_FIELD_ENVELOPE_VERSION
            or "source" in value
            or "approval_state" in value
        )
    )


def field_value(value: Any, default: Any = None) -> Any:
    if is_field_envelope(value):
        return value.get("value", default)
    return default if value is None else value


def is_placeholder_metadata_value(value: Any) -> bool:
    raw = field_value(value)
    if raw is None:
        return True
    if isinstance(raw, str):
        normalized = raw.strip().casefold()
        return normalized in PLACEHOLDER_METADATA_VALUES
    if isinstance(raw, (list, tuple, set, dict)):
        return not bool(raw)
    return False


def field_source(value: Any, default: str = "unknown") -> str:
    if is_field_envelope(value):
        return _normalize_source(str(value.get("source") or default))
    return default


def field_confidence(value: Any, default: Any = None) -> Any:
    if is_field_envelope(value):
        confidence = _clamp_confidence(value.get("confidence"))
        return default if confidence is None else confidence
    return default


def approve_field(
    field_or_value: Any,
    *,
    approved_by: str | None = None,
    reason: str | None = None,
) -> dict[str, Any]:
    field = (
        dict(field_or_value)
        if is_field_envelope(field_or_value)
        else metadata_field(field_or_value)
    )
    timestamp = now_metadata_timestamp()
    approved_by = approved_by or resolve_approval_actor()
    field.update({
        "approval_state": "approved",
        "approved": True,
        "approved_at": timestamp,
        "approved_by": approved_by,
        "updated_at": timestamp,
    })
    if reason is not None:
        field["reason"] = reason
    return field


def inherit_field(
    field_or_value: Any,
    *,
    source: str,
    reason: str | None = None,
    confidence: float | None = None,
) -> dict[str, Any]:
    value = field_value(field_or_value)
    field = (
        dict(field_or_value)
        if is_field_envelope(field_or_value)
        else metadata_field(value)
    )
    field.update({
        "source": _normalize_source(source),
        "approval_state": "inherited",
        "approved": False,
        "updated_at": now_metadata_timestamp(),
    })
    if reason is not None:
        field["reason"] = reason
    if confidence is not None:
        field["confidence"] = _clamp_confidence(confidence)
    return field


def compact_metadata_value(value: Any) -> Any:
    if is_field_envelope(value):
        return value.get("value")
    if isinstance(value, dict):
        return {
            key: compact_metadata_value(item)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [compact_metadata_value(item) for item in value]
    return value


def detailed_metadata_value(value: Any) -> dict[str, Any]:
    if is_field_envelope(value):
        return dict(value)
    return metadata_field(value)


def metadata_manifest_header(
    *,
    manifest_type: str,
    manifest_version: str | int,
    media_type: str | None = None,
    metadata_version: str | None = None,
    sources_summary: dict | None = None,
) -> dict[str, Any]:
    generated_at = now_metadata_timestamp()
    header = {
        "metadata_contract_version": METADATA_CONTRACT_VERSION,
        "manifest_type": manifest_type,
        "manifest_version": manifest_version,
        "metadata_version": metadata_version or generated_at,
        "metadata_generated_at": generated_at,
        "metadata_sources_summary": sources_summary or {},
    }
    if media_type is not None:
        header["media_type"] = media_type
    return header


def summarize_metadata_sources(metadata: Mapping[str, Any] | None) -> dict[str, int]:
    counts: dict[str, int] = {}

    def visit(value: Any) -> None:
        if is_field_envelope(value):
            source = field_source(value)
            counts[source] = counts.get(source, 0) + 1
            return
        if isinstance(value, Mapping):
            for item in value.values():
                visit(item)
        elif isinstance(value, list):
            for item in value:
                visit(item)

    if metadata:
        contract = metadata.get("metadata_contract")
        if isinstance(contract, Mapping):
            fields = contract.get("fields")
            if isinstance(fields, Mapping):
                visit(fields)
        else:
            visit(metadata)
    counts.setdefault("unknown", 0)
    return counts


def apply_manual_field_envelopes(
    metadata: dict[str, Any],
    fields: list[str] | tuple[str, ...],
    *,
    reason: str,
    approved_by: str | None = None,
) -> dict[str, Any]:
    approved_by = approved_by or resolve_approval_actor()
    contract = dict(metadata.get("metadata_contract") or {})
    contract["version"] = METADATA_CONTRACT_VERSION
    contract_fields = dict(contract.get("fields") or {})
    timestamp = now_metadata_timestamp()
    touched = [field_name for field_name in fields if field_name in metadata]
    for field_name in touched:
        contract_fields[field_name] = metadata_field(
            metadata.get(field_name),
            source="manual",
            confidence=1.0,
            reason=reason,
            approval_state="approved",
            approved=True,
            approved_at=timestamp,
            approved_by=approved_by,
            updated_at=timestamp,
        )
    contract["fields"] = contract_fields
    metadata["metadata_contract"] = contract
    metadata["field_sources"] = {
        **dict(metadata.get("field_sources") or {}),
        **{field_name: "manual" for field_name in touched},
    }
    metadata["field_confidence"] = {
        **dict(metadata.get("field_confidence") or {}),
        **{field_name: 1.0 for field_name in touched},
    }
    return metadata
