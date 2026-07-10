from __future__ import annotations

from difflib import SequenceMatcher
import json
from pathlib import Path
import re
import threading
import time
from typing import Any, Protocol
from urllib.error import HTTPError, URLError
from urllib.parse import quote_plus
from urllib.request import Request, urlopen

from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.time import now_utc
from app.core.version import METADATA_ASSIST_VERSION
from app.services.destination_authority import rebuild_music_batch_destination_from_attached_files
from app.services.metadata_candidates import add_candidate, make_candidate, normalize_metadata_text
from app.services.metadata_contract import metadata_field, now_metadata_timestamp
from app.services.music_metadata import (
    is_audio_file,
    music_track_numbers,
    normalize_track_title_for_destination,
    track_number_evidence,
)
from app.services.review_state import build_review_state
from app.models.archive import IngestBatch, IngestFile


UNKNOWN_VALUES = {
    "",
    "unknown",
    "unknown artist",
    "unknown album",
    "unknown year",
    "unknown ye",
    "unkn",
}
RELEASE_TYPES = {"Album", "EP", "Single", "Compilation", "Live", "Other"}
CACHE_TTL_SECONDS = 60 * 60 * 24
REQUEST_INTERVAL_SECONDS = 1.05
_MAX_RELEASE_RESULTS = 4

_cache: dict[str, tuple[float, Any]] = {}
_cache_lock = threading.Lock()
_last_request_at = 0.0


class MetadataEnrichmentError(RuntimeError):
    pass


class ReleaseProvider(Protocol):
    def search_release_payloads(self, evidence: dict[str, Any]) -> list[dict[str, Any]]:
        ...


def _clean_identity(value: Any) -> str:
    text = normalize_metadata_text(value)
    text = re.sub(r"^\s*\(?\d{4}\)?\s*[-:]\s*", "", text)
    text = re.sub(r"\s*\((?:EP|LP|Album|Single|Deluxe|Edition)\)\s*$", "", text, flags=re.I)
    text = re.sub(r"\s+\[(?:FLAC|MP3|WEB|CD|VINYL)[^\]]*\]\s*$", "", text, flags=re.I)
    return re.sub(r"\s+", " ", text).strip(" .-_")


def _key(value: Any) -> str:
    return re.sub(r"[^a-z0-9]+", " ", _clean_identity(value).casefold()).strip()


def _ratio(left: Any, right: Any) -> float:
    left_key = _key(left)
    right_key = _key(right)
    if not left_key or not right_key:
        return 0.0
    if left_key == right_key:
        return 1.0
    return SequenceMatcher(None, left_key, right_key).ratio()


def _year(value: Any) -> str | None:
    match = re.search(r"(?:19|20)\d{2}", str(value or ""))
    return match.group(0) if match else None


def _known(value: Any) -> bool:
    return _key(value) not in {_key(item) for item in UNKNOWN_VALUES}


def _artist_credit(value: Any) -> str:
    if not isinstance(value, list):
        return ""
    names: list[str] = []
    for item in value:
        if not isinstance(item, dict):
            continue
        artist = item.get("artist") if isinstance(item.get("artist"), dict) else item
        name = artist.get("name") if isinstance(artist, dict) else None
        if name:
            names.append(str(name))
    return "".join(names).strip()


def _release_type(payload: dict[str, Any]) -> str:
    group = payload.get("release-group") or {}
    primary = str(group.get("primary-type") or "").strip()
    secondary = [str(item) for item in group.get("secondary-types") or []]
    if primary in RELEASE_TYPES:
        return primary
    if "EP" in secondary:
        return "EP"
    return primary or "Other"


def _extract_tracks(payload: dict[str, Any]) -> list[dict[str, Any]]:
    tracks: list[dict[str, Any]] = []
    for medium_index, medium in enumerate(payload.get("media") or [], start=1):
        if not isinstance(medium, dict):
            continue
        for position, track in enumerate(medium.get("tracks") or [], start=1):
            if not isinstance(track, dict):
                continue
            recording = track.get("recording") or {}
            tracks.append({
                "disc_number": int(medium.get("position") or medium_index),
                "track_number": str(track.get("position") or position),
                "track_number_text": str(track.get("number") or track.get("position") or position),
                "title": str(track.get("title") or recording.get("title") or "").strip(),
                "length_ms": recording.get("length") or track.get("length"),
                "recording_id": recording.get("id"),
            })
    return tracks


def _normalize_provider_release(payload: dict[str, Any]) -> dict[str, Any]:
    date = payload.get("date") or payload.get("first-release-date")
    group = payload.get("release-group") or {}
    return {
        "provider": "musicbrainz",
        "release_id": payload.get("id"),
        "release_group_id": group.get("id"),
        "artist": _artist_credit(payload.get("artist-credit")),
        "title": str(payload.get("title") or "").strip(),
        "year": _year(date),
        "release_type": _release_type(payload),
        "genres": [
            str(item.get("name"))
            for item in payload.get("genres") or []
            if isinstance(item, dict) and item.get("name")
        ],
        "tracks": _extract_tracks(payload),
        "provider_score": float(payload.get("score") or 0) / 100,
    }


def _request_json(url: str) -> dict[str, Any]:
    global _last_request_at
    now = time.monotonic()
    with _cache_lock:
        cached = _cache.get(url)
        if cached and now - cached[0] < CACHE_TTL_SECONDS:
            return cached[1]
        delay = REQUEST_INTERVAL_SECONDS - (now - _last_request_at)
        if delay > 0:
            time.sleep(delay)
        request = Request(
            url,
            headers={
                "Accept": "application/json",
                "User-Agent": settings.musicbrainz_user_agent,
            },
        )
        try:
            with urlopen(request, timeout=settings.musicbrainz_timeout_seconds) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except HTTPError as exc:
            raise MetadataEnrichmentError(f"MusicBrainz returned HTTP {exc.code}.") from exc
        except (URLError, TimeoutError, OSError, json.JSONDecodeError) as exc:
            raise MetadataEnrichmentError("MusicBrainz lookup is unavailable.") from exc
        _last_request_at = time.monotonic()
        _cache[url] = (_last_request_at, payload)
        return payload


class MusicBrainzProvider:
    def __init__(self, base_url: str | None = None) -> None:
        self.base_url = (base_url or settings.musicbrainz_api_base_url).rstrip("/")

    def _url(self, path: str, query: str = "") -> str:
        return f"{self.base_url}/{path.lstrip('/')}?{query}" if query else f"{self.base_url}/{path.lstrip('/')}"

    def search_release_payloads(self, evidence: dict[str, Any]) -> list[dict[str, Any]]:
        title = str(evidence.get("release_title") or "").strip()
        tracks = evidence.get("tracks") or []
        if title:
            query = f'release:"{title}"'
            if evidence.get("year"):
                query += f" AND date:{evidence['year']}"
        elif tracks:
            query = f'track:"{tracks[0].get("title", "")}"'
        else:
            raise MetadataEnrichmentError("No release title or track title is available for lookup.")

        search = _request_json(self._url(
            "release",
            f"query={quote_plus(query)}&fmt=json&limit={_MAX_RELEASE_RESULTS}",
        ))
        releases = search.get("releases") or []
        payloads: list[dict[str, Any]] = []
        for result in releases[:_MAX_RELEASE_RESULTS]:
            release_id = result.get("id")
            if not release_id:
                continue
            detail = _request_json(self._url(
                f"release/{release_id}",
                "inc=recordings+artist-credits+release-groups+genres&fmt=json",
            ))
            detail["score"] = result.get("score", 0)
            payloads.append(_normalize_provider_release(detail))
        return payloads


def _batch_evidence(batch: IngestBatch) -> dict[str, Any]:
    metadata = batch.metadata_json or {}
    suggested = batch.suggested_metadata or {}
    release_title = (
        metadata.get("album")
        or suggested.get("album")
        or metadata.get("title")
        or Path(batch.source_path or "").name
    )
    release_year = _year(metadata.get("year") or metadata.get("date") or suggested.get("year")) or _year(release_title)
    artist = metadata.get("artist") or metadata.get("albumartist") or suggested.get("artist")
    tracks: list[dict[str, Any]] = []
    for ingest_file in batch.files or []:
        if not is_audio_file(Path(ingest_file.file_name or "")):
            continue
        file_metadata = ingest_file.metadata_json or {}
        track_evidence = track_number_evidence(file_metadata, ingest_file.file_name)
        disc = int(track_evidence.get("disc") or 1)
        track_number = track_evidence.get("resolved_track")
        title = (
            file_metadata.get("title")
            or normalize_track_title_for_destination(
                Path(ingest_file.file_name or "").stem,
                file_metadata.get("tracknumber"),
            )
        )
        if title:
            tracks.append({
                "file_id": ingest_file.id,
                "file_name": ingest_file.file_name,
                "disc_number": disc,
                "track_number": track_number,
                "title": str(title).strip(),
            })
    return {
        "batch_id": batch.id,
        "release_title": _clean_identity(release_title),
        "raw_release_title": str(release_title),
        "artist": str(artist).strip() if _known(artist) else None,
        "year": release_year,
        "tracks": tracks,
    }


def _score_release(evidence: dict[str, Any], release: dict[str, Any]) -> dict[str, Any]:
    local_tracks = evidence.get("tracks") or []
    provider_tracks = release.get("tracks") or []
    mapped: list[dict[str, Any]] = []
    used: set[tuple[int, str]] = set()

    for local in local_tracks:
        best: tuple[float, dict[str, Any]] | None = None
        for remote in provider_tracks:
            identity = (int(remote.get("disc_number") or 1), str(remote.get("track_number") or ""))
            if identity in used:
                continue
            title_score = _ratio(local.get("title"), remote.get("title"))
            number_score = 1.0 if (
                local.get("track_number") is not None
                and str(local.get("track_number")) == str(remote.get("track_number"))
                and int(local.get("disc_number") or 1) == int(remote.get("disc_number") or 1)
            ) else 0.0
            score = title_score * 0.75 + number_score * 0.25
            if best is None or score > best[0]:
                best = (score, remote)
        if best is None:
            continue
        match_score, remote = best
        if match_score >= 0.45:
            identity = (int(remote.get("disc_number") or 1), str(remote.get("track_number") or ""))
            used.add(identity)
            mapped.append({
                "file_id": local.get("file_id"),
                "file_name": local.get("file_name"),
                "score": round(match_score, 4),
                "disc_number": remote.get("disc_number"),
                "track_number": remote.get("track_number"),
                "title": remote.get("title"),
                "recording_id": remote.get("recording_id"),
                "release_id": release.get("release_id"),
            })

    track_score = (
        sum(float(item["score"]) for item in mapped) / len(local_tracks)
        if local_tracks else 0.0
    )
    weights = [(0.35, _ratio(evidence.get("release_title"), release.get("title")))]
    if evidence.get("year"):
        weights.append((0.1, 1.0 if evidence["year"] == release.get("year") else 0.0))
    if evidence.get("artist"):
        weights.append((0.15, _ratio(evidence["artist"], release.get("artist"))))
    if local_tracks:
        weights.append((0.4, track_score))
    weight_total = sum(weight for weight, _ in weights) or 1.0
    score = sum(weight * value for weight, value in weights) / weight_total
    result = dict(release)
    result.update({
        "match_score": round(score, 4),
        "match_confidence": round(score, 4),
        "matched_track_count": len(mapped),
        "local_track_count": len(local_tracks),
        "unmatched_track_count": max(0, len(local_tracks) - len(mapped)),
        "track_matches": mapped,
    })
    return result


def preview_music_metadata_enrichment(
    db: Session,
    batch_id: int,
    *,
    provider: ReleaseProvider | None = None,
) -> dict[str, Any]:
    batch = db.get(IngestBatch, batch_id)
    if batch is None:
        raise MetadataEnrichmentError("Batch not found.")
    if batch.detected_type != "music_album":
        raise MetadataEnrichmentError("Metadata enrichment currently supports music albums.")
    evidence = _batch_evidence(batch)
    provider = provider or MusicBrainzProvider()
    releases = provider.search_release_payloads(evidence)
    candidates = sorted(
        (_score_release(evidence, release) for release in releases),
        key=lambda item: (float(item.get("match_score") or 0), float(item.get("provider_score") or 0)),
        reverse=True,
    )
    return {
        "batch_id": batch.id,
        "provider": "musicbrainz",
        "query": evidence,
        "candidates": candidates[:_MAX_RELEASE_RESULTS],
        "message": (
            f"Found {len(candidates)} metadata match{'es' if len(candidates) != 1 else ''}."
            if candidates
            else "No metadata matches found."
        ),
    }


def apply_music_metadata_enrichment(
    db: Session,
    batch_id: int,
    release_id: str,
    *,
    provider: ReleaseProvider | None = None,
) -> dict[str, Any]:
    preview = preview_music_metadata_enrichment(db, batch_id, provider=provider)
    candidate = next(
        (item for item in preview["candidates"] if str(item.get("release_id")) == str(release_id)),
        None,
    )
    if candidate is None:
        raise MetadataEnrichmentError("That metadata match is no longer available. Run Find metadata again.")
    if float(candidate.get("match_confidence") or 0) < 0.55:
        raise MetadataEnrichmentError("The selected metadata match is too weak to apply safely.")

    batch = db.get(IngestBatch, batch_id)
    metadata = dict(batch.metadata_json or {})
    timestamp = now_metadata_timestamp()
    artist = str(candidate.get("artist") or "").strip()
    album = str(candidate.get("title") or "").strip()
    year = str(candidate.get("year") or "").strip()
    field_values = {
        "artist": artist,
        "albumartist": artist,
        "album": album,
        "year": year,
        "release_type": candidate.get("release_type"),
        "genre": (candidate.get("genres") or [None])[0],
    }
    contract = dict(metadata.get("metadata_contract") or {})
    contract_fields = dict(contract.get("fields") or {})
    for field_name, value in field_values.items():
        if not value:
            continue
        metadata[field_name] = value
        contract_fields[field_name] = metadata_field(
            value,
            source="musicbrainz_lookup",
            confidence=float(candidate.get("match_confidence") or 0),
            reason=f"MusicBrainz release match {candidate.get('release_id')}",
            approval_state="pending",
            approved=False,
            updated_at=timestamp,
        )
    contract["fields"] = contract_fields
    metadata["metadata_contract"] = contract
    metadata["field_sources"] = {
        **dict(metadata.get("field_sources") or {}),
        **{field: "musicbrainz_lookup" for field, value in field_values.items() if value},
    }
    metadata["metadata_enrichment"] = {
        "provider": "musicbrainz",
        "release_id": candidate.get("release_id"),
        "release_group_id": candidate.get("release_group_id"),
        "match_confidence": candidate.get("match_confidence"),
        "matched_track_count": candidate.get("matched_track_count"),
        "local_track_count": candidate.get("local_track_count"),
        "applied_at": timestamp,
        "approval_state": "pending_review",
    }
    metadata["metadata_assist_version"] = METADATA_ASSIST_VERSION
    metadata["metadata_candidates"] = dict(metadata.get("metadata_candidates") or {})
    for field, value in (
        ("album_artist", artist),
        ("album_title", album),
        ("year", year),
        ("release_type", candidate.get("release_type")),
        ("genre", (candidate.get("genres") or [None])[0]),
    ):
        if value:
            add_candidate(
                metadata["metadata_candidates"],
                make_candidate(
                    field,
                    value,
                    "musicbrainz_lookup",
                    "MusicBrainz release match",
                    float(candidate.get("match_confidence") or 0),
                    notes=[f"Release {candidate.get('release_id')}"],
                ),
            )

    mapped_by_id = {
        int(item["file_id"]): item
        for item in candidate.get("track_matches") or []
        if item.get("file_id") is not None
    }
    applied_track_count = 0
    for ingest_file in batch.files or []:
        match = mapped_by_id.get(ingest_file.id)
        if not match:
            continue
        file_metadata = dict(ingest_file.metadata_json or {})
        previous = {
            key: file_metadata.get(key)
            for key in ("artist", "albumartist", "album", "title", "tracknumber", "discnumber", "date")
            if key in file_metadata
        }
        file_metadata["metadata_enrichment"] = {
            "provider": "musicbrainz",
            "release_id": candidate.get("release_id"),
            "recording_id": match.get("recording_id"),
            "applied_at": timestamp,
            "previous_fields": previous,
            "approval_state": "pending_review",
        }
        file_metadata.update({
            "artist": artist or file_metadata.get("artist"),
            "albumartist": artist or file_metadata.get("albumartist"),
            "album": album or file_metadata.get("album"),
            "title": match.get("title") or file_metadata.get("title"),
            "tracknumber": str(match.get("track_number") or file_metadata.get("tracknumber") or ""),
            "discnumber": str(match.get("disc_number") or file_metadata.get("discnumber") or "1"),
            "date": year or file_metadata.get("date"),
            "musicbrainz_release_id": candidate.get("release_id"),
            "musicbrainz_release_group_id": candidate.get("release_group_id"),
            "musicbrainz_recording_id": match.get("recording_id"),
        })
        ingest_file.metadata_json = file_metadata
        applied_track_count += 1

    metadata = build_review_state(batch.detected_type, {**metadata, **field_values})
    batch.metadata_json = metadata
    suggested = dict(batch.suggested_metadata or {})
    suggested.update({
        "artist": artist or suggested.get("artist"),
        "album": album or suggested.get("album"),
        "year": year or suggested.get("year"),
        "genre": metadata.get("genre") or suggested.get("genre"),
        "format": metadata.get("format") or suggested.get("format"),
        "sources": {
            **dict(suggested.get("sources") or {}),
            "artist": "MusicBrainz release match",
            "album": "MusicBrainz release match",
            "year": "MusicBrainz release match",
        },
    })
    batch.suggested_metadata = suggested
    rebuild_music_batch_destination_from_attached_files(batch, db)
    batch.metadata_confirmed = False
    batch.status = "needs_metadata_review" if metadata.get("blocking_review_items") else "pending_review"
    batch.confidence = max(float(batch.confidence or 0), float(candidate.get("match_confidence") or 0))
    batch.updated_at = now_utc()
    db.commit()

    return {
        "batch_id": batch.id,
        "provider": "musicbrainz",
        "release_id": candidate.get("release_id"),
        "artist": artist,
        "album": album,
        "year": year or None,
        "release_type": candidate.get("release_type"),
        "genre": (candidate.get("genres") or [None])[0],
        "match_confidence": candidate.get("match_confidence"),
        "applied_track_count": applied_track_count,
        "matched_track_count": candidate.get("matched_track_count"),
        "local_track_count": candidate.get("local_track_count"),
        "filename_previews": [
            {
                "file_id": item.get("file_id"),
                "source_name": item.get("file_name"),
                "suggested_track_number": item.get("track_number"),
                "suggested_title": item.get("title"),
            }
            for item in candidate.get("track_matches") or []
        ],
        "suggested_destination": batch.suggested_destination,
        "message": (
            f"Applied {applied_track_count} track mapping{'s' if applied_track_count != 1 else ''}. "
            "Save metadata review to confirm the release."
        ),
    }