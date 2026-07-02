import argparse
import json
import os
import sys
from pathlib import Path

from sqlalchemy import func

PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = PROJECT_ROOT / "backend"
os.environ["DEBUG"] = "true"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.db.session import Base, SessionLocal, engine  # noqa: E402
from app.models.media_metadata import MetadataQualityDecision, MetadataReviewFlag  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="Report AA metadata quality decisions.")
    parser.add_argument("--out", type=Path, help="Optional JSON output path.")
    args = parser.parse_args()

    Base.metadata.create_all(bind=engine)
    with SessionLocal() as db:
        decision_counts = dict(
            db.query(MetadataQualityDecision.decision, func.count(MetadataQualityDecision.id))
            .group_by(MetadataQualityDecision.decision)
            .all()
        )
        flag_counts = dict(
            db.query(MetadataReviewFlag.flag_type, func.count(MetadataReviewFlag.id))
            .filter(MetadataReviewFlag.status == "open")
            .group_by(MetadataReviewFlag.flag_type)
            .all()
        )
        examples = {}
        for decision in ("review_required", "blocked"):
            rows = (
                db.query(MetadataQualityDecision)
                .filter(MetadataQualityDecision.decision == decision)
                .order_by(MetadataQualityDecision.updated_at.desc())
                .limit(5)
                .all()
            )
            examples[decision] = [
                {
                    "media_file_id": row.media_file_id,
                    "batch_id": row.batch_id,
                    "reasons": row.reasons_json or [],
                    "blocking_flags": row.blocking_flags_json or [],
                    "warning_flags": row.warning_flags_json or [],
                }
                for row in rows
            ]
    report = {
        "decision_counts": decision_counts,
        "flag_counts": flag_counts,
        "examples": examples,
    }
    print("AA-M4C Metadata Quality Report")
    print("===============================")
    print()
    print("Decision counts:")
    if decision_counts:
        for decision, count in sorted(decision_counts.items()):
            print(f"- {decision}: {count}")
    else:
        print("- no quality decisions found")
    print()
    print("Open flag counts:")
    if flag_counts:
        for flag_type, count in sorted(flag_counts.items()):
            print(f"- {flag_type}: {count}")
    else:
        print("- no open metadata review flags found")
    for decision, rows in examples.items():
        print()
        print(f"Examples: {decision}")
        if not rows:
            print("- none")
        for row in rows:
            print(f"- media_file_id={row['media_file_id']} batch_id={row['batch_id']} reasons={', '.join(row['reasons'])}")
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(report, indent=2), encoding="utf-8")
        print(f"Wrote JSON report: {args.out}")


if __name__ == "__main__":
    main()
