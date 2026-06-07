"""Reset Archive Assistant music test data without dropping database tables."""

from __future__ import annotations

import argparse
import shutil
import sqlite3
import sys
from dataclasses import dataclass
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATA_ROOT = PROJECT_ROOT / "data"
DATABASE_PATH = PROJECT_ROOT / "backend" / "archive_assistant.db"
REPORTS_DIR = DATA_ROOT / "_REPORTS" / "ingest-reports"
LIBRARY_ROOT = DATA_ROOT / "Music" / "Library"


@dataclass(frozen=True)
class MoveRecord:
    batch_id: int
    source: Path
    destination: Path
    status: str


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Restore moved music to its original ingest paths, remove generated "
            "music reports, and clear music rows while preserving all tables."
        )
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Perform the reset. Without this flag, only print the planned changes.",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Print every file that will be restored.",
    )
    return parser.parse_args()


def is_within(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False


def load_music_state(connection: sqlite3.Connection) -> tuple[list[int], list[MoveRecord]]:
    batch_rows = connection.execute(
        """
        SELECT id
        FROM ingest_batches
        WHERE detected_type = 'music_album'
        ORDER BY id
        """
    ).fetchall()
    batch_ids = [row[0] for row in batch_rows]
    if not batch_ids:
        return [], []

    placeholders = ",".join("?" for _ in batch_ids)
    move_rows = connection.execute(
        f"""
        SELECT batch_id, source_path, destination_path, status
        FROM move_actions
        WHERE batch_id IN ({placeholders})
        ORDER BY id
        """,
        batch_ids,
    ).fetchall()
    moves = [
        MoveRecord(
            batch_id=row[0],
            source=Path(row[1]),
            destination=Path(row[2]),
            status=row[3],
        )
        for row in move_rows
    ]
    return batch_ids, moves


def validate_moves(moves: list[MoveRecord]) -> list[str]:
    errors: list[str] = []
    seen_sources: set[Path] = set()

    for move in moves:
        if move.status != "completed":
            continue
        if not is_within(move.source, DATA_ROOT / "_INGEST" / "music"):
            errors.append(f"Source is outside music ingest: {move.source}")
        if not is_within(move.destination, LIBRARY_ROOT):
            errors.append(f"Destination is outside music library: {move.destination}")
        if move.source in seen_sources:
            errors.append(f"Duplicate restore target: {move.source}")
        seen_sources.add(move.source)
        if move.source.exists() and move.destination.exists():
            errors.append(
                f"Both restore paths exist; refusing to overwrite: {move.source}"
            )

    return errors


def print_plan(
    connection: sqlite3.Connection,
    batch_ids: list[int],
    moves: list[MoveRecord],
    verbose: bool,
) -> None:
    completed = [move for move in moves if move.status == "completed"]
    restorable = [move for move in completed if move.destination.exists()]
    already_restored = [
        move for move in completed if move.source.exists() and not move.destination.exists()
    ]
    placeholders = ",".join("?" for _ in batch_ids)

    def count(table: str, condition: str, params: list[int]) -> int:
        return connection.execute(
            f"SELECT COUNT(*) FROM {table} WHERE {condition}", params
        ).fetchone()[0]

    archive_item_count = count("archive_items", "media_type = 'music'", [])
    print(f"Database: {DATABASE_PATH}")
    print(f"Music batches: {len(batch_ids)}")
    if batch_ids:
        print(
            "Rows to delete: "
            f"{count('ingest_files', f'batch_id IN ({placeholders})', batch_ids)} ingest files, "
            f"{count('move_actions', f'batch_id IN ({placeholders})', batch_ids)} move actions, "
            f"{archive_item_count} archive items"
        )
    print(f"Tracks to restore to ingest: {len(restorable)}")
    print(f"Tracks already restored: {len(already_restored)}")
    print(f"Generated batch reports to remove: {len(batch_ids)}")

    if verbose:
        for move in restorable:
            print(f"  RESTORE {move.destination} -> {move.source}")


def restore_files(moves: list[MoveRecord]) -> int:
    restored = 0
    for move in moves:
        if move.status != "completed" or not move.destination.exists():
            continue
        move.source.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(move.destination), str(move.source))
        restored += 1
    return restored


def remove_reports(batch_ids: list[int]) -> int:
    removed = 0
    for batch_id in batch_ids:
        report = REPORTS_DIR / f"batch-{batch_id}.json"
        if report.exists():
            report.unlink()
            removed += 1
    return removed


def remove_generated_library_metadata() -> int:
    removed = 0
    for path in LIBRARY_ROOT.rglob("batch-*-move-log.json"):
        if path.is_file():
            path.unlink()
            removed += 1
    return removed


def remove_empty_directories(root: Path) -> int:
    removed = 0
    directories = sorted(
        (path for path in root.rglob("*") if path.is_dir()),
        key=lambda path: len(path.parts),
        reverse=True,
    )
    for directory in directories:
        try:
            directory.rmdir()
            removed += 1
        except OSError:
            pass
    return removed


def clear_music_rows(connection: sqlite3.Connection, batch_ids: list[int]) -> None:
    if not batch_ids:
        return
    placeholders = ",".join("?" for _ in batch_ids)
    with connection:
        connection.execute(
            f"DELETE FROM move_actions WHERE batch_id IN ({placeholders})", batch_ids
        )
        connection.execute(
            f"DELETE FROM ingest_files WHERE batch_id IN ({placeholders})", batch_ids
        )
        connection.execute("DELETE FROM archive_items WHERE media_type = 'music'")
        connection.execute(
            f"DELETE FROM ingest_batches WHERE id IN ({placeholders})", batch_ids
        )


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(errors="backslashreplace")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(errors="backslashreplace")

    args = parse_args()
    if not DATABASE_PATH.exists():
        print(f"Database not found: {DATABASE_PATH}", file=sys.stderr)
        return 1

    connection = sqlite3.connect(DATABASE_PATH, timeout=30)
    try:
        batch_ids, moves = load_music_state(connection)
        errors = validate_moves(moves)
        if errors:
            print("Reset blocked:", file=sys.stderr)
            for error in errors:
                print(f"  {error}", file=sys.stderr)
            return 1

        print_plan(connection, batch_ids, moves, args.verbose)
        if not args.apply:
            print("\nDry run only. Run again with --apply to perform the reset.")
            return 0

        restored = restore_files(moves)
        reports = remove_reports(batch_ids)
        move_logs = remove_generated_library_metadata()
        empty_dirs = remove_empty_directories(LIBRARY_ROOT)
        clear_music_rows(connection, batch_ids)

        print("\nReset complete.")
        print(f"Restored tracks: {restored}")
        print(f"Removed reports: {reports}")
        print(f"Removed move logs: {move_logs}")
        print(f"Removed empty library directories: {empty_dirs}")
        print("Database tables were preserved.")
        return 0
    finally:
        connection.close()


if __name__ == "__main__":
    raise SystemExit(main())
