import json
from pathlib import Path


def write_json_report(report_dir: Path, batch_id: int, payload: dict) -> Path:
    report_dir.mkdir(parents=True, exist_ok=True)
    path = report_dir / f"batch-{batch_id}.json"
    path.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
    return path
