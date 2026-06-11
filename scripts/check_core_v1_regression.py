#!/usr/bin/env python3
"""
Runs the bounded Archive Assistant v1 regression suite.

This guardrail does not replace manual UI testing and does not use the real
ingest or library folders. Each child check has a strict timeout so the suite
cannot wait indefinitely.
"""

from __future__ import annotations

import os
import signal
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CHECK_TIMEOUT_SECONDS = 30

CHECKS = [
    "scripts/check_universal_review_contract.py",
    "scripts/check_movie_final_polish.py",
    "scripts/check_movie_collection_split_review.py",
    "scripts/check_movie_collection_approval_fix.py",
    "scripts/check_tv_review_contract_no_regression.py",
    "scripts/check_tv_final_polish.py",
    "scripts/check_discography_album_editor.py",
    "scripts/check_discography_singles_bucket.py",
    "scripts/check_books_parse_and_collection_review.py",
    "scripts/check_audiobook_detection_and_review_display.py",
    "scripts/check_bulk_approve.py",
    "scripts/check_core_v1_freeze_contract.py",
]

# These filesystem integration checks remain available for targeted/manual
# runs, but are intentionally excluded from the default Windows suite because
# they have repeatedly stalled during temporary-directory cleanup:
# - scripts/check_discography_intake.py
# - scripts/check_audiobooks_foundation.py
# - scripts/check_library_metadata_manifests.py


def run_check(relative_path: str) -> None:
    script = ROOT / relative_path
    if not script.exists():
        raise AssertionError(f"Missing regression script: {relative_path}")

    print(f"\n=== RUNNING {relative_path} ===", flush=True)
    environment = os.environ.copy()
    environment["DEBUG"] = "true"
    environment["PYTHONPATH"] = str(ROOT / "backend")

    creationflags = (
        subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0
    )
    process = subprocess.Popen(
        [sys.executable, "-u", str(script)],
        cwd=str(ROOT),
        env=environment,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        creationflags=creationflags,
        start_new_session=os.name != "nt",
    )
    try:
        output, _ = process.communicate(timeout=CHECK_TIMEOUT_SECONDS)
    except subprocess.TimeoutExpired as exc:
        if os.name == "nt":
            subprocess.run(
                ["taskkill", "/PID", str(process.pid), "/T", "/F"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=False,
            )
        else:
            os.killpg(process.pid, signal.SIGKILL)
        output, _ = process.communicate()
        output = output or exc.stdout or ""
        if output:
            print(output)
        raise AssertionError(
            f"Regression check timed out after {CHECK_TIMEOUT_SECONDS}s: "
            f"{relative_path}"
        ) from exc

    print(output)
    if process.returncode != 0:
        raise AssertionError(
            f"Regression check failed: {relative_path} returned "
            f"{process.returncode}"
        )


def main() -> None:
    for check in CHECKS:
        try:
            run_check(check)
        except Exception as exc:
            print("\nCORE V1 REGRESSION FAILED")
            print(f"  - {check}: {exc}")
            raise SystemExit(1) from exc

    print("\nCORE V1 REGRESSION PASSED")
    print("Archive Assistant v1 core behavior is locked.")


if __name__ == "__main__":
    main()
