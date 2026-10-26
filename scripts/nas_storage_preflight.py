"""Check that a NAS data root is laid out so the NAS apps can move files safely.

Run it on the machine that holds the data, as the same user the apps run as, before putting any real
media on it:

    python scripts/nas_storage_preflight.py --data-root /mnt/tank/nas-data

Stand-alone on purpose (standard library only), so it can run on the NAS host or inside a container.
It creates one temporary folder inside the data root, uses it for probes, and removes it again. It never
touches existing files.

Why it exists: Archive Assistant, Intake Watcher and Cleaner move things by rename. A rename only works
inside one filesystem. On ZFS, a child dataset (for example one per media type) is a separate filesystem,
so a move from _INGEST into Music/Library would have to copy and delete. Archive Assistant refuses that;
this script tells you before you hit it.

Exit code: 0 when nothing failed (warnings are information), 1 when something failed.
"""

from __future__ import annotations

import argparse
import os
import shutil
import sys
import unicodedata
import uuid
from pathlib import Path

# Folders the NAS apps move between. They must all be on one filesystem.
MOVE_GROUP = (
    "_INGEST/incoming",
    "_INGEST/intake-processing",
    "_INGEST/ready",
    "_INGEST/failed",
    "_INGEST/leftover-review",
    "_STAGING",
    "_QUARANTINE",
    "_TRASH",
    "Music/Library/FLAC",
    "Music/Library/MP3",
    "Movies/Library",
    "TV/Library",
    "Audiobooks/Library",
    "Books",
)
# Other folders: reported if they sit on a different filesystem, but moves do not depend on them.
OTHER = ("_REPORTS", "Music/Metadata", "Movies/Metadata", "TV/Metadata", "Audiobooks/Metadata", "Books/Metadata")

results: list[tuple[str, str]] = []


def say(status: str, message: str) -> None:
    results.append((status, message))
    print(f"[{status}] {message}")


def device(path: Path) -> int | None:
    current = path
    while not current.exists():
        if current.parent == current:
            return None
        current = current.parent
    return os.stat(current).st_dev


def mount_points(root: Path, depth: int = 3) -> list[Path]:
    """Folders inside the data root that are mount points: on ZFS, each one is a child dataset."""
    found: list[Path] = []
    base = len(root.parts)
    for folder, dirs, _files in os.walk(root, followlinks=False):
        here = Path(folder)
        if here != root and os.path.ismount(here):
            found.append(here)
        if len(here.parts) - base >= depth:
            dirs[:] = []
    return found


def check_one_filesystem(root: Path) -> None:
    devices: dict[int, list[str]] = {}
    for relative in MOVE_GROUP:
        path = root / relative
        dev = device(path)
        if dev is None:
            continue
        devices.setdefault(dev, []).append(relative + ("" if path.exists() else " (not created yet)"))
    if len(devices) <= 1:
        say("PASS", f"every folder the apps move between is on one filesystem ({sum(len(v) for v in devices.values())} checked)")
    else:
        say("FAIL", "the folders the apps move between are on DIFFERENT filesystems, so moves would have to copy and delete:")
        for index, (dev, folders) in enumerate(sorted(devices.items()), start=1):
            print(f"        filesystem {index} (device {dev}): {', '.join(folders)}")
        print("        Fix: keep all of these inside ONE dataset/mount, using plain folders, not child datasets.")
    mounts = mount_points(root)
    if mounts:
        say("FAIL" if any(m.relative_to(root).parts[0] in {p.split("/")[0] for p in MOVE_GROUP} for m in mounts) else "WARN",
            "mount points (child datasets) inside the data root: " + ", ".join(str(m.relative_to(root)) for m in mounts))
    else:
        say("PASS", "no child datasets or mounts inside the data root")
    others = [r for r in OTHER if device(root / r) not in (None, device(root))]
    if others:
        say("WARN", "on a different filesystem from the data root (not required, but unusual): " + ", ".join(others))


def probe_moves(root: Path, work: Path) -> None:
    """Rename a real file between the real folders, and back. A cross-filesystem layout fails here."""
    present = [r for r in MOVE_GROUP if (root / r).is_dir()]
    if len(present) < 2:
        say("WARN", "fewer than two of the NAS folders exist yet, so cross-folder renames were not tested (run again once they do)")
        return
    anchor = root / present[0]
    probe = anchor / f"{work.name}.probe"
    probe.write_bytes(b"preflight")
    failures = 0
    try:
        for relative in present[1:]:
            target = root / relative / f"{work.name}.probe"
            try:
                os.rename(probe, target)
                os.rename(target, probe)
            except OSError as exc:
                failures += 1
                say("FAIL", f"cannot rename between {present[0]} and {relative}: {exc}")
                if target.exists() and not probe.exists():
                    os.rename(target, probe)
    finally:
        probe.unlink(missing_ok=True)
        for relative in present[1:]:
            (root / relative / f"{work.name}.probe").unlink(missing_ok=True)
    if not failures:
        say("PASS", f"a real file renamed between {len(present)} NAS folders and back")


def check_permissions(work: Path) -> None:
    who = f"uid {os.getuid()} gid {os.getgid()}" if hasattr(os, "getuid") else "this Windows user"
    try:
        sample = work / "perm.txt"
        sample.write_text("x")
        renamed = work / "perm-renamed.txt"
        os.rename(sample, renamed)
        folder = work / "sub" / "deeper"
        folder.mkdir(parents=True)
        (folder / "a.txt").write_text("x")
        shutil.rmtree(work / "sub")
        renamed.unlink()
        say("PASS", f"this user ({who}) can create, rename and delete files and folders there")
    except OSError as exc:
        say("FAIL", f"this user ({who}) cannot write to the data root: {exc}. Check the dataset owner/ACL for the apps' user.")


def check_case(work: Path) -> None:
    (work / "Case.txt").write_text("x")
    sensitive = not (work / "case.txt").exists()
    (work / "Case.txt").unlink()
    say("PASS", "filenames are case-sensitive (Linux style)" if sensitive else
        "filenames are case-INSENSITIVE (Windows style). The apps compare names ignoring case, so both work")


def check_unicode(work: Path) -> None:
    composed = unicodedata.normalize("NFC", "Beyoncé")
    decomposed = unicodedata.normalize("NFD", "Beyoncé")
    (work / composed).write_text("x")
    try:
        same = (work / decomposed).exists()
        names = [p.name for p in work.iterdir() if "Beyonc" in p.name]
    finally:
        (work / composed).unlink(missing_ok=True)
    if same:
        say("PASS", "accented names match whichever Unicode form they are written in (the filesystem normalises them)")
    else:
        say("WARN", "accented names are stored exactly as written: the same name typed on a Mac (e + accent as two characters) "
                    "and on Windows or Linux (one accented character) are DIFFERENT files here. Files from Mac clients over "
                    f"SMB can look identical but not match. (stored as {ascii(names)})")


def check_name_limits(work: Path) -> None:
    name = "n" * 251 + ".txt"  # exactly 255 characters, the usual filesystem limit
    try:
        (work / name).write_text("x")
        (work / name).unlink()
    except OSError as exc:
        if os.name == "nt":
            say("WARN", "a 255-character filename does not fit under Windows' 260-character path limit (does not apply on the NAS)")
        else:
            say("FAIL", f"a 255-character filename cannot be created: {exc}")
        return
    say("PASS", "a 255-character filename works")


def check_space(root: Path) -> None:
    usage = shutil.disk_usage(root)
    say("PASS" if usage.free > 50 * 1024**3 else "WARN",
        f"free space {usage.free / 1024**3:.0f} GB of {usage.total / 1024**3:.0f} GB (a move needs no extra space, but ingest and quarantine do)")


def main() -> int:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(errors="replace")
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--data-root", required=True, type=Path, help="the NAS data root, for example /mnt/tank/nas-data")
    args = parser.parse_args()
    root = args.data_root.resolve()
    if not root.is_dir():
        print(f"[FAIL] {root} is not a folder")
        return 1
    print(f"NAS storage preflight for {root}\n")
    check_one_filesystem(root)
    work = root / f".nas-preflight-{uuid.uuid4().hex[:8]}"
    try:
        work.mkdir()
    except OSError as exc:
        say("FAIL", f"cannot create a folder in the data root: {exc}")
        return 1
    try:
        check_permissions(work)
        probe_moves(root, work)
        check_case(work)
        check_unicode(work)
        check_name_limits(work)
        check_space(root)
    finally:
        shutil.rmtree(work, ignore_errors=True)
    failed = sum(1 for status, _ in results if status == "FAIL")
    warned = sum(1 for status, _ in results if status == "WARN")
    print(f"\n{len(results) - failed - warned} passed, {warned} warning(s), {failed} failed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
