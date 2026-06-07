from app.db.init_db import init_db
from app.db.session import SessionLocal
from app.services.scanner import scan_music_ingest


if __name__ == "__main__":
    init_db()
    db = SessionLocal()
    try:
        result = scan_music_ingest(db)
        print(
            f"Created {result.created} new batch(es); "
            f"skipped {result.skipped_duplicates} duplicate(s)."
        )
    finally:
        db.close()
