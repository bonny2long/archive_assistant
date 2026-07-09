import sys
from sqlalchemy.orm import sessionmaker

sys.path.append(r"c:\Users\BonnyMakaniankhondo\Documents\GitHub\NAS\archive-assistant-scaffold\archive-assistant-scaffold\backend")
from app.db.session import SessionLocal
from app.models.archive import IngestBatch, IngestFile

def main():
    db = SessionLocal()
    batches = db.query(IngestBatch).count()
    files = db.query(IngestFile).count()
    print(f"Total batches: {batches}")
    print(f"Total files: {files}")
    
    # give me the batch ID of a batch that has files
    a_file = db.query(IngestFile).first()
    if a_file:
        print(f"File {a_file.id} has batch_id {a_file.batch_id}")

if __name__ == "__main__":
    main()
