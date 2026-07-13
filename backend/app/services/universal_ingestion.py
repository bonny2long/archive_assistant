from __future__ import annotations

import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path, PureWindowsPath
from typing import Any

from sqlalchemy.orm import Session

from app.models.archive import IngestBatch, IngestFile
from app.models.media_metadata import (
    CandidateMember,
    FragmentReconstructionDecision,
    MediaFile,
    MediaIdentityCandidate,
    MixedMediaFlag,
    SourceFragment,
)
from app.services.music_metadata import (
    parse_discography_parent_folder,
    parse_music_folder_name,
    resolved_music_track_evidence,
)

PHASE_NAME = "AA-M4D.1 — Universal Media Ingestion Boundary + Fragment Reconstruction"

AUDIO_EXTENSIONS = {".mp3", ".flac", ".m4a", ".wav", ".ogg", ".opus", ".aac", ".aiff"}
AUDIOBOOK_EXTENSIONS = {".m4b"}
EBOOK_EXTENSIONS = {".epub", ".pdf", ".mobi", ".azw", ".azw3"}
COMIC_EXTENSIONS = {".cbz", ".cbr", ".cb7", ".cbt"}
VIDEO_EXTENSIONS = {".mkv", ".mp4", ".avi", ".mov", ".m4v", ".wmv"}
SUBTITLE_EXTENSIONS = {".srt", ".ass", ".ssa", ".vtt", ".sub"}
ARTWORK_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".gif"}
SIDECAR_EXTENSIONS = {".nfo", ".cue", ".log", ".txt", ".json", ".xml"}
PLAYLIST_EXTENSIONS = {".m3u", ".m3u8", ".pls"}
ARCHIVE_EXTENSIONS = {".zip", ".rar", ".7z", ".tar", ".gz"}
PRIMARY_MEDIA_CLASSES = {"music_audio", "audiobook_audio", "ebook", "comic", "movie", "tv_episode", "video_extra"}
SUPPORT_MEDIA_CLASSES = {"subtitle", "artwork", "sidecar_metadata", "playlist"}

FRAGMENT_PATTERNS = [
    re.compile(r"^(?P<prefix>drive-download-.+?-\d+)-(?P<index>\d{3})$", re.IGNORECASE),
    re.compile(r"^(?P<prefix>.*?)[\s._-]*(?:part|pt)[\s._-]*(?P<index>\d+)$", re.IGNORECASE),
    re.compile(r"^(?P<prefix>.*?)[\s._-]*(?:cd|disc|disk|vol|volume)[\s._-]*(?P<index>\d+)$", re.IGNORECASE),
    re.compile(r"^(?P<prefix>.+?)-(?P<index>\d{3})$", re.IGNORECASE),
]
SXXEYY_RE = re.compile(r"\bS(?P<season>\d{1,2})E(?P<episode>\d{1,3})\b", re.IGNORECASE)
YEAR_RE = re.compile(r"\b(19\d{2}|20\d{2})\b")
TRACK_RE = re.compile(r"(?:^|\D)(?P<track>\d+)(?:\D|$)")
DISC_FOLDER_RE = re.compile(r"^(?:cd|disc|disk|part)\s*0*\d+\b", re.IGNORECASE)


@dataclass
class ClassifiedFile:
    ingest_file: IngestFile
    relative_path: str
    fragment_path: str
    media_class: str
    evidence: dict[str, Any] = field(default_factory=dict)


@dataclass
class CandidateDraft:
    key: str
    media_type: str
    title: str | None = None
    primary_creator: str | None = None
    secondary_creator: str | None = None
    year: str | None = None
    series: str | None = None
    series_index: str | None = None
    release_type: str | None = None
    confidence: float = 0.55
    evidence: dict[str, Any] = field(default_factory=dict)
    members: list[ClassifiedFile] = field(default_factory=list)
    support_members: list[ClassifiedFile] = field(default_factory=list)
    flags: set[str] = field(default_factory=set)
    reasons: list[str] = field(default_factory=list)


def _norm(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _key_part(value: Any) -> str:
    text = _norm(value) or "unknown"
    text = re.sub(r"\s+", " ", text.casefold())
    return re.sub(r"[^a-z0-9]+", "-", text).strip("-") or "unknown"


def _path_parts(path: str) -> list[str]:
    return [part for part in path.replace("\\", "/").split("/") if part]


def _discography_release_folder(ingest_file: IngestFile) -> tuple[str | None, str | None]:
    """Return the real release folder beneath a stored discography container.

    Older split metadata sometimes stored the outer discography directory as the
    release source for every file. The physical file path remains authoritative
    evidence for grouping, including files collected from several drive chunks.
    """
    metadata = ingest_file.metadata_json or {}
    album_metadata = metadata.get("_discography_album")
    if not isinstance(album_metadata, dict):
        return None, None
    container = str(album_metadata.get("source_folder") or "").strip()
    if not container:
        return None, None
    parts = _path_parts(str(ingest_file.file_path))
    matches = [
        index
        for index, part in enumerate(parts[:-1])
        if part.casefold() == container.casefold()
    ]
    if not matches:
        physical_parent = parts[-2] if len(parts) > 1 else None
        if physical_parent and not DISC_FOLDER_RE.match(physical_parent):
            return physical_parent, container
        return container, container
    index = matches[-1]
    nested = parts[index + 1] if index + 1 < len(parts) - 1 else None
    if not nested or DISC_FOLDER_RE.match(nested):
        return container, container
    return nested, container


def relative_path_for(batch: IngestBatch, ingest_file: IngestFile) -> str:
    file_path = Path(str(ingest_file.file_path))
    try:
        return file_path.relative_to(Path(str(batch.source_path))).as_posix()
    except Exception:
        raw = str(ingest_file.file_path).replace("\\", "/")
        source = str(batch.source_path).replace("\\", "/").rstrip("/")
        if raw.startswith(source + "/"):
            return raw[len(source) + 1:]
        parts = PureWindowsPath(str(ingest_file.file_path)).parts
        return "/".join(parts[-2:]) if len(parts) > 1 else ingest_file.file_name


def _metadata_fields(ingest_file: IngestFile) -> dict[str, Any]:
    metadata = ingest_file.metadata_json or {}
    fields: dict[str, Any] = {}
    sources = [metadata]
    if isinstance(metadata.get("embedded_metadata_fields"), dict):
        sources.append(metadata["embedded_metadata_fields"])
    embedded = metadata.get("embedded_metadata")
    if isinstance(embedded, dict) and isinstance(embedded.get("fields"), dict):
        sources.append(embedded["fields"])
    for source in sources:
        fields.update({key: value for key, value in source.items() if value not in (None, "")})
    return fields


def _field(fields: dict[str, Any], *names: str) -> str | None:
    for name in names:
        value = _norm(fields.get(name))
        if value:
            return value
    return None


def _path_has(relative_path: str, *needles: str) -> bool:
    lower = relative_path.casefold()
    return any(needle in lower for needle in needles)

def classify_media_file(ingest_file: IngestFile, relative_path: str | None = None) -> tuple[str, dict[str, Any]]:
    rel = relative_path or ingest_file.file_name
    extension = (ingest_file.extension or Path(ingest_file.file_name).suffix).casefold()
    name = Path(ingest_file.file_name).stem.casefold()
    evidence: dict[str, Any] = {"extension": extension}
    stored_role = str(ingest_file.detected_role or "").casefold()
    if (
        stored_role in {"audiobook_audio", "audiobook_track", "audiobook_chapter"}
        and extension in AUDIO_EXTENSIONS | AUDIOBOOK_EXTENSIONS
    ):
        evidence["manual_or_scoped_audiobook_role"] = True
        return "audiobook_audio", evidence
    if extension in AUDIOBOOK_EXTENSIONS:
        evidence["audiobook_extension"] = True
        return "audiobook_audio", evidence
    if extension in AUDIO_EXTENSIONS:
        if _path_has(rel, "audiobook", "audio book", "narrator", "chapter"):
            evidence["audiobook_path_clue"] = True
            return "audiobook_audio", evidence
        return "music_audio", evidence
    if extension in COMIC_EXTENSIONS:
        return "comic", evidence
    if extension in EBOOK_EXTENSIONS:
        if extension == ".pdf":
            if _path_has(rel, "comic", "comics", "manga"):
                evidence["pdf_comic_path_clue"] = True
                return "comic", evidence
            evidence["ambiguous_pdf_role"] = True
        return "ebook", evidence
    if extension in VIDEO_EXTENSIONS:
        if SXXEYY_RE.search(rel):
            evidence["sxxeyy_pattern"] = True
            return "tv_episode", evidence
        if any(token in name for token in ("extra", "extras", "trailer", "sample", "featurette")):
            evidence["extra_filename_clue"] = True
            return "video_extra", evidence
        if not YEAR_RE.search(rel):
            evidence["movie_tv_ambiguous"] = True
        return "movie", evidence
    if extension in SUBTITLE_EXTENSIONS:
        return "subtitle", evidence
    if extension in ARTWORK_EXTENSIONS:
        return "artwork", evidence
    if extension in SIDECAR_EXTENSIONS:
        return "sidecar_metadata", evidence
    if extension in PLAYLIST_EXTENSIONS:
        return "playlist", evidence
    if extension in ARCHIVE_EXTENSIONS:
        return "archive_file", evidence
    return "unknown", evidence


def _fragment_info(relative_path: str) -> tuple[str, str | None, str | None, int | None]:
    parts = _path_parts(relative_path)
    if len(parts) <= 1:
        return ".", None, None, None
    fragment_path = parts[0]
    label = parts[0]
    for pattern in FRAGMENT_PATTERNS:
        match = pattern.match(label)
        if match:
            prefix = (match.group("prefix") or "").strip(" ._-") or "source"
            parent = "/".join(parts[:-2]) if len(parts) > 2 else ""
            group_key = "/".join(part for part in [parent, _key_part(prefix)] if part)
            return fragment_path, group_key, label, int(match.group("index"))
    if len(parts) > 2:
        nested_label = parts[-2]
        for pattern in FRAGMENT_PATTERNS[1:]:
            match = pattern.match(nested_label)
            if match:
                parent = "/".join(parts[:-2])
                group_key = "/".join(part for part in [parent, _key_part(match.group("prefix") or "fragment")] if part)
                return "/".join(parts[:-1]), group_key, nested_label, int(match.group("index"))
    return fragment_path, None, label, None


def classify_batch_files(batch: IngestBatch) -> list[ClassifiedFile]:
    classified: list[ClassifiedFile] = []
    for ingest_file in batch.files:
        rel = relative_path_for(batch, ingest_file)
        fragment_path, group_key, label, index = _fragment_info(rel)
        media_class, evidence = classify_media_file(ingest_file, rel)
        if media_class == "music_audio":
            release_folder, discography_folder = _discography_release_folder(ingest_file)
            review_origin = str((batch.metadata_json or {}).get("review_origin") or "")
            if not release_folder and review_origin in {
                "multi_artist_discography_split",
                "approved_candidate_materialization",
            }:
                path_parts = _path_parts(str(ingest_file.file_path))
                physical_parent = path_parts[-2] if len(path_parts) > 1 else None
                if physical_parent and not DISC_FOLDER_RE.match(physical_parent):
                    release_folder = physical_parent
                    discography_folder = path_parts[-3] if len(path_parts) > 2 else None
            if release_folder:
                evidence["release_source_folder"] = release_folder
                evidence["discography_source_folder"] = discography_folder
        if group_key:
            evidence["fragment_group_key"] = group_key
            evidence["fragment_label"] = label
            evidence["fragment_index"] = index
        classified.append(ClassifiedFile(ingest_file, rel, fragment_path, media_class, evidence))
    return classified


def _track_number(value: str | None) -> str | None:
    if not value:
        return None
    match = TRACK_RE.search(value)
    return str(int(match.group("track"))) if match else None


def _music_candidate_key(item: ClassifiedFile) -> tuple[str, dict[str, Any]]:
    fields = _metadata_fields(item.ingest_file)
    release_folder = _norm(item.evidence.get("release_source_folder"))
    discography_folder = _norm(item.evidence.get("discography_source_folder"))
    folder = parse_music_folder_name(release_folder) if release_folder else {}
    folder_artist = _norm(folder.get("artist")) if folder else None
    if folder_artist and YEAR_RE.fullmatch(folder_artist):
        folder_artist = None
    parent_artist = (
        _norm(parse_discography_parent_folder(discography_folder).get("artist"))
        if (
            discography_folder
            and _key_part(discography_folder) != _key_part(release_folder)
        )
        else None
    )
    artist = (
        folder_artist
        or parent_artist
        or _field(fields, "album_artist", "albumartist", "artist")
    )
    album = (_norm(folder.get("album")) if folder else None) or _field(
        fields, "album", "release",
    )
    year = _norm(folder.get("year")) if folder else None
    if release_folder:
        key = (
            f"music:source:{_key_part(discography_folder)}:"
            f"{_key_part(release_folder)}"
        )
        confidence = 0.92
    elif artist and album:
        key = f"music:{_key_part(artist)}:{_key_part(album)}"
        confidence = 0.88
    else:
        parts = _path_parts(item.relative_path)
        group = item.evidence.get("fragment_group_key") or (parts[0] if parts else "loose-audio")
        key = f"music:custom:{_key_part(group)}"
        confidence = 0.45
    track_evidence = resolved_music_track_evidence(item.ingest_file.metadata_json, item.ingest_file.file_name)
    return key, {
        "artist": artist,
        "album": album,
        "year": year or _field(fields, "date", "year"),
        "title": _field(fields, "title"),
        "track_number": track_evidence.get("resolved_track"),
        "disc_number": track_evidence.get("disc"),
        "track_number_source": track_evidence.get("preferred_source"),
        "release_type": _field(fields, "release_type"),
        "source_folder": release_folder,
        "discography_source_folder": discography_folder,
        "confidence": confidence,
    }


def _audiobook_candidate_key(item: ClassifiedFile) -> tuple[str, dict[str, Any]]:
    fields = _metadata_fields(item.ingest_file)
    author = _field(fields, "author", "album_artist", "albumartist", "artist", "composer")
    title = _field(fields, "album", "title")
    if author and title:
        key = f"audiobook:{_key_part(author)}:{_key_part(title)}"
        confidence = 0.82
    else:
        parts = _path_parts(item.relative_path)
        folder = parts[-2] if len(parts) > 1 else Path(item.ingest_file.file_name).stem
        key = f"audiobook:custom:{_key_part(folder)}"
        confidence = 0.48
    return key, {
        "author": author,
        "title": title,
        "series": _field(fields, "series"),
        "series_index": _field(fields, "series_index"),
        "narrator": _field(fields, "narrator"),
        "chapter_number": _field(fields, "chapter", "track_number", "tracknumber"),
        "disc_number": _field(fields, "disc_number", "discnumber"),
        "confidence": confidence,
    }


def _bookish_candidate_key(item: ClassifiedFile, media_type: str) -> tuple[str, dict[str, Any]]:
    fields = _metadata_fields(item.ingest_file)
    title = _field(fields, "title") or re.sub(r"[._-]+", " ", Path(item.ingest_file.file_name).stem).strip()
    author = _field(fields, "author", "creator", "artist")
    key = f"{media_type}:{_key_part(author)}:{_key_part(title)}"
    return key, {
        "author": author,
        "title": title,
        "series": _field(fields, "series"),
        "series_index": _field(fields, "series_index", "issue", "volume"),
        "confidence": 0.72 if author else 0.58,
    }


def _video_candidate_key(item: ClassifiedFile, media_type: str) -> tuple[str, dict[str, Any]]:
    stem = re.sub(r"[._-]+", " ", Path(item.ingest_file.file_name).stem).strip()
    sxxeyy = SXXEYY_RE.search(item.relative_path)
    year = YEAR_RE.search(item.relative_path)
    if media_type == "tv_episode" and sxxeyy:
        show = _path_parts(item.relative_path)[0] if _path_parts(item.relative_path) else "Unknown Show"
        key = f"tv:{_key_part(show)}:s{sxxeyy.group('season')}:e{sxxeyy.group('episode')}"
        return key, {"show": show, "title": stem, "season": sxxeyy.group("season"), "episode": sxxeyy.group("episode"), "confidence": 0.84}
    title = YEAR_RE.sub("", stem).strip(" -._") or stem
    key = f"movie:{_key_part(title)}:{year.group(1) if year else 'unknown'}"
    return key, {"title": title, "year": year.group(1) if year else None, "confidence": 0.76 if year else 0.5}

def _sort_key(item: ClassifiedFile) -> str:
    if item.media_class == "music_audio":
        evidence = resolved_music_track_evidence(item.ingest_file.metadata_json, item.ingest_file.file_name)
        disc = int(evidence.get("disc") or 1)
        track = int(evidence.get("resolved_track") or 1_000_000)
        return f"{disc:04d}:{track:08d}:{item.relative_path}"
    fields = _metadata_fields(item.ingest_file)
    disc = _field(fields, "disc_number", "discnumber") or "0"
    track = _field(fields, "track_number", "tracknumber") or _field(fields, "chapter") or "0"
    return f"{disc}:{track}:{item.relative_path}"


def build_candidate_drafts(classified: list[ClassifiedFile]) -> dict[str, CandidateDraft]:
    candidates: dict[str, CandidateDraft] = {}
    support: list[ClassifiedFile] = []
    for item in classified:
        if item.media_class in SUPPORT_MEDIA_CLASSES:
            support.append(item)
            continue
        if item.media_class not in PRIMARY_MEDIA_CLASSES:
            continue
        if item.media_class == "music_audio":
            key, evidence = _music_candidate_key(item)
            media_type, title, creator = "music", evidence.get("album"), evidence.get("artist")
        elif item.media_class == "audiobook_audio":
            key, evidence = _audiobook_candidate_key(item)
            media_type, title, creator = "audiobook", evidence.get("title"), evidence.get("author")
        elif item.media_class == "ebook":
            key, evidence = _bookish_candidate_key(item, "ebook")
            media_type, title, creator = "ebook", evidence.get("title"), evidence.get("author")
        elif item.media_class == "comic":
            key, evidence = _bookish_candidate_key(item, "comic")
            media_type, title, creator = "comic", evidence.get("title"), evidence.get("author")
        elif item.media_class in {"movie", "video_extra"}:
            key, evidence = _video_candidate_key(item, "movie")
            media_type, title, creator = "movie", evidence.get("title"), None
        else:
            key, evidence = _video_candidate_key(item, "tv_episode")
            media_type, title, creator = "tv", evidence.get("show"), None
        draft = candidates.setdefault(key, CandidateDraft(
            key=key,
            media_type=media_type,
            title=_norm(title),
            primary_creator=_norm(creator),
            secondary_creator=_norm(evidence.get("narrator")),
            year=_norm(evidence.get("year")),
            series=_norm(evidence.get("series")),
            series_index=_norm(evidence.get("series_index")),
            release_type=_norm(evidence.get("release_type")),
            confidence=float(evidence.get("confidence") or 0.55),
            evidence={
                "phase": PHASE_NAME,
                "identity": evidence,
                **(
                    {"source_folder": str(evidence["source_folder"])}
                    if evidence.get("source_folder")
                    else {}
                ),
            },
        ))
        draft.members.append(item)
        if item.evidence.get("ambiguous_pdf_role"):
            draft.flags.add("ambiguous_pdf_role")
            draft.reasons.append("PDF role is ambiguous without stronger folder or metadata evidence")
        if item.evidence.get("movie_tv_ambiguous"):
            draft.flags.add("movie_tv_ambiguous")
            draft.reasons.append("Video file lacks TV episode or movie-year evidence")
        if draft.confidence < 0.55 and item.media_class in {"music_audio", "audiobook_audio"}:
            draft.flags.add("custom_media_low_metadata")
            draft.reasons.append("Audio identity has low embedded metadata evidence")
    _attach_support_members(candidates, support)
    _detect_track_conflicts(candidates.values())
    return candidates


def _attach_support_members(candidates: dict[str, CandidateDraft], support_items: list[ClassifiedFile]) -> None:
    for item in support_items:
        same_fragment = [candidate for candidate in candidates.values() if any(member.fragment_path == item.fragment_path for member in candidate.members)]
        same_stem = [
            candidate for candidate in candidates.values()
            if any(Path(member.ingest_file.file_name).stem.casefold() == Path(item.ingest_file.file_name).stem.casefold() for member in candidate.members)
        ]
        target = same_stem[0] if len(same_stem) == 1 else same_fragment[0] if len(same_fragment) == 1 else None
        if target:
            target.support_members.append(item)
            continue
        if item.media_class == "artwork":
            for candidate in same_fragment or candidates.values():
                candidate.flags.add("artwork_without_owner")
                candidate.reasons.append("Artwork ownership is unclear")
        elif item.media_class in {"subtitle", "sidecar_metadata"}:
            for candidate in same_fragment or candidates.values():
                candidate.flags.add("sidecar_without_owner")
                candidate.reasons.append("Sidecar ownership is unclear")


def _detect_track_conflicts(candidates: Any) -> None:
    for candidate in candidates:
        if candidate.media_type not in {"music", "audiobook"}:
            continue
        seen: dict[tuple[str, str], ClassifiedFile] = {}
        track_counts: Counter[str] = Counter()
        disc_values: set[str] = set()
        for member in candidate.members:
            fields = _metadata_fields(member.ingest_file)
            if candidate.media_type == "music":
                evidence = resolved_music_track_evidence(member.ingest_file.metadata_json, member.ingest_file.file_name)
                track = _track_number(str(evidence.get("resolved_track") or ""))
                disc = _track_number(str(evidence.get("disc") or "1"))
            else:
                track = _track_number(_field(fields, "track_number", "tracknumber", "chapter"))
                disc = _track_number(_field(fields, "disc_number", "discnumber"))
            if disc:
                disc_values.add(disc)
            if track:
                track_counts[track] += 1
                key = (disc or "", track)
                if key in seen:
                    candidate.flags.add("track_number_conflict" if candidate.media_type == "music" else "duplicate_chapter_identity")
                    candidate.reasons.append("Duplicate track/chapter number evidence within one candidate")
                seen[key] = member
        if any(count > 1 for count in track_counts.values()) and not disc_values and len(candidate.members) > 1:
            candidate.flags.add("disc_number_missing")
            candidate.flags.add("track_number_conflict" if candidate.media_type == "music" else "duplicate_chapter_identity")
            candidate.reasons.append("Repeated track/chapter numbers need disc or part evidence")


def _delete_existing_snapshot(db: Session, batch_id: int) -> None:
    db.query(MixedMediaFlag).filter(MixedMediaFlag.batch_id == batch_id).delete(synchronize_session=False)
    db.query(FragmentReconstructionDecision).filter(FragmentReconstructionDecision.batch_id == batch_id).delete(synchronize_session=False)
    candidate_ids = [row.id for row in db.query(MediaIdentityCandidate.id).filter(MediaIdentityCandidate.batch_id == batch_id).all()]
    if candidate_ids:
        db.query(CandidateMember).filter(CandidateMember.candidate_id.in_(candidate_ids)).delete(synchronize_session=False)
    db.query(MediaIdentityCandidate).filter(MediaIdentityCandidate.batch_id == batch_id).delete(synchronize_session=False)
    db.query(SourceFragment).filter(SourceFragment.batch_id == batch_id).delete(synchronize_session=False)


def _media_file_id_for(db: Session, ingest_file_id: int | None) -> int | None:
    if ingest_file_id is None:
        return None
    row = db.query(MediaFile.id).filter(MediaFile.ingest_file_id == ingest_file_id).one_or_none()
    return row[0] if row else None

def snapshot_universal_ingestion_boundary(db: Session, batch: IngestBatch) -> dict[str, Any]:
    """Persist AA-M4D.1 source fragments, candidates, decisions, and flags for a batch."""
    _delete_existing_snapshot(db, batch.id)
    classified = classify_batch_files(batch)
    fragments = _persist_fragments(db, batch, classified)
    candidates = build_candidate_drafts(classified)
    candidate_rows = _persist_candidates(db, batch, candidates)
    decisions = _persist_decisions_and_flags(db, batch, candidates, candidate_rows, fragments, classified)
    db.flush()
    return {
        "phase": PHASE_NAME,
        "batch_id": batch.id,
        "source_fragments": len(fragments),
        "media_identity_candidates": len(candidates),
        "reconstruction_decisions": len(decisions),
        "mixed_media_flags": db.query(MixedMediaFlag).filter(MixedMediaFlag.batch_id == batch.id).count(),
        "media_class_counts": dict(Counter(item.media_class for item in classified)),
    }


def _persist_fragments(db: Session, batch: IngestBatch, classified: list[ClassifiedFile]) -> dict[str, SourceFragment]:
    by_fragment: dict[str, list[ClassifiedFile]] = defaultdict(list)
    for item in classified:
        by_fragment[item.fragment_path].append(item)
    group_fragment_counts: dict[str, int] = defaultdict(int)
    for items in by_fragment.values():
        for key in {item.evidence.get("fragment_group_key") for item in items if item.evidence.get("fragment_group_key")}:
            group_fragment_counts[str(key)] += 1
    rows: dict[str, SourceFragment] = {}
    for fragment_path, items in sorted(by_fragment.items()):
        first = items[0]
        group_key = _norm(first.evidence.get("fragment_group_key"))
        row = SourceFragment(
            batch_id=batch.id,
            source_root=str(batch.source_path),
            relative_fragment_path=fragment_path,
            fragment_group_key=group_key,
            fragment_label=_norm(first.evidence.get("fragment_label")) or fragment_path,
            fragment_index=first.evidence.get("fragment_index") if isinstance(first.evidence.get("fragment_index"), int) else None,
            fragment_count=group_fragment_counts.get(group_key or "") or None,
            file_count=len(items),
            media_class_counts_json=dict(Counter(item.media_class for item in items)),
        )
        db.add(row)
        rows[fragment_path] = row
    db.flush()
    return rows


def _persist_candidates(db: Session, batch: IngestBatch, candidates: dict[str, CandidateDraft]) -> dict[str, MediaIdentityCandidate]:
    rows: dict[str, MediaIdentityCandidate] = {}
    for draft in sorted(candidates.values(), key=lambda item: item.key):
        row = MediaIdentityCandidate(
            batch_id=batch.id,
            candidate_key=draft.key,
            candidate_media_type=draft.media_type,
            candidate_title=draft.title,
            candidate_primary_creator=draft.primary_creator,
            candidate_secondary_creator=draft.secondary_creator,
            candidate_year=draft.year,
            candidate_series=draft.series,
            candidate_series_index=draft.series_index,
            candidate_release_type=draft.release_type,
            candidate_confidence=draft.confidence,
            identity_evidence_json={
                **draft.evidence,
                "flags": sorted(draft.flags),
                "member_count": len(draft.members),
                "support_member_count": len(draft.support_members),
            },
        )
        db.add(row)
        db.flush()
        rows[draft.key] = row
        for member in draft.members + draft.support_members:
            db.add(CandidateMember(
                candidate_id=row.id,
                media_file_id=_media_file_id_for(db, getattr(member.ingest_file, "id", None)),
                batch_file_id=getattr(member.ingest_file, "id", None),
                relative_path=member.relative_path,
                media_class=member.media_class,
                role_in_candidate="support" if member in draft.support_members else "primary",
                sort_key=_sort_key(member),
                evidence_json=member.evidence,
            ))
    db.flush()
    return rows


def _persist_flag(
    db: Session,
    batch_id: int,
    flag_type: str,
    message: str,
    *,
    severity: str = "warning",
    source_fragment_id: int | None = None,
    candidate_id: int | None = None,
    examples: list[str] | None = None,
) -> None:
    db.add(MixedMediaFlag(
        batch_id=batch_id,
        source_fragment_id=source_fragment_id,
        candidate_id=candidate_id,
        flag_type=flag_type,
        severity=severity,
        message=message,
        examples_json=examples or [],
    ))


def _persist_decisions_and_flags(
    db: Session,
    batch: IngestBatch,
    candidates: dict[str, CandidateDraft],
    candidate_rows: dict[str, MediaIdentityCandidate],
    fragments: dict[str, SourceFragment],
    classified: list[ClassifiedFile],
) -> list[FragmentReconstructionDecision]:
    rows: list[FragmentReconstructionDecision] = []
    batch_metadata = batch.metadata_json or {}
    source_origins_resolved = (
        batch_metadata.get("source_origins_resolved") is True
        and batch_metadata.get("duplicate_fragment_review_state") == "reviewed_merged"
    )
    resolved_single_identity = source_origins_resolved and len(candidates) == 1
    missing_track_numbers = [
        int(value)
        for value in (batch_metadata.get("missing_track_numbers") or [])
        if str(value).isdigit()
    ]
    media_types = {candidate.media_type for candidate in candidates.values()}
    mixed_batch = len(media_types) > 1
    if mixed_batch:
        _persist_flag(db, batch.id, "mixed_media_source", "Batch contains multiple primary media candidate types.", severity="review", examples=sorted(media_types))
    fragment_primary_types: dict[str, set[str]] = defaultdict(set)
    for item in classified:
        if item.media_class in PRIMARY_MEDIA_CLASSES:
            fragment_primary_types[item.fragment_path].add(item.media_class)
    for fragment_path, classes in fragment_primary_types.items():
        if len(classes) > 1:
            _persist_flag(
                db,
                batch.id,
                "mixed_media_source",
                "Source fragment contains multiple primary media classes.",
                severity="review",
                source_fragment_id=fragments.get(fragment_path).id if fragments.get(fragment_path) else None,
                examples=sorted(classes),
            )
    fragment_group_keys = {item.evidence.get("fragment_group_key") for item in classified if item.evidence.get("fragment_group_key")}
    if not source_origins_resolved:
        for group_key in sorted(str(key) for key in fragment_group_keys):
            _persist_flag(db, batch.id, "source_fragment_group_detected", "Sibling source fragments were detected and treated as evidence, not final grouping.", examples=[group_key])
    for draft in candidates.values():
        row = candidate_rows[draft.key]
        candidate_fragments = {member.fragment_path for member in draft.members}
        candidate_group_keys = {str(member.evidence.get("fragment_group_key")) for member in draft.members if member.evidence.get("fragment_group_key")}
        flags = set(draft.flags)
        reasons = list(dict.fromkeys(draft.reasons))
        if mixed_batch:
            flags.add("candidate_media_type_conflict")
            reasons.append("Candidate is part of a mixed-media batch")
        if (len(candidate_fragments) > 1 or candidate_group_keys) and not resolved_single_identity:
            flags.add("merge_recommended")
            if draft.media_type in {"music", "audiobook"}:
                flags.add("split_release_candidate")
            reasons.append("Candidate spans multiple source fragments")
        if draft.media_type == "music" and missing_track_numbers:
            flags.add("partial_track_set")
            missing_label = " and ".join(str(value) for value in missing_track_numbers)
            reasons.append(f"Partial track set - missing tracks {missing_label}")
        decision = "safe_group"
        severity = "info"
        score = min(0.98, max(0.1, draft.confidence))
        recommended_action = "keep candidate grouped"
        if "blocked_identity_conflict" in flags:
            decision, severity, recommended_action = "blocked_conflict", "error", "manual identity repair required"
        elif "track_number_conflict" in flags or "duplicate_chapter_identity" in flags or "disc_number_missing" in flags:
            decision, severity, recommended_action = "review_required", "review", "review disc/part and track/chapter numbering before move"
        elif any(flag in flags for flag in ("ambiguous_pdf_role", "movie_tv_ambiguous", "custom_media_low_metadata")):
            decision, severity, recommended_action = "review_required", "review", "review uncertain media identity or ownership"
        elif mixed_batch:
            decision, severity, recommended_action = "split_recommended", "review", "split candidate by media type before final move planning"
        elif any(flag in flags for flag in ("sidecar_without_owner", "artwork_without_owner")):
            decision, severity, recommended_action = "review_required", "review", "review uncertain media identity or ownership"
        elif "merge_recommended" in flags:
            decision, severity, recommended_action = "merge_recommended", "info", "merge sibling fragments into one candidate"
        for flag in sorted(flags):
            _persist_flag(
                db,
                batch.id,
                flag,
                (
                    f"Partial track set - missing tracks {' and '.join(str(value) for value in missing_track_numbers)}."
                    if flag == "partial_track_set"
                    else _flag_message(flag)
                ),
                severity="error" if flag == "blocked_identity_conflict" else "review" if decision in {"review_required", "split_recommended", "blocked_conflict"} else "warning",
                candidate_id=row.id,
                examples=[member.relative_path for member in draft.members[:3]],
            )
        decision_row = FragmentReconstructionDecision(
            batch_id=batch.id,
            candidate_id=row.id,
            fragment_group_key=sorted(candidate_group_keys)[0] if candidate_group_keys else None,
            decision=decision,
            severity=severity,
            score=score,
            reasons_json=reasons or [recommended_action],
            conflict_flags_json=sorted(flags),
            recommended_action=recommended_action,
        )
        db.add(decision_row)
        rows.append(decision_row)
    db.flush()
    return rows

def _flag_message(flag: str) -> str:
    messages = {
        "mixed_media_source": "Source contains multiple media types.",
        "source_fragment_group_detected": "Sibling source fragments were detected.",
        "split_release_candidate": "Release appears split across source fragments.",
        "merge_recommended": "Multiple source fragments appear to belong to one candidate.",
        "duplicate_track_identity": "Duplicate track identity detected.",
        "duplicate_chapter_identity": "Duplicate chapter identity detected.",
        "disc_number_missing": "Repeated track numbers need disc or part numbers.",
        "track_number_conflict": "Track number conflict requires review.",
        "candidate_media_type_conflict": "Candidate is in a mixed-media source.",
        "ambiguous_pdf_role": "PDF role is ambiguous.",
        "sidecar_without_owner": "Sidecar ownership is unclear.",
        "artwork_without_owner": "Artwork ownership is unclear.",
        "movie_tv_ambiguous": "Video file could be movie or TV without stronger evidence.",
        "custom_media_low_metadata": "Audio identity has low metadata evidence.",
        "blocked_identity_conflict": "Identity conflict blocks safe grouping.",
        "partial_track_set": "Partial track set requires metadata review.",
    }
    return messages.get(flag, flag.replace("_", " "))


def batch_reconstruction_summary(db: Session, batch_id: int) -> dict[str, Any]:
    fragments = db.query(SourceFragment).filter(SourceFragment.batch_id == batch_id).order_by(SourceFragment.relative_fragment_path).all()
    candidates = db.query(MediaIdentityCandidate).filter(MediaIdentityCandidate.batch_id == batch_id).order_by(MediaIdentityCandidate.candidate_media_type, MediaIdentityCandidate.candidate_title).all()
    decisions = db.query(FragmentReconstructionDecision).filter(FragmentReconstructionDecision.batch_id == batch_id).all()
    flags = db.query(MixedMediaFlag).filter(MixedMediaFlag.batch_id == batch_id).all()
    decision_by_candidate = {decision.candidate_id: decision for decision in decisions if decision.candidate_id is not None}
    return {
        "batch_id": batch_id,
        "source_fragments": [
            {
                "id": row.id,
                "relative_fragment_path": row.relative_fragment_path,
                "fragment_group_key": row.fragment_group_key,
                "fragment_label": row.fragment_label,
                "fragment_index": row.fragment_index,
                "fragment_count": row.fragment_count,
                "file_count": row.file_count,
                "media_class_counts": row.media_class_counts_json or {},
            }
            for row in fragments
        ],
        "candidates": [
            {
                "id": row.id,
                "candidate_key": row.candidate_key,
                "media_type": row.candidate_media_type,
                "title": row.candidate_title,
                "primary_creator": row.candidate_primary_creator,
                "confidence": row.candidate_confidence,
                "decision": getattr(decision_by_candidate.get(row.id), "decision", None),
                "flags": getattr(decision_by_candidate.get(row.id), "conflict_flags_json", []) or [],
            }
            for row in candidates
        ],
        "decisions": [
            {
                "decision": row.decision,
                "severity": row.severity,
                "candidate_id": row.candidate_id,
                "fragment_group_key": row.fragment_group_key,
                "reasons": row.reasons_json or [],
                "conflict_flags": row.conflict_flags_json or [],
                "recommended_action": row.recommended_action,
            }
            for row in decisions
        ],
        "flags": [
            {
                "flag_type": row.flag_type,
                "severity": row.severity,
                "message": row.message,
                "examples": row.examples_json or [],
            }
            for row in flags
        ],
    }