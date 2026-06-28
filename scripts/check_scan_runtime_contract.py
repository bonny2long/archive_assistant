#!/usr/bin/env python3
"""Bounded contract check for process-local scan runtime behavior."""

from __future__ import annotations

import json
import sys
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.services import scan_runtime


REQUIRED_STATUS_KEYS = {
    "job_id",
    "status",
    "phase",
    "message",
    "current_path",
    "started_at",
    "completed_at",
    "elapsed_seconds",
    "created",
    "skipped_duplicates",
    "result",
    "error_message",
}


class FakeDb:
    def __init__(self) -> None:
        self.closed = False

    def close(self) -> None:
        self.closed = True


class FakeResult:
    created = 2
    skipped_duplicates = 1
    movie_batches_found = 0
    tv_shows_found = 0
    tv_episodes_found = 0
    music_albums_found = 0
    discographies_found = 0
    book_batches_found = 0
    book_files_found = 0
    audiobook_batches_found = 2
    audiobook_files_found = 4
    unknown_items = 0
    unsupported_files = 0
    ignored_system_files = 0
    ignored_sidecar_only_folders = 0
    artwork_files_found = 0
    subtitle_files_found = 0


def assert_status_shape(status: dict[str, object], label: str) -> None:
    missing = REQUIRED_STATUS_KEYS - set(status)
    if missing:
        raise AssertionError(f"{label}: missing status keys {sorted(missing)}")
    json.dumps(status)


def main() -> None:
    original_session_local = scan_runtime.SessionLocal
    fake_db = FakeDb()
    started = threading.Event()
    release = threading.Event()
    seen_dbs: list[FakeDb] = []

    def fake_scan(db, progress=None):
        if db is not fake_db:
            raise AssertionError("scan runtime did not use patched DB session")
        seen_dbs.append(db)
        if progress:
            progress(
                phase="Fake scan phase",
                message="Fake scan message",
                current_path="fake://ready",
            )
        started.set()
        if not release.wait(timeout=5):
            raise AssertionError("fake scan release timed out")
        return FakeResult()

    try:
        scan_runtime.SessionLocal = lambda: fake_db

        idle = scan_runtime.get_scan_status()
        assert_status_shape(idle, "idle status")

        first = scan_runtime.start_scan_job(scan_func=fake_scan)
        assert_status_shape(first, "first start status")
        if first.get("already_running") is not False:
            raise AssertionError("first scan should not report already_running")
        if first["status"] != "running":
            raise AssertionError(f"first scan status was {first['status']!r}")

        if not started.wait(timeout=2):
            raise AssertionError("fake scan did not start quickly")

        second = scan_runtime.start_scan_job(scan_func=fake_scan)
        assert_status_shape(second, "second start status")
        if second.get("already_running") is not True:
            raise AssertionError("second scan should report already_running")

        mid = scan_runtime.get_scan_status()
        assert_status_shape(mid, "mid-scan status")
        if mid["phase"] != "Fake scan phase":
            raise AssertionError(f"progress phase not reflected: {mid['phase']!r}")
        if mid["current_path"] != "fake://ready":
            raise AssertionError("progress current_path not reflected")

        release.set()
        deadline = time.monotonic() + 5
        completed = scan_runtime.get_scan_status()
        while time.monotonic() < deadline:
            completed = scan_runtime.get_scan_status()
            if completed["status"] == "completed":
                break
            time.sleep(0.05)

        assert_status_shape(completed, "completed status")
        if completed["status"] != "completed":
            raise AssertionError(f"scan did not complete: {completed}")
        if completed["created"] != 2:
            raise AssertionError(f"created count mismatch: {completed['created']!r}")
        if completed["skipped_duplicates"] != 1:
            raise AssertionError(
                f"skipped duplicate count mismatch: {completed['skipped_duplicates']!r}"
            )
        result = completed.get("result")
        if not isinstance(result, dict):
            raise AssertionError("completed result was not serialized to a dict")
        if result.get("audiobook_batches_found") != 2:
            raise AssertionError("serialized result lost audiobook batch count")
        if seen_dbs != [fake_db]:
            raise AssertionError("scan function should run exactly once")
        if not fake_db.closed:
            raise AssertionError("scan runtime did not close the DB session")
    finally:
        release.set()
        scan_runtime.SessionLocal = original_session_local

    print("PASS - Scan runtime contract verified")


if __name__ == "__main__":
    main()
