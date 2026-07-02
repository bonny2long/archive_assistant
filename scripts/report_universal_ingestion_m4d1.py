import argparse
import json
import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = PROJECT_ROOT / "backend"
os.environ["DEBUG"] = "true"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.db.session import Base, SessionLocal, engine  # noqa: E402
from app.models.archive import IngestBatch  # noqa: E402
from app.models.media_metadata import MediaIdentityCandidate  # noqa: E402
from app.services.universal_ingestion import (  # noqa: E402
    PHASE_NAME,
    batch_reconstruction_summary,
    snapshot_universal_ingestion_boundary,
)


def main() -> None:
    parser = argparse.ArgumentParser(description="Report AA-M4D.1 universal ingestion reconstruction findings.")
    parser.add_argument("--out", type=Path, help="Optional JSON output path.")
    parser.add_argument("--snapshot", action="store_true", help="Snapshot current batches before reporting.")
    args = parser.parse_args()

    Base.metadata.create_all(bind=engine)
    report = {"phase": PHASE_NAME, "batches": []}
    with SessionLocal() as db:
        batches = db.query(IngestBatch).order_by(IngestBatch.id).all()
        if args.snapshot:
            for batch in batches:
                snapshot_universal_ingestion_boundary(db, batch)
            db.commit()
        for batch in batches:
            if not db.query(MediaIdentityCandidate.id).filter(MediaIdentityCandidate.batch_id == batch.id).first():
                continue
            summary = batch_reconstruction_summary(db, batch.id)
            summary["detected_type"] = batch.detected_type
            summary["status"] = batch.status
            summary["source_path"] = batch.source_path
            report["batches"].append(summary)

    print("AA-M4D.1 Universal Media Ingestion Boundary + Fragment Reconstruction Report")
    print("=========================================================================")
    print()
    if not report["batches"]:
        print("No universal ingestion reconstruction records found.")
        print("Run with --snapshot to build records for current batches without changing media or move plans.")
    for batch in report["batches"]:
        print(f"Batch ID: {batch['batch_id']} ({batch['detected_type']} / {batch['status']})")
        print(f"Source: {batch['source_path']}")
        print("Source fragment groups:")
        for fragment in batch["source_fragments"]:
            group = fragment["fragment_group_key"] or "-"
            counts = ", ".join(f"{key}={value}" for key, value in sorted(fragment["media_class_counts"].items())) or "none"
            print(f"- {fragment['relative_fragment_path']} group={group} files={fragment['file_count']} classes={counts}")
        print("Candidate groups:")
        for candidate in batch["candidates"]:
            title = candidate["title"] or candidate["candidate_key"]
            flags = ", ".join(candidate["flags"]) or "none"
            print(f"- {candidate['media_type']} | {title} | decision={candidate['decision']} | flags={flags}")
        print("Conflict flags:")
        if not batch["flags"]:
            print("- none")
        for flag in batch["flags"]:
            examples = ", ".join(flag["examples"][:3]) if flag["examples"] else "-"
            print(f"- {flag['flag_type']} ({flag['severity']}): {flag['message']} examples={examples}")
        print()

    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(report, indent=2), encoding="utf-8")
        print(f"Wrote JSON report: {args.out}")


if __name__ == "__main__":
    main()