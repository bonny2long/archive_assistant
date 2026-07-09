import sys
import json
from sqlalchemy.orm import sessionmaker

sys.path.append(r"c:\Users\BonnyMakaniankhondo\Documents\GitHub\NAS\archive-assistant-scaffold\archive-assistant-scaffold\backend")
from app.db.session import SessionLocal
from app.models.archive import IngestBatch, IngestFile

def main():
    db = SessionLocal()
    batch = db.query(IngestBatch).get(20)
    with open("tmp_batch20_debug.txt", "w", encoding="utf-8") as f:
        f.write(f"Batch {batch.id} status: {batch.status}\n")
        f.write(f"Is parent_review_state: {batch.metadata_json.get('parent_review_state')}\n")
        f.write(f"split_history: {json.dumps(batch.metadata_json.get('split_history'), indent=2)}\n")
        f.write(f"remaining_albums count: {len(batch.metadata_json.get('albums', []))}\n")
        
        # Check files that previously belonged to this batch by parsing the history
        history = batch.metadata_json.get('split_history') or []
        for h in history:
            child_id = h.get("child_batch_id")
            if child_id:
                child = db.query(IngestBatch).get(child_id)
                f.write(f"Child {child_id} has {len(child.files) if child else 'NO BATCH'} files\n")

if __name__ == "__main__":
    main()
