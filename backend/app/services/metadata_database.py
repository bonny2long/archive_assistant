from __future__ import annotations

from pathlib import Path
from typing import Any

from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.core.time import now_utc
from app.models.archive import IngestBatch, IngestFile
from app.models.media_metadata import (
    GenreTaxonomy,
    MediaFile,
    MetadataReviewFlag,
    NormalizedMusicProfile,
    RawMediaTag,
)

MUSIC_AUDIO_ROLES = {"music_track", "discography_track"}
UNKNOWN_GENRE_FAMILY = "Unknown / Review Needed"
UNKNOWN_VALUES = {"", "unknown", "unknown artist", "unknown album", "unknown title", "none", "null"}

MOJIBAKE_PATTERNS = (
    "\u00c3\u00a2??",
    "\u00c3\u00a2\u00e2\u0082\u00ac\u00e2\u0084\u00a2",
    "\u00c3\u00a2\u00e2\u0082\u00ac\u00c5\u201c",
    "\u00c3\u00a2\u00e2\u0082\u00ac",
    "\u00c3\u0192\u00c2\u00a9",
    "\u00c3\u0192\u00c2\u00a8",
    "\u00c3\u0192\u00c2\u00a1",
    "\u00c3\u0192\u00c2\u00b1",
    "\u00ef\u00bf\u00bd",
)

GENRE_SEEDS: tuple[tuple[str, str, tuple[str, ...]], ...] = (
    ("Hip-Hop", "Hip-Hop / Rap / Mixtape", ("rap", "mixtape", "trap", "boom bap", "hip hop", "hip-hop")),
    ("Electronic", "Electronic / EDM / House / Techno / IDM / Ambient", ("edm", "house", "techno", "idm", "ambient", "electronica", "dance")),
    ("Classical", "Classical", ("classical", "opera", "symphony", "baroque", "chamber", "orchestral")),
    ("Reggae", "Reggae / Dancehall / Dub / Ska", ("dancehall", "dub", "ska", "roots reggae")),
    ("Afrobeats", "Afrobeats / Afro-fusion / Highlife / Amapiano / Afro-house", ("afrobeat", "afro-fusion", "highlife", "amapiano", "afro-house")),
    ("Folk", "Folk / Singer-Songwriter / Americana / Traditional Folk", ("singer-songwriter", "americana", "traditional folk")),
    ("Jazz", "Jazz", ("bebop", "fusion", "smooth jazz", "vocal jazz")),
    ("R&B", "R&B / Soul / Funk", ("rnb", "r&b", "soul", "funk", "neo soul")),
    ("Rock", "Rock / Alternative / Indie", ("alternative", "indie", "alt rock", "indie rock")),
    ("Pop", "Pop", ("dance pop", "synthpop", "synth pop")),
    ("Country", "Country", ("bluegrass", "country pop")),
    ("Blues", "Blues", ("delta blues", "electric blues")),
    ("Gospel", "Gospel", ("christian", "worship")),
    ("Latin", "Latin / Caribbean", ("reggaeton", "salsa", "bachata", "merengue", "caribbean")),
    ("Metal", "Metal", ("heavy metal", "death metal", "black metal")),
    ("Punk", "Punk", ("post-punk", "hardcore")),
    ("Soundtrack", "Soundtrack / Score", ("score", "ost", "film score", "game score")),
    ("World", "World / International", ("international", "global")),
    ("Spoken Word", "Spoken Word / Comedy", ("comedy", "stand-up", "spoken word")),
    ("Children's", "Children's", ("children", "kids", "childrens", "children's")),
    ("Unknown", UNKNOWN_GENRE_FAMILY, ("unknown", "review needed")),
)


def _key(value: str | None) -> str:
    return " ".join(str(value or "").strip().casefold().replace("_", "-").split())


def _clean(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, (list, tuple)):
        for item in value:
            cleaned = _clean(item)
            if cleaned:
                return cleaned
        return None
    text = str(value).strip()
    return text or None


def _is_unknown(value: Any) -> bool:
    return _key(_clean(value)) in UNKNOWN_VALUES


def _metadata_value(metadata: dict[str, Any], *keys: str) -> str | None:
    fields = metadata.get("embedded_metadata_fields") or {}
    embedded = metadata.get("embedded_metadata") or {}
    embedded_fields = embedded.get("fields") or {}
    for key in keys:
        value = _clean(metadata.get(key))
        if value:
            return value
        value = _clean(fields.get(key))
        if value:
            return value
        value = _clean(embedded_fields.get(key))
        if value:
            return value
    return None


def _technical(metadata: dict[str, Any]) -> dict[str, Any]:
    embedded = metadata.get("embedded_metadata") or {}
    return {
        **dict(embedded.get("technical") or {}),
        **dict(metadata.get("embedded_technical") or {}),
    }


def _artwork(metadata: dict[str, Any]) -> list[dict[str, Any]]:
    embedded = metadata.get("embedded_metadata") or {}
    artwork = metadata.get("embedded_artwork") or embedded.get("artwork") or []
    return list(artwork) if isinstance(artwork, list) else []


def _int_value(value: Any) -> int | None:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None


def _float_value(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _metadata_confidence(metadata: dict[str, Any]) -> float | None:
    for key in ("metadata_confidence", "confidence"):
        value = _float_value(metadata.get(key))
        if value is not None:
            return value
    return None


def _source_relative(path: Path, batch: IngestBatch | None) -> str | None:
    if batch is None:
        return path.name
    source = Path(batch.source_path)
    try:
        if source.is_dir():
            return str(path.relative_to(source))
    except ValueError:
        pass
    return path.name


def seed_genre_taxonomy(db: Session) -> None:
    existing = {
        row.canonical_genre: row
        for row in db.query(GenreTaxonomy).all()
    }
    for canonical, family, aliases in GENRE_SEEDS:
        row = existing.get(canonical)
        if row is None:
            db.add(GenreTaxonomy(
                canonical_genre=canonical,
                display_genre=canonical,
                genre_family=family,
                display_family=family,
                aliases_json=list(aliases),
                is_active=True,
            ))
            continue
        row.display_genre = row.display_genre or canonical
        row.genre_family = row.genre_family or family
        row.display_family = row.display_family or family
        row.aliases_json = row.aliases_json or list(aliases)
        row.is_active = True
        row.updated_at = now_utc()


def _fallback_genre_map() -> dict[str, str]:
    mapping: dict[str, str] = {}
    for canonical, family, aliases in GENRE_SEEDS:
        mapping[_key(canonical)] = family
        for alias in aliases:
            mapping[_key(alias)] = family
    return mapping


FALLBACK_GENRE_MAP = _fallback_genre_map()


def genre_family_for(raw_genre: str | None, db: Session | None = None) -> str:
    cleaned = _clean(raw_genre)
    if not cleaned:
        return UNKNOWN_GENRE_FAMILY
    genre_key = _key(cleaned)
    if db is not None:
        rows = db.query(GenreTaxonomy).filter(GenreTaxonomy.is_active.is_(True)).all()
        for row in rows:
            if genre_key == _key(row.canonical_genre) or genre_key == _key(row.display_genre):
                return row.display_family or row.genre_family or UNKNOWN_GENRE_FAMILY
            for alias in row.aliases_json or []:
                if genre_key == _key(alias):
                    return row.display_family or row.genre_family or UNKNOWN_GENRE_FAMILY
    return FALLBACK_GENRE_MAP.get(genre_key, UNKNOWN_GENRE_FAMILY)


def _find_media_file(db: Session, ingest_file: IngestFile) -> MediaFile | None:
    if ingest_file.id is not None:
        row = db.query(MediaFile).filter(MediaFile.ingest_file_id == ingest_file.id).one_or_none()
        if row is not None:
            return row
    if ingest_file.checksum:
        row = (
            db.query(MediaFile)
            .filter(
                MediaFile.checksum == ingest_file.checksum,
                MediaFile.absolute_path == ingest_file.file_path,
            )
            .one_or_none()
        )
        if row is not None:
            return row
    return db.query(MediaFile).filter(MediaFile.absolute_path == ingest_file.file_path).one_or_none()


def _raw_tag_for(db: Session, media_file: MediaFile) -> RawMediaTag | None:
    return (
        db.query(RawMediaTag)
        .filter(RawMediaTag.media_file_id == media_file.id, RawMediaTag.tag_source == "mutagen")
        .one_or_none()
    )


def _profile_for(db: Session, media_file: MediaFile) -> NormalizedMusicProfile | None:
    return (
        db.query(NormalizedMusicProfile)
        .filter(NormalizedMusicProfile.media_file_id == media_file.id)
        .one_or_none()
    )


def _detect_mojibake(value: str | None) -> bool:
    text = value or ""
    return any(pattern in text for pattern in MOJIBAKE_PATTERNS)


def _flag_exists(
    db: Session,
    *,
    media_file: MediaFile,
    batch: IngestBatch | None,
    flag_type: str,
    field_name: str | None,
) -> bool:
    return db.query(MetadataReviewFlag).filter(
        MetadataReviewFlag.media_file_id == media_file.id,
        MetadataReviewFlag.ingest_batch_id == (batch.id if batch else None),
        MetadataReviewFlag.flag_type == flag_type,
        MetadataReviewFlag.field_name == field_name,
        MetadataReviewFlag.status == "open",
    ).first() is not None


def _add_flag(
    db: Session,
    *,
    media_file: MediaFile,
    batch: IngestBatch | None,
    flag_type: str,
    severity: str,
    field_name: str | None,
    raw_value: str | None,
    normalized_value: str | None,
    message: str,
) -> int:
    if _flag_exists(
        db,
        media_file=media_file,
        batch=batch,
        flag_type=flag_type,
        field_name=field_name,
    ):
        return 0
    db.add(MetadataReviewFlag(
        media_file_id=media_file.id,
        ingest_batch_id=batch.id if batch else None,
        flag_type=flag_type,
        severity=severity,
        field_name=field_name,
        raw_value=raw_value,
        normalized_value=normalized_value,
        message=message,
        status="open",
    ))
    return 1


def _profile_values(metadata: dict[str, Any], db: Session) -> dict[str, Any]:
    artist = _metadata_value(metadata, "artist", "trackartist")
    album_artist = _metadata_value(metadata, "album_artist", "albumartist", "album artist")
    album = _metadata_value(metadata, "album")
    title = _metadata_value(metadata, "title")
    primary_genre = _metadata_value(metadata, "genre", "primary_genre")
    return {
        "artist": artist,
        "album_artist": album_artist,
        "album": album,
        "title": title,
        "track_number": _metadata_value(metadata, "tracknumber", "track_number"),
        "disc_number": _metadata_value(metadata, "discnumber", "disc_number"),
        "year": _metadata_value(metadata, "date", "year", "original_date"),
        "release_type": _metadata_value(metadata, "release_type"),
        "primary_genre": primary_genre,
        "genre_family": genre_family_for(primary_genre, db),
        "subgenres_json": metadata.get("subgenres") or metadata.get("subgenres_json"),
        "moods_json": metadata.get("moods") or metadata.get("moods_json"),
        "energy": _metadata_value(metadata, "energy"),
        "language": _metadata_value(metadata, "language"),
        "region": _metadata_value(metadata, "region"),
        "composer": _metadata_value(metadata, "composer"),
        "conductor": _metadata_value(metadata, "conductor"),
        "orchestra": _metadata_value(metadata, "orchestra"),
        "ensemble": _metadata_value(metadata, "ensemble"),
        "soloist": _metadata_value(metadata, "soloist"),
        "work": _metadata_value(metadata, "work"),
        "movement": _metadata_value(metadata, "movement"),
        "metadata_status": _metadata_value(metadata, "metadata_quality", "metadata_status") or "snapshot",
        "metadata_confidence": _metadata_confidence(metadata),
        "metadata_source": _metadata_value(metadata, "metadata_source") or "archive_assistant_snapshot",
        "approved": bool(metadata.get("approved") or metadata.get("review_confirmed")),
    }


def _detect_flags(
    db: Session,
    *,
    media_file: MediaFile,
    batch: IngestBatch | None,
    values: dict[str, Any],
) -> int:
    created = 0
    for field in ("artist", "album_artist", "album", "title", "track_number"):
        if _is_unknown(values.get(field)):
            created += _add_flag(
                db,
                media_file=media_file,
                batch=batch,
                flag_type=f"missing_{field}",
                severity="warning",
                field_name=field,
                raw_value=_clean(values.get(field)),
                normalized_value=None,
                message=f"Missing {field.replace('_', ' ')} metadata.",
            )
    for field in ("artist", "album_artist", "album", "title", "primary_genre", "composer"):
        raw = _clean(values.get(field))
        if _detect_mojibake(raw):
            created += _add_flag(
                db,
                media_file=media_file,
                batch=batch,
                flag_type="mojibake_detected",
                severity="warning",
                field_name=field,
                raw_value=raw,
                normalized_value=raw,
                message="Possible mojibake detected. Detection only; value was not changed.",
            )
    genre = _clean(values.get("primary_genre"))
    if not genre:
        created += _add_flag(
            db,
            media_file=media_file,
            batch=batch,
            flag_type="unknown_genre",
            severity="warning",
            field_name="primary_genre",
            raw_value=genre,
            normalized_value=UNKNOWN_GENRE_FAMILY,
            message="Missing genre maps to Unknown / Review Needed.",
        )
    elif values.get("genre_family") == UNKNOWN_GENRE_FAMILY:
        created += _add_flag(
            db,
            media_file=media_file,
            batch=batch,
            flag_type="unmapped_genre",
            severity="warning",
            field_name="primary_genre",
            raw_value=genre,
            normalized_value=UNKNOWN_GENRE_FAMILY,
            message="Genre is not mapped in the local taxonomy.",
        )
    if values.get("genre_family") == "Classical" and _is_unknown(values.get("composer")) and (
        _is_unknown(values.get("artist")) and _is_unknown(values.get("album_artist"))
    ):
        created += _add_flag(
            db,
            media_file=media_file,
            batch=batch,
            flag_type="classical_metadata_incomplete",
            severity="warning",
            field_name="composer",
            raw_value=_clean(values.get("composer")),
            normalized_value=None,
            message="Classical item is missing composer and performer/album artist metadata.",
        )
    return created


def snapshot_ingest_file_metadata(
    db: Session,
    ingest_file: IngestFile,
    batch: IngestBatch | None = None,
) -> MediaFile | None:
    if ingest_file.detected_role not in MUSIC_AUDIO_ROLES:
        return None
    metadata = dict(ingest_file.metadata_json or {})
    technical = _technical(metadata)
    artwork = _artwork(metadata)
    now = now_utc()
    media_file = _find_media_file(db, ingest_file)
    if media_file is None:
        media_file = MediaFile(
            ingest_file_id=ingest_file.id,
            ingest_batch_id=batch.id if batch else ingest_file.batch_id,
            absolute_path=ingest_file.file_path,
            relative_path=_source_relative(Path(ingest_file.file_path), batch),
            file_name=ingest_file.file_name,
            extension=ingest_file.extension,
            size_bytes=ingest_file.size_bytes,
            checksum=ingest_file.checksum,
            media_type="music",
            detected_role=ingest_file.detected_role,
        )
        db.add(media_file)
        db.flush()
    media_file.ingest_file_id = ingest_file.id
    media_file.ingest_batch_id = batch.id if batch else ingest_file.batch_id
    media_file.absolute_path = ingest_file.file_path
    media_file.relative_path = _source_relative(Path(ingest_file.file_path), batch)
    media_file.file_name = ingest_file.file_name
    media_file.extension = ingest_file.extension
    media_file.size_bytes = ingest_file.size_bytes
    media_file.checksum = ingest_file.checksum
    media_file.media_type = "music"
    media_file.detected_role = ingest_file.detected_role
    media_file.duration_seconds = _float_value(technical.get("duration_seconds"))
    media_file.bitrate = _int_value(technical.get("bitrate"))
    media_file.sample_rate = _int_value(technical.get("sample_rate"))
    media_file.codec = _clean(technical.get("codec"))
    media_file.container = _clean(technical.get("container")) or ingest_file.extension.lstrip(".")
    media_file.embedded_artwork_count = int(metadata.get("embedded_artwork_count") or technical.get("embedded_artwork_count") or len(artwork) or 0)
    media_file.updated_at = now

    raw_payload = dict(metadata.get("embedded_metadata") or {})
    raw_tag = _raw_tag_for(db, media_file)
    if raw_tag is None:
        raw_tag = RawMediaTag(media_file_id=media_file.id, tag_source="mutagen")
        db.add(raw_tag)
    raw_tag.read_ok = bool(raw_payload.get("read_ok") or metadata.get("embedded_metadata_fields"))
    raw_tag.raw_fields_json = dict(metadata.get("embedded_metadata_fields") or raw_payload.get("fields") or {})
    raw_tag.raw_technical_json = technical
    raw_tag.raw_artwork_json = artwork
    raw_tag.raw_payload_json = raw_payload or metadata
    raw_tag.warnings_json = list(metadata.get("extraction_warnings") or raw_payload.get("warnings") or [])
    raw_tag.extracted_at = now

    values = _profile_values(metadata, db)
    profile = _profile_for(db, media_file)
    if profile is None:
        profile = NormalizedMusicProfile(media_file_id=media_file.id)
        db.add(profile)
    for key, value in values.items():
        setattr(profile, key, value)
    profile.updated_at = now

    db.flush()
    _detect_flags(db, media_file=media_file, batch=batch, values=values)
    return media_file


def snapshot_batch_metadata(db: Session, batch: IngestBatch) -> dict:
    files = list(batch.files) or db.query(IngestFile).filter(IngestFile.batch_id == batch.id).all()
    media_files = 0
    raw_tags = 0
    profiles = 0
    flags_before = db.query(MetadataReviewFlag).filter(
        or_(MetadataReviewFlag.ingest_batch_id == batch.id, MetadataReviewFlag.ingest_batch_id.is_(None))
    ).count()
    for ingest_file in files:
        row = snapshot_ingest_file_metadata(db, ingest_file, batch)
        if row is None:
            continue
        media_files += 1
        if _raw_tag_for(db, row) is not None:
            raw_tags += 1
        if _profile_for(db, row) is not None:
            profiles += 1
    db.flush()
    flags_after = db.query(MetadataReviewFlag).filter(
        or_(MetadataReviewFlag.ingest_batch_id == batch.id, MetadataReviewFlag.ingest_batch_id.is_(None))
    ).count()
    return {
        "media_files": media_files,
        "raw_tags": raw_tags,
        "normalized_profiles": profiles,
        "flags": max(flags_after - flags_before, 0),
    }
