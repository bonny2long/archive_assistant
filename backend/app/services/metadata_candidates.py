from __future__ import annotations

import re
from typing import Any


METADATA_ASSIST_VERSION = "v2.059"

GENERIC_UNKNOWN_VALUES = {
    "",
    "unknown",
    "unknown album",
    "unknown artist",
    "unknown author",
    "unknown title",
    "untitled",
    "unkn",
}
GENERIC_TRACK_RE = re.compile(
    r"^(?:0*\d+\s*[-_. ]*)?(?:track|chapter|audio|part)\s*0*\d+$",
    re.I,
)
TIMESTAMP_RE = re.compile(
    r"^(?:unknown album\s*)?\(?"
    r"(?:\d{1,2}[/-]\d{1,2}[/-](?:19|20)\d{2})"
    r"(?:\s+\d{1,2}:\d{2}(?::\d{2})?\s*(?:am|pm)?)?"
    r"\)?$",
    re.I,
)


def confidence_label(score: float) -> str:
    if score >= 0.85:
        return "high"
    if score >= 0.65:
        return "medium"
    return "low"


def normalize_metadata_text(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def is_generic_unknown_value(value: str) -> bool:
    normalized = normalize_metadata_text(value).casefold()
    return normalized in GENERIC_UNKNOWN_VALUES or normalized.startswith(
        "unknown album ("
    )


def is_generic_track_value(value: str) -> bool:
    normalized = normalize_metadata_text(value)
    return bool(GENERIC_TRACK_RE.fullmatch(normalized))


def is_generated_timestamp_value(value: str) -> bool:
    normalized = normalize_metadata_text(value)
    return bool(TIMESTAMP_RE.fullmatch(normalized))


def should_hide_candidate(field: str, value: str, source: str) -> bool:
    if is_generic_unknown_value(value):
        return True
    if field in {"title", "chapter_title"} and (
        is_generic_track_value(value)
        or is_generated_timestamp_value(value)
    ):
        return True
    return False


def candidate_quality_notes(
    field: str,
    value: str,
    source: str,
) -> list[str]:
    notes: list[str] = []
    if source.startswith("audio_tag") and (
        is_generic_unknown_value(value)
        or is_generic_track_value(value)
        or is_generated_timestamp_value(value)
    ):
        notes.append("generic embedded tag")
    return notes


def make_candidate(
    field: str,
    value: Any,
    source: str,
    source_label: str,
    confidence: float,
    notes: list[str] | None = None,
) -> dict[str, Any] | None:
    if value is None:
        return None
    normalized_value = normalize_metadata_text(value)
    if not normalized_value:
        return None
    quality_notes = candidate_quality_notes(
        str(field),
        normalized_value,
        str(source),
    )
    score = max(0.0, min(1.0, float(confidence)))
    hidden = should_hide_candidate(
        str(field),
        normalized_value,
        str(source),
    )
    if quality_notes:
        score = min(score, 0.35)
    return {
        "field": str(field),
        "value": normalized_value,
        "source": str(source),
        "source_label": str(source_label),
        "confidence": score,
        "confidence_label": confidence_label(score),
        "applied": False,
        "ignored": hidden,
        "notes": list(dict.fromkeys([
            *quality_notes,
            *[str(note) for note in (notes or []) if str(note).strip()],
        ])),
    }


def add_candidate(
    candidates: dict[str, list[dict[str, Any]]],
    candidate: dict[str, Any] | None,
) -> None:
    if not candidate:
        return
    field = str(candidate["field"])
    values = candidates.setdefault(field, [])
    identity = str(candidate["value"]).strip().casefold()
    for index, existing in enumerate(values):
        if str(existing.get("value", "")).strip().casefold() != identity:
            continue
        if float(candidate.get("confidence") or 0) > float(
            existing.get("confidence") or 0
        ):
            values[index] = candidate
        break
    else:
        values.append(candidate)
    values.sort(
        key=lambda item: (
            -float(item.get("confidence") or 0),
            str(item.get("value") or "").casefold(),
        )
    )


def preferred_candidate_value(
    candidates: dict[str, list[dict[str, Any]]],
    field: str,
    fallback: Any = None,
    *,
    min_confidence: str | float = "medium",
    require_not_filename_guess: bool = False,
) -> Any:
    confidence_thresholds = {
        "low": 0.0,
        "medium": 0.65,
        "high": 0.85,
    }
    threshold = (
        confidence_thresholds.get(min_confidence, 0.65)
        if isinstance(min_confidence, str)
        else float(min_confidence)
    )
    for candidate in candidates.get(field, []):
        if candidate.get("ignored"):
            continue
        if float(candidate.get("confidence") or 0) < threshold:
            continue
        if (
            require_not_filename_guess
            and candidate.get("source") == "filename"
        ):
            continue
        value = candidate.get("value")
        if value is not None and str(value).strip():
            return value
    return fallback
