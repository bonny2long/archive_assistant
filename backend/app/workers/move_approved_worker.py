from app.db.init_db import init_db
from app.db.session import SessionLocal
from app.services.mover import move_approved_batches


if __name__ == "__main__":
    init_db()
    db = SessionLocal()
    try:
        moved, errors = move_approved_batches(db)
        print(f"Moved {moved} approved batch(es).")
        for error in errors:
            print(error)
    finally:
        db.close()
