# Testing

## Current Checks

```bash
python -m compileall backend/app scripts
python scripts/check_core_v1_regression.py
python scripts/check_tv_anime_specials_regression.py
python scripts/check_root_ingest.py
PYTHONPATH=backend DEBUG=true python scripts/check_reset_safety.py
cd frontend
npm run build
cd ..
git diff --check
```

## Manual Proof Tests

```text
PDF/book bridge test
Large discography bridge test
TV hard-case regression
Quarantine/unsupported test
Destination collision/no-overwrite test
Manifest/log verification
```

PASS means the requested behavior works without changing safety rules.

