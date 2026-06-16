"""Check deterministic classification of direct root ingest items."""

from __future__ import annotations

import faulthandler
import os
import subprocess
import shutil
import sys
import time
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = PROJECT_ROOT / "backend"
CHILD_ENV = "ARCHIVE_ASSISTANT_ROOT_INGEST_CHECK_CHILD"
TIMEOUT_SECONDS = 30
TEMP_ROOTS = [Path(r"C:\tmp"), PROJECT_ROOT / ".tmp"]


def cleanup_old_temp_folders() -> None:
    for tmp_root in TEMP_ROOTS:
        if not tmp_root.exists():
            continue
        for path in tmp_root.glob("archive-root-ingest-*"):
            if path.is_dir():
                shutil.rmtree(path, ignore_errors=True)


def make_temp_root(prefix: str) -> Path:
    denied_roots = []
    for tmp_root in TEMP_ROOTS:
        try:
            tmp_root.mkdir(parents=True, exist_ok=True)
        except PermissionError:
            denied_roots.append(tmp_root)
            continue
        for attempt in range(100):
            candidate = (
                tmp_root
                / f"{prefix}{os.getpid()}-{time.monotonic_ns()}-{attempt}"
            )
            try:
                candidate.mkdir()
                return candidate
            except FileExistsError:
                continue
            except PermissionError:
                denied_roots.append(tmp_root)
                break
    raise RuntimeError(
        "Could not create temp folder under "
        + ", ".join(str(root) for root in TEMP_ROOTS)
        + f"; permission denied for: {', '.join(str(root) for root in denied_roots)}"
    )


def check(label: str, condition: bool) -> int:
    print(f"{'PASS' if condition else 'FAIL'} {label}", flush=True)
    return 0 if condition else 1


def touch(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"root-ingest-check")


def run_checks() -> int:
    print("check: before imports", flush=True)
    faulthandler.enable()
    faulthandler.dump_traceback_later(15, repeat=False)
    os.environ["DEBUG"] = "true"
    sys.path.insert(0, str(BACKEND_ROOT))
    print("check: after imports", flush=True)

    failures = 0
    print("check: before temp root setup", flush=True)
    cleanup_old_temp_folders()
    print("check: setup temp root", flush=True)
    root = make_temp_root("archive-root-ingest-")
    try:
        print(f"root ingest check temp: {root}", flush=True)
        print("check: scan root ingest classification", flush=True)
        from app.services.scanner import (  # noqa: WPS433
            classify_ingest_item,
            is_skipped_root_unsupported_file,
        )

        album = root / "Artist - Album"
        touch(album / "01.mp3")

        discography = root / "Artist Discography"
        touch(discography / "2001 - First" / "01.flac")
        touch(discography / "2003 - Second" / "01.flac")

        multi_disc = root / "Artist - Double Album"
        touch(multi_disc / "CD1" / "01.mp3")
        touch(multi_disc / "CD2" / "01.mp3")

        unknown = root / "notes.txt"
        unknown.write_text("not media", encoding="utf-8")

        sidecar_only = root / "Severance Season 1 Mp4 1080p"
        sidecar_only.mkdir()
        (sidecar_only / "Read Me.txt").write_text("source note", encoding="utf-8")

        legacy = root / "music"
        touch(legacy / "Old Album" / "01.mp3")

        print("check: root-level album", flush=True)
        failures += check(
            "root-level album classifies as music_album",
            classify_ingest_item(album) == "music_album",
        )
        print("check: root-level discography", flush=True)
        failures += check(
            "root-level discography classifies as music_discography",
            classify_ingest_item(discography) == "music_discography",
        )
        print("check: multi-disc release", flush=True)
        failures += check(
            "multi-disc release remains music_album",
            classify_ingest_item(multi_disc) == "music_album",
        )
        print("check: loose unsupported root file", flush=True)
        failures += check(
            "unknown file is skipped safely",
            is_skipped_root_unsupported_file(
                unknown,
                classify_ingest_item(unknown),
            ),
        )
        print("check: sidecar-only folder", flush=True)
        failures += check(
            "sidecar-only folder is skipped without quarantine",
            classify_ingest_item(sidecar_only) == "ignored_sidecar_only_folder",
        )
        print("check: legacy root folder", flush=True)
        failures += check(
            "legacy music container is not the scan target",
            classify_ingest_item(legacy) == "ignored_system_folder",
        )
    finally:
        faulthandler.cancel_dump_traceback_later()
        print("check: before cleanup", flush=True)
        shutil.rmtree(root, ignore_errors=True)
        print("check: after cleanup", flush=True)

    return 1 if failures else 0


def main() -> int:
    if os.environ.get(CHILD_ENV) == "1":
        return run_checks()

    env = {**os.environ, CHILD_ENV: "1"}
    try:
        completed = subprocess.run(
            [sys.executable, str(Path(__file__).resolve())],
            cwd=PROJECT_ROOT,
            env=env,
            text=True,
            capture_output=True,
            timeout=TIMEOUT_SECONDS,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        if exc.stdout:
            print(exc.stdout, end="")
        if exc.stderr:
            print(exc.stderr, end="", file=sys.stderr)
        print(
            f"FAIL check_root_ingest.py timed out after {TIMEOUT_SECONDS}s",
            flush=True,
        )
        return 124

    if completed.stdout:
        print(completed.stdout, end="")
    if completed.stderr:
        print(completed.stderr, end="", file=sys.stderr)
    return completed.returncode


if __name__ == "__main__":
    raise SystemExit(main())
