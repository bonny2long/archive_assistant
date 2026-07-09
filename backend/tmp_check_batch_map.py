import sys
from sqlalchemy.orm import sessionmaker

sys.path.append(r"c:\Users\BonnyMakaniankhondo\Documents\GitHub\NAS\archive-assistant-scaffold\archive-assistant-scaffold\backend")
from app.db.session import SessionLocal
from app.models.archive import IngestBatch, IngestFile

def main():
    db = SessionLocal()
    files = db.query(IngestFile).all()
    batch_map = {}
    for f in files:
        batch_map[f.batch_id] = batch_map.get(f.batch_id, 0) + 1
        
    print(f"Files per batch mapping: {batch_map}")
    
    # Check if there are any child batches
    # child batches have source_kind="manual-drop" and detected_type="music_album" (or similar)
    # let's just see how many batches there are in total
    batches = db.query(IngestBatch.id, IngestBatch.detected_type, IngestBatch.status, IngestBatch.metadata_json).all()
    for b in batches:
        # child batches have review_origin == 'multi_artist_discography_split'
        meta = b.metadata_json or {}
        if meta.get("review_origin") == "multi_artist_discography_split":
            print(f"Child batch detected! ID={b.id}, files count in map={batch_map.get(b.id, 0)}")

if __name__ == "__main__":
    main()
