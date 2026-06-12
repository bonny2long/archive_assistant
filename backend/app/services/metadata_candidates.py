from __future__ import annotations

from typing import Any


def confidence_label(score: float) -> str:
    if score >= 0.85:
        return "high"
    if score >= 0.65:
        return "medium"
    return "low"


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
    normalized_value = str(value).strip()
    if not normalized_value:
        return None
    score = max(0.0, min(1.0, float(confidence)))
    return {
        "field": str(field),
        "value": normalized_value,
        "source": str(source),
        "source_label": str(source_label),
        "confidence": score,
        "confidence_label": confidence_label(score),
        "applied": False,
        "ignored": False,
        "notes": [str(note) for note in (notes or []) if str(note).strip()],
    }


def add_candidate(
    candidates: dict[str, list[dict[str, Any]]],
    candidate: dict[str, Any] | None,
) -> None:
    if not candidate:
        return
    field = str(candidate["field"])
    values = candidates.setdefault(field, [])
    identity = (
        str(candidate["value"]).casefold(),
        str(candidate["source"]).casefold(),
    )
    if any(
        (
            str(existing.get("value", "")).casefold(),
            str(existing.get("source", "")).casefold(),
        )
        == identity
        for existing in values
    ):
        return
    values.append(candidate)
    values.sort(
        key=lambda item: (
            -float(item.get("confidence") or 0),
            str(item.get("value") or "").casefold(),
        )
    )
