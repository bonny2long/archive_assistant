from __future__ import annotations

import re
import unicodedata
from typing import Any

from app.core.version import METADATA_ASSIST_VERSION

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
GENERIC_BOOK_METADATA_VALUES = {
    "[no data]",
    "no data",
    "n/a",
    "unknown",
    "unknown author",
    "unknown title",
    "untitled",
    "document",
    "microsoft word - document",
    "title",
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
    cleaned: list[str] = []
    for character in str(value or ""):
        if character == "\x00":
            continue
        if unicodedata.category(character).startswith("C"):
            cleaned.append(" ")
        else:
            cleaned.append(character)
    text = "".join(cleaned)
    return re.sub(r"\s+", " ", text).strip(" \t\r\n")


def is_garbage_document_title(value: Any) -> bool:
    raw = str(value or "")
    if any(unicodedata.category(char).startswith("C") for char in raw):
        return True
    text = normalize_metadata_text(raw).strip(" ._-")
    normalized = text.casefold()
    if len(re.sub(r"[^a-z0-9]", "", normalized)) < 4:
        return True
    if re.match(
        r"^(?:tmp|temp)[a-z0-9_-]*$",
        normalized,
    ):
        return True
    if re.match(r"^scan(?:ner)?(?:[_ -].*)?$", normalized):
        return True
    if normalized in {"document", "untitled"}:
        return True
    if re.match(r"^(?:microsoft word|adobe acrobat)\b", normalized):
        return True
    words = re.findall(r"[A-Za-z][A-Za-z'’&-]*", text)
    if not words:
        return True
    if (
        len(words) == 1
        and len(text) >= 8
        and re.search(r"[a-z][A-Z]|[A-Z][a-z].*\d|\d.*[A-Za-z]", text)
    ):
        return True
    return False


BUSINESS_AUTHOR_WORDS = {
    "books",
    "company",
    "group",
    "inc",
    "llc",
    "media",
    "press",
    "publishing",
    "studios",
}


def canonicalize_author_name(value: Any) -> str:
    text = normalize_metadata_text(value)
    if text.count(",") != 1:
        return text
    last, first = (part.strip() for part in text.split(",", 1))
    combined_words = {
        word.casefold()
        for word in re.findall(r"[A-Za-z][A-Za-z'’.-]*", text)
    }
    if combined_words & BUSINESS_AUTHOR_WORDS:
        return text
    surname = re.compile(r"^[A-Za-z][A-Za-z'’.-]*$")
    given_names = re.compile(
        r"^[A-Za-z][A-Za-z'’.-]*(?:\s+[A-Za-z][A-Za-z'’.-]*)?$"
    )
    if not surname.fullmatch(last) or not given_names.fullmatch(first):
        return text
    return f"{first} {last}"


def is_generic_unknown_value(value: str) -> bool:
    normalized = normalize_metadata_text(value).casefold()
    return normalized in GENERIC_UNKNOWN_VALUES or normalized.startswith(
        "unknown album ("
    )


def is_generic_book_metadata_value(value: str) -> bool:
    return normalize_metadata_text(value).casefold() in GENERIC_BOOK_METADATA_VALUES


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
    if (
        field == "title"
        and source.startswith("pdf_document_info")
        and is_garbage_document_title(value)
    ):
        return True
    if (
        field in {"title", "author", "year"}
        and source.startswith(("epub_opf", "pdf_document_info"))
        and is_generic_book_metadata_value(value)
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
    if (
        field == "title"
        and source.startswith("pdf_document_info")
        and is_garbage_document_title(value)
    ):
        notes.append("garbage PDF document title")
    if (
        field in {"title", "author", "year"}
        and source.startswith(("epub_opf", "pdf_document_info"))
        and is_generic_book_metadata_value(value)
    ):
        notes.append("generic embedded book metadata ignored")
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
    if str(field) == "author":
        normalized_value = canonicalize_author_name(normalized_value)
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
    if "generic embedded book metadata ignored" in quality_notes:
        score = min(score, 0.2)
    elif quality_notes:
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
