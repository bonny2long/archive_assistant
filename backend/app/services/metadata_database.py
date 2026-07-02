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
BROAD_GENRE_FAMILIES = {"World / International"}
UNKNOWN_VALUES = {"", "unknown", "unknown artist", "unknown album", "unknown title", "none", "null"}

FLAG_SEVERITY = {
    "mojibake_detected": "high",
    "unknown_genre": "high",
    "missing_artist": "high",
    "missing_title": "high",
    "unmapped_genre": "medium",
    "classical_metadata_incomplete": "medium",
    "missing_composer": "medium",
    "missing_work_or_movement": "medium",
    "missing_performer_or_ensemble": "medium",
    "missing_album_artist": "medium",
    "possible_broad_genre": "low",
    "missing_album": "low",
    "missing_track_number": "low",
}

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

# Overlap decisions are deterministic for M4B: bluegrass and americana map to
# Folk, reggaeton maps to Latin / Caribbean, and rhythm and blues maps to R&B.
GENRE_SEEDS: tuple[tuple[str, str, tuple[str, ...]], ...] = (
    ("Hip-Hop", "Hip-Hop / Rap / Mixtape", ("hip hop", "hip-hop", "hiphop", "rap", "rap/hip hop", "rap hip hop", "trap", "southern hip-hop", "southern hip hop", "east coast hip-hop", "east coast hip hop", "west coast hip-hop", "west coast hip hop", "alternative hip-hop", "alternative hip hop", "jazz rap", "conscious hip-hop", "conscious hip hop", "boom bap", "gangsta rap", "mixtape")),
    ("Electronic", "Electronic / EDM / House / Techno / IDM / Ambient", ("electronic", "electronica", "edm", "dance", "house", "progressive house", "electro house", "tech house", "deep house", "disco house", "french house", "techno", "acid techno", "ambient techno", "idm", "intelligent dance music", "ambient", "ambient electronic", "experimental electronic", "downtempo", "trip hop", "synthpop", "synth pop", "electropop", "electro pop", "nu-disco", "nu disco")),
    ("Classical", "Classical", ("classical", "baroque", "romantic", "renaissance", "modern classical", "contemporary classical", "orchestral", "symphony", "concerto", "sonata", "chamber music", "opera", "choral", "solo piano", "piano", "violin", "cello", "string quartet", "classical piano", "classical guitar")),
    ("Reggae", "Reggae / Dancehall / Dub / Ska", ("reggae", "roots reggae", "roots", "dub", "dancehall", "ska", "rocksteady", "lovers rock", "ragga")),
    ("Afrobeats", "Afrobeats / African", ("afrobeats", "afro beats", "afrobeat", "afro beat", "afropop", "afro pop", "afro-fusion", "afro fusion", "afro-house", "afro house", "amapiano", "highlife", "soukos", "soukous", "kwaito", "azonto", "bongo flava", "makossa", "juju", "fuji", "afrosoul", "afro soul")),
    ("Folk", "Folk / Singer-Songwriter / Americana", ("folk", "traditional folk", "indie folk", "folk rock", "singer-songwriter", "singer songwriter", "acoustic", "americana", "bluegrass", "roots", "roots music", "contemporary folk")),
    ("Jazz", "Jazz", ("jazz", "bebop", "hard bop", "post-bop", "post bop", "modal jazz", "cool jazz", "free jazz", "fusion", "jazz fusion", "smooth jazz", "vocal jazz", "latin jazz", "big band", "swing")),
    ("R&B", "R&B / Soul / Funk", ("r&b", "rnb", "r and b", "rhythm and blues", "soul", "neo soul", "neosoul", "funk", "motown", "quiet storm", "contemporary r&b", "contemporary rnb")),
    ("Rock", "Rock / Alternative / Indie", ("rock", "classic rock", "progressive rock", "prog rock", "psychedelic rock", "alternative", "alternative rock", "alt rock", "indie", "indie rock", "post-rock", "post rock", "garage rock", "soft rock", "hard rock")),
    ("Pop", "Pop", ("pop", "dance pop", "synth pop", "synthpop", "electropop", "electro pop", "indie pop", "art pop", "adult contemporary")),
    ("Country", "Country", ("country", "country music", "alt-country", "alt country", "country rock", "outlaw country")),
    ("Blues", "Blues", ("blues", "delta blues", "chicago blues", "electric blues", "acoustic blues")),
    ("Gospel", "Gospel", ("gospel", "christian gospel", "black gospel", "southern gospel", "worship", "praise and worship", "christian", "ccm")),
    ("Latin", "Latin / Caribbean", ("latin", "latin pop", "salsa", "bachata", "merengue", "cumbia", "reggaeton", "latin trap", "latin hip hop", "bossa nova", "samba", "mambo", "calypso", "soca", "kompa", "zouk")),
    ("Metal", "Metal", ("metal", "heavy metal", "black metal", "death metal", "thrash metal", "doom metal", "progressive metal", "prog metal", "metalcore", "nu metal")),
    ("Punk", "Punk", ("punk", "punk rock", "hardcore punk", "post-punk", "post punk", "pop punk", "emo", "ska punk")),
    ("Soundtrack", "Soundtrack / Score", ("soundtrack", "score", "film score", "movie score", "tv score", "television score", "original score", "ost", "game soundtrack", "video game music", "anime soundtrack", "musical", "show tunes")),
    ("World", "World / International", ("world", "world music", "international", "global", "traditional", "ethnic")),
    ("Spoken Word", "Spoken Word / Comedy", ("spoken word", "comedy", "stand-up", "stand up", "audio drama", "speech", "lecture", "interview")),
    ("Children's", "Children's", ("children", "children's", "kids", "kids music", "nursery rhyme", "lullaby")),
    ("Unknown", UNKNOWN_GENRE_FAMILY, ("unknown", "misc", "miscellaneous", "other", "uncategorized", "review needed")),
)


def normalize_genre_text(value: str | None) -> str | None:
    if value is None:
        return None
    text = str(value).strip().casefold()
    if not text:
        return None
    for old, new in {"_": " ", "-": " ", "/": " ", "\\": " ", ":": " ", "&": " and "}.items():
        text = text.replace(old, new)
    return " ".join(text.split()) or None


def _key(value: str | None) -> str:
    return normalize_genre_text(value) or ""


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
    return {**dict(embedded.get("technical") or {}), **dict(metadata.get("embedded_technical") or {})}


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


def _taxonomy_entries() -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    for canonical, family, aliases in GENRE_SEEDS:
        values = (canonical, family, *aliases)
        entries.append({
            "canonical_genre": canonical,
            "display_genre": canonical,
            "genre_family": family,
            "display_family": family,
            "aliases": tuple(dict.fromkeys(values)),
            "keys": {_key(value) for value in values if _key(value)},
        })
    return entries


TAXONOMY_ENTRIES = _taxonomy_entries()
FALLBACK_GENRE_MAP = {key: entry["display_family"] for entry in TAXONOMY_ENTRIES for key in entry["keys"]}


def seed_genre_taxonomy(db: Session) -> None:
    existing = {row.canonical_genre: row for row in db.query(GenreTaxonomy).all()}
    for entry in TAXONOMY_ENTRIES:
        canonical = entry["canonical_genre"]
        row = existing.get(canonical)
        if row is None:
            db.add(GenreTaxonomy(
                canonical_genre=canonical,
                display_genre=entry["display_genre"],
                genre_family=entry["genre_family"],
                display_family=entry["display_family"],
                aliases_json=list(entry["aliases"]),
                is_active=True,
            ))
            continue
        row.display_genre = entry["display_genre"]
        row.genre_family = entry["genre_family"]
        row.display_family = entry["display_family"]
        row.aliases_json = list(entry["aliases"])
        row.is_active = True
        row.updated_at = now_utc()


def _db_taxonomy_entries(db: Session | None) -> list[dict[str, Any]]:
    if db is None:
        return TAXONOMY_ENTRIES
    rows = db.query(GenreTaxonomy).filter(GenreTaxonomy.is_active.is_(True)).all()
    if not rows:
        return TAXONOMY_ENTRIES
    entries: list[dict[str, Any]] = []
    for row in rows:
        aliases = tuple(dict.fromkeys((
            row.canonical_genre,
            row.display_genre,
            row.genre_family,
            row.display_family,
            *(row.aliases_json or []),
        )))
        entries.append({
            "canonical_genre": row.canonical_genre,
            "display_genre": row.display_genre,
            "genre_family": row.genre_family,
            "display_family": row.display_family,
            "aliases": aliases,
            "keys": {_key(value) for value in aliases if _key(value)},
        })
    return entries


def _match_from_entries(value: str | None, entries: list[dict[str, Any]]) -> dict[str, Any] | None:
    normalized = normalize_genre_text(value)
    if not normalized:
        return None
    for entry in entries:
        if normalized == _key(entry["canonical_genre"]) or normalized == _key(entry["display_genre"]):
            return {**entry, "match_source": "exact"}
    for entry in entries:
        if normalized in entry["keys"]:
            return {**entry, "match_source": "alias"}
    return None


def _hint_match(hint: str | None, entries: list[dict[str, Any]]) -> dict[str, Any] | None:
    normalized = normalize_genre_text(hint)
    if not normalized:
        return None
    tokens = f" {normalized} "
    matches: list[tuple[int, dict[str, Any]]] = []
    for entry in entries:
        for key in entry["keys"]:
            if key and f" {key} " in tokens:
                matches.append((len(key), entry))
    if not matches:
        return None
    return max(matches, key=lambda item: item[0])[1]


def genre_taxonomy_match(
    value: str | None,
    *,
    path_hint: str | None = None,
    folder_hint: str | None = None,
    db: Session | None = None,
) -> dict[str, Any]:
    entries = _db_taxonomy_entries(db)
    raw_genre = _clean(value)
    normalized = normalize_genre_text(raw_genre)
    flags: list[str] = []
    direct = _match_from_entries(raw_genre, entries)
    folder = _hint_match(folder_hint, entries)
    path = _hint_match(path_hint, entries)
    hint = folder or path
    hint_source = "folder_hint" if folder else "path_hint" if path else None

    if direct is None:
        flags.append("unknown_genre" if not normalized or normalized in UNKNOWN_VALUES else "unmapped_genre")
        return {
            "raw_genre": raw_genre,
            "normalized_genre": normalized or "unknown",
            "primary_genre": "Unknown",
            "genre_family": UNKNOWN_GENRE_FAMILY,
            "confidence": "low",
            "match_source": "unknown",
            "review_flags": flags,
        }

    chosen = direct
    match_source = direct["match_source"]
    confidence = "high"
    if direct["display_family"] in BROAD_GENRE_FAMILIES:
        flags.append("possible_broad_genre")
        confidence = "low"
        if hint is not None and hint["display_family"] not in BROAD_GENRE_FAMILIES:
            chosen = hint
            match_source = hint_source or "path_hint"
            confidence = "medium"
    if chosen["display_family"] == UNKNOWN_GENRE_FAMILY:
        flags.append("unknown_genre")
        confidence = "low"
    return {
        "raw_genre": raw_genre,
        "normalized_genre": normalized or "unknown",
        "primary_genre": chosen["display_genre"],
        "genre_family": chosen["display_family"],
        "confidence": confidence,
        "match_source": match_source,
        "review_flags": list(dict.fromkeys(flags)),
    }


def genre_family_for(
    value: str | None,
    db: Session | None = None,
    *,
    path_hint: str | None = None,
    folder_hint: str | None = None,
) -> str:
    return genre_taxonomy_match(value, path_hint=path_hint, folder_hint=folder_hint, db=db)["genre_family"]


def _find_media_file(db: Session, ingest_file: IngestFile) -> MediaFile | None:
    if ingest_file.id is not None:
        row = db.query(MediaFile).filter(MediaFile.ingest_file_id == ingest_file.id).one_or_none()
        if row is not None:
            return row
    if ingest_file.checksum:
        row = db.query(MediaFile).filter(MediaFile.checksum == ingest_file.checksum, MediaFile.absolute_path == ingest_file.file_path).one_or_none()
        if row is not None:
            return row
    return db.query(MediaFile).filter(MediaFile.absolute_path == ingest_file.file_path).one_or_none()


def _raw_tag_for(db: Session, media_file: MediaFile) -> RawMediaTag | None:
    return db.query(RawMediaTag).filter(RawMediaTag.media_file_id == media_file.id, RawMediaTag.tag_source == "mutagen").one_or_none()


def _profile_for(db: Session, media_file: MediaFile) -> NormalizedMusicProfile | None:
    return db.query(NormalizedMusicProfile).filter(NormalizedMusicProfile.media_file_id == media_file.id).one_or_none()


def _detect_mojibake(value: str | None) -> bool:
    text = value or ""
    return any(pattern in text for pattern in MOJIBAKE_PATTERNS)


def _flag_exists(db: Session, *, media_file: MediaFile, batch: IngestBatch | None, flag_type: str, message: str) -> bool:
    return db.query(MetadataReviewFlag).filter(
        MetadataReviewFlag.media_file_id == media_file.id,
        MetadataReviewFlag.ingest_batch_id == (batch.id if batch else None),
        MetadataReviewFlag.flag_type == flag_type,
        MetadataReviewFlag.message == message,
        MetadataReviewFlag.status == "open",
    ).first() is not None


def _add_flag(
    db: Session,
    *,
    media_file: MediaFile,
    batch: IngestBatch | None,
    flag_type: str,
    field_name: str | None,
    raw_value: str | None,
    normalized_value: str | None,
    message: str,
) -> int:
    if _flag_exists(db, media_file=media_file, batch=batch, flag_type=flag_type, message=message):
        return 0
    db.add(MetadataReviewFlag(
        media_file_id=media_file.id,
        ingest_batch_id=batch.id if batch else None,
        flag_type=flag_type,
        severity=FLAG_SEVERITY.get(flag_type, "warning"),
        field_name=field_name,
        raw_value=raw_value,
        normalized_value=normalized_value,
        message=message,
        status="open",
    ))
    return 1


def _profile_values(metadata: dict[str, Any], db: Session, *, ingest_file: IngestFile | None = None, batch: IngestBatch | None = None) -> dict[str, Any]:
    artist = _metadata_value(metadata, "artist", "trackartist")
    album_artist = _metadata_value(metadata, "album_artist", "albumartist", "album artist")
    album = _metadata_value(metadata, "album")
    title = _metadata_value(metadata, "title")
    raw_genre = _metadata_value(metadata, "genre", "primary_genre")
    genre_match = genre_taxonomy_match(
        raw_genre,
        path_hint=ingest_file.file_path if ingest_file else None,
        folder_hint=batch.source_path if batch else None,
        db=db,
    )
    return {
        "artist": artist,
        "album_artist": album_artist,
        "album": album,
        "title": title,
        "track_number": _metadata_value(metadata, "tracknumber", "track_number"),
        "disc_number": _metadata_value(metadata, "discnumber", "disc_number"),
        "year": _metadata_value(metadata, "date", "year", "original_date"),
        "release_type": _metadata_value(metadata, "release_type"),
        "primary_genre": genre_match["primary_genre"],
        "genre_family": genre_match["genre_family"],
        "genre_match": genre_match,
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
        "metadata_source": _metadata_value(metadata, "metadata_source") or f"genre:{genre_match['match_source']}",
        "approved": bool(metadata.get("approved") or metadata.get("review_confirmed")),
    }


def _detect_flags(db: Session, *, media_file: MediaFile, batch: IngestBatch | None, values: dict[str, Any]) -> int:
    created = 0
    missing_fields = {
        "artist": "missing_artist",
        "album_artist": "missing_album_artist",
        "album": "missing_album",
        "title": "missing_title",
        "track_number": "missing_track_number",
    }
    for field, flag_type in missing_fields.items():
        if _is_unknown(values.get(field)):
            created += _add_flag(
                db,
                media_file=media_file,
                batch=batch,
                flag_type=flag_type,
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
                field_name=field,
                raw_value=raw,
                normalized_value=raw,
                message="Possible mojibake detected. Detection only; value was not changed.",
            )
    genre_match = values.get("genre_match") or {}
    for flag_type in genre_match.get("review_flags") or []:
        created += _add_flag(
            db,
            media_file=media_file,
            batch=batch,
            flag_type=flag_type,
            field_name="primary_genre",
            raw_value=genre_match.get("raw_genre"),
            normalized_value=genre_match.get("genre_family"),
            message=f"Genre review flag: {flag_type}.",
        )
    if values.get("genre_family") == "Classical":
        composer_missing = _is_unknown(values.get("composer"))
        performer_missing = all(_is_unknown(values.get(field)) for field in ("artist", "album_artist", "conductor", "orchestra", "ensemble", "soloist"))
        work_missing = _is_unknown(values.get("work")) and _is_unknown(values.get("movement"))
        if composer_missing:
            created += _add_flag(db, media_file=media_file, batch=batch, flag_type="missing_composer", field_name="composer", raw_value=_clean(values.get("composer")), normalized_value=None, message="Classical item is missing composer metadata.")
        if performer_missing:
            created += _add_flag(db, media_file=media_file, batch=batch, flag_type="missing_performer_or_ensemble", field_name="artist", raw_value=_clean(values.get("artist")), normalized_value=None, message="Classical item is missing performer, ensemble, or orchestra metadata.")
        if work_missing:
            created += _add_flag(db, media_file=media_file, batch=batch, flag_type="missing_work_or_movement", field_name="work", raw_value=_clean(values.get("work")), normalized_value=None, message="Classical item is missing work or movement metadata.")
        if composer_missing and performer_missing:
            created += _add_flag(db, media_file=media_file, batch=batch, flag_type="classical_metadata_incomplete", field_name="composer", raw_value=_clean(values.get("composer")), normalized_value=None, message="Classical item is missing composer and performer/album artist metadata.")
    return created


def snapshot_ingest_file_metadata(db: Session, ingest_file: IngestFile, batch: IngestBatch | None = None) -> MediaFile | None:
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

    values = _profile_values(metadata, db, ingest_file=ingest_file, batch=batch)
    profile = _profile_for(db, media_file)
    if profile is None:
        profile = NormalizedMusicProfile(media_file_id=media_file.id)
        db.add(profile)
    for key, value in values.items():
        if key != "genre_match":
            setattr(profile, key, value)
    profile.updated_at = now

    db.flush()
    _detect_flags(db, media_file=media_file, batch=batch, values=values)
    from app.services.metadata_quality_gate import snapshot_or_update_quality_decision
    snapshot_or_update_quality_decision(db, media_file.id)
    return media_file


def snapshot_batch_metadata(db: Session, batch: IngestBatch) -> dict:
    files = list(batch.files) or db.query(IngestFile).filter(IngestFile.batch_id == batch.id).all()
    media_files = 0
    raw_tags = 0
    profiles = 0
    flags_before = db.query(MetadataReviewFlag).filter(or_(MetadataReviewFlag.ingest_batch_id == batch.id, MetadataReviewFlag.ingest_batch_id.is_(None))).count()
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
    flags_after = db.query(MetadataReviewFlag).filter(or_(MetadataReviewFlag.ingest_batch_id == batch.id, MetadataReviewFlag.ingest_batch_id.is_(None))).count()
    return {
        "media_files": media_files,
        "raw_tags": raw_tags,
        "normalized_profiles": profiles,
        "flags": max(flags_after - flags_before, 0),
    }


def unmapped_genre_rows(db: Session) -> list[dict[str, Any]]:
    rows = db.query(NormalizedMusicProfile).filter(NormalizedMusicProfile.primary_genre.isnot(None)).all()
    grouped: dict[str, dict[str, Any]] = {}
    for profile in rows:
        raw = profile.primary_genre or "Unknown"
        match = genre_taxonomy_match(raw, db=db)
        flags = set(match.get("review_flags") or [])
        if profile.genre_family == UNKNOWN_GENRE_FAMILY:
            flags.add("unmapped_genre" if raw and _key(raw) not in UNKNOWN_VALUES else "unknown_genre")
        if profile.genre_family in BROAD_GENRE_FAMILIES:
            flags.add("possible_broad_genre")
        if not flags.intersection({"unknown_genre", "unmapped_genre", "possible_broad_genre"}):
            continue
        key = normalize_genre_text(raw) or "unknown"
        item = grouped.setdefault(key, {
            "raw_genre": raw,
            "normalized_genre": key,
            "count": 0,
            "genre_family": profile.genre_family or match["genre_family"],
            "review_flags": sorted(flags),
            "examples": [],
        })
        item["count"] += 1
        item["review_flags"] = sorted(set(item["review_flags"]) | flags)
        if len(item["examples"]) < 3:
            item["examples"].append({"artist": profile.artist, "album": profile.album, "title": profile.title})
    return sorted(grouped.values(), key=lambda item: (-item["count"], item["normalized_genre"]))
