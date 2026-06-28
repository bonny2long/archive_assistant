from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from threading import Lock, Thread
from time import monotonic
from typing import Any
from uuid import uuid4

from app.core.time import now_utc, serialize_utc
from app.db.session import SessionLocal
from app.services.scanner import scan_music_ingest


@dataclass
class ScanState:
    job_id: str | None = None
    status: str = "idle"
    phase: str | None = None
    message: str | None = None
    current_path: str | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    started_monotonic: float | None = None
    elapsed_seconds: float = 0.0
    created: int = 0
    skipped_duplicates: int = 0
    result: dict[str, Any] | None = None
    error_message: str | None = None


_state = ScanState()
_lock = Lock()
_worker: Thread | None = None


def _elapsed_seconds() -> float:
    if _state.started_monotonic is None:
        return 0.0
    return round(max(0.0, monotonic() - _state.started_monotonic), 2)


def _snapshot_locked() -> dict[str, Any]:
    if _state.status == "running":
        _state.elapsed_seconds = _elapsed_seconds()
    return {
        "job_id": _state.job_id,
        "status": _state.status,
        "phase": _state.phase,
        "message": _state.message,
        "current_path": _state.current_path,
        "started_at": (
            serialize_utc(_state.started_at) if _state.started_at else None
        ),
        "completed_at": (
            serialize_utc(_state.completed_at) if _state.completed_at else None
        ),
        "elapsed_seconds": _state.elapsed_seconds,
        "created": _state.created,
        "skipped_duplicates": _state.skipped_duplicates,
        "result": _state.result,
        "error_message": _state.error_message,
    }


def get_scan_status() -> dict[str, Any]:
    with _lock:
        return _snapshot_locked()


def _set_progress(
    *,
    phase: str,
    message: str | None = None,
    current_path: str | None = None,
) -> None:
    with _lock:
        if _state.status != "running":
            return
        _state.phase = phase
        _state.message = message
        _state.current_path = current_path
        _state.elapsed_seconds = _elapsed_seconds()


def _result_to_dict(result: Any) -> dict[str, Any]:
    return {
        "created": int(getattr(result, "created", 0) or 0),
        "skipped_duplicates": int(
            getattr(result, "skipped_duplicates", 0) or 0
        ),
        "movie_batches_found": int(
            getattr(result, "movie_batches_found", 0) or 0
        ),
        "tv_shows_found": int(getattr(result, "tv_shows_found", 0) or 0),
        "tv_episodes_found": int(
            getattr(result, "tv_episodes_found", 0) or 0
        ),
        "music_albums_found": int(
            getattr(result, "music_albums_found", 0) or 0
        ),
        "discographies_found": int(
            getattr(result, "discographies_found", 0) or 0
        ),
        "book_batches_found": int(
            getattr(result, "book_batches_found", 0) or 0
        ),
        "book_files_found": int(getattr(result, "book_files_found", 0) or 0),
        "audiobook_batches_found": int(
            getattr(result, "audiobook_batches_found", 0) or 0
        ),
        "audiobook_files_found": int(
            getattr(result, "audiobook_files_found", 0) or 0
        ),
        "unknown_items": int(getattr(result, "unknown_items", 0) or 0),
        "unsupported_files": int(
            getattr(result, "unsupported_files", 0) or 0
        ),
        "ignored_system_files": int(
            getattr(result, "ignored_system_files", 0) or 0
        ),
        "ignored_sidecar_only_folders": int(
            getattr(result, "ignored_sidecar_only_folders", 0) or 0
        ),
        "artwork_files_found": int(
            getattr(result, "artwork_files_found", 0) or 0
        ),
        "subtitle_files_found": int(
            getattr(result, "subtitle_files_found", 0) or 0
        ),
    }


def start_scan_job(scan_func=scan_music_ingest) -> dict[str, Any]:
    global _worker
    with _lock:
        if _state.status == "running" and _worker and _worker.is_alive():
            snap = _snapshot_locked()
            snap["already_running"] = True
            return snap

        _state.job_id = str(uuid4())
        _state.status = "running"
        _state.phase = "Preparing scan"
        _state.message = "Scan queued"
        _state.current_path = None
        _state.started_at = now_utc()
        _state.completed_at = None
        _state.started_monotonic = monotonic()
        _state.elapsed_seconds = 0.0
        _state.created = 0
        _state.skipped_duplicates = 0
        _state.result = None
        _state.error_message = None

        _worker = Thread(
            target=_run_scan_job,
            args=(scan_func,),
            name="archive-scan-worker",
            daemon=True,
        )
        _worker.start()
        snap = _snapshot_locked()
        snap["already_running"] = False
        return snap


def _run_scan_job(scan_func=scan_music_ingest) -> None:
    db = SessionLocal()
    try:
        _set_progress(phase="Reading ready folder", message="Starting scan")
        result = scan_func(db, progress=_set_progress)
        result_dict = _result_to_dict(result)
        with _lock:
            _state.status = "completed"
            _state.phase = "Complete"
            _state.message = "Scan complete"
            _state.current_path = None
            _state.completed_at = now_utc()
            _state.elapsed_seconds = _elapsed_seconds()
            _state.created = result_dict["created"]
            _state.skipped_duplicates = result_dict["skipped_duplicates"]
            _state.result = result_dict
    except Exception as exc:
        with _lock:
            _state.status = "failed"
            _state.phase = "Failed"
            _state.message = "Scan failed"
            _state.error_message = f"{type(exc).__name__}: {exc}"
            _state.completed_at = now_utc()
            _state.elapsed_seconds = _elapsed_seconds()
    finally:
        db.close()
