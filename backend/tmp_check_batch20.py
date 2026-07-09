import sys
import json
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

sys.path.append(r"c:\Users\BonnyMakaniankhondo\Documents\GitHub\NAS\archive-assistant-scaffold\archive-assistant-scaffold\backend")
from app.db.session import SessionLocal
from app.models.archive import IngestBatch, IngestFile
from app.services.batch_split import _file_album_source_folder

def main():
    db = SessionLocal()
    batch = db.query(IngestBatch).get(20)
    with open("tmp_batch20_out.txt", "w", encoding="utf-8") as f:
        f.write(f"Batch 20 file count: {len(batch.files)}\n")
        
        albums = batch.metadata_json.get("albums", [])
        f.write("Albums in metadata:\n")
        for a in albums:
            f.write(f"  - {a.get('source_folder')} | include={a.get('include')}\n")
            
        f.write("\nFile-level source folders:\n")
        counts = {}
        no_meta = 0
        for fi in batch.files:
            sf = _file_album_source_folder(fi)
            if sf:
                counts[sf] = counts.get(sf, 0) + 1
            else:
                no_meta += 1
                
        for sf, count in counts.items():
            f.write(f"  - {sf} (x{count})\n")
            
        f.write(f"\nFiles with no sf: {no_meta}\n")

if __name__ == "__main__":
    main()
