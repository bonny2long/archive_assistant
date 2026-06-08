import json
from pathlib import Path
from app.core.time import serialize_utc, now_utc


def write_json_report(report_dir: Path, batch_id: int, payload: dict) -> Path:
    report_dir.mkdir(parents=True, exist_ok=True)
    path = report_dir / f"batch-{batch_id}.json"
    report = {**payload, "generated_at": serialize_utc(now_utc())}
    path.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    return path
