import sys
import json
from sqlalchemy.orm import sessionmaker

sys.path.append(r"c:\Users\BonnyMakaniankhondo\Documents\GitHub\NAS\archive-assistant-scaffold\archive-assistant-scaffold\backend")
from app.db.session import SessionLocal
from app.models.archive import IngestBatch, IngestFile

def main():
    db = SessionLocal()
    files = db.query(IngestFile).filter(IngestFile.batch_id == 20).all()
    print(f"Direct query file count for batch 20: {len(files)}")
    
    # Let's search if these albums' source_folders are in ANY files in the system
    batch = db.query(IngestBatch).get(20)
    if batch:
        albums = batch.metadata_json.get("albums", [])
        for a in albums:
            sf = a.get("source_folder")
            print(f"Searching for sf: {sf}")
            # we need to search files' json
    
    # Are there children created from batch 20?
    if batch:
        print(f"Parent batch 20 split_history: {batch.metadata_json.get('split_history')}")

if __name__ == "__main__":
    main()
