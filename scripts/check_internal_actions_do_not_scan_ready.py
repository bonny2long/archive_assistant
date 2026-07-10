"""AA-FLOW1 guard: internal archive actions must not scan _INGEST/ready."""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ROUTES = ROOT / "backend" / "app" / "api" / "routes.py"
SCAN_RUNTIME = ROOT / "backend" / "app" / "services" / "scan_runtime.py"
APP = ROOT / "frontend" / "src" / "App.tsx"
ACTION_BAR = ROOT / "frontend" / "src" / "components" / "ActionBar.tsx"
BATCH_TABLE = ROOT / "frontend" / "src" / "components" / "BatchTable.tsx"
CLIENT = ROOT / "frontend" / "src" / "api" / "client.ts"

FORBIDDEN_ROUTE_CALLS = (
    "start_scan_job(",
    "scan_music_ingest(",
    "scan_ready",
    "scan_ingest",
)


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8-sig")


def route_functions(source: str) -> dict[str, str]:
    matches = list(re.finditer(r"^def\s+(\w+)\([^\n]*\):", source, flags=re.MULTILINE))
    functions: dict[str, str] = {}
    for index, match in enumerate(matches):
        name = match.group(1)
        end = matches[index + 1].start() if index + 1 < len(matches) else len(source)
        functions[name] = source[match.start():end]
    return functions


def const_block(source: str, name: str) -> str:
    marker = f"const {name}"
    start = source.find(marker)
    if start == -1:
        raise AssertionError(f"Missing frontend block: {name}")
    next_const = source.find("\n  const ", start + len(marker))
    next_effect = source.find("\n  useEffect", start + len(marker))
    candidates = [pos for pos in (next_const, next_effect) if pos != -1]
    end = min(candidates) if candidates else len(source)
    return source[start:end]


def assert_true(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def check_backend_routes() -> None:
    routes = read(ROUTES)
    functions = route_functions(routes)
    assert_true("scan_music" in functions, "Missing explicit scan route function")
    assert_true("start_scan_job()" in functions["scan_music"], "Explicit scan route no longer starts scan job")

    for name, body in functions.items():
        if name == "scan_music":
            continue
        for forbidden in FORBIDDEN_ROUTE_CALLS:
            assert_true(forbidden not in body, f"Route {name} must not call scanner code: {forbidden}")

    scan_runtime = read(SCAN_RUNTIME)
    assert_true("def start_scan_job(scan_func=scan_music_ingest)" in scan_runtime, "Scan runtime should default to filesystem scan")
    assert_true("result = scan_func(db, progress=_set_progress)" in scan_runtime, "Scan runtime should execute only through the explicit scan worker")


def check_frontend_actions() -> None:
    app = read(APP)
    action_bar = read(ACTION_BAR)
    batch_table = read(BATCH_TABLE)
    client = read(CLIENT)

    assert_true('scanMusic: () => request<ScanJobStatus>("/scan/music", "POST")' in client, "scanMusic must target explicit scan endpoint")
    assert_true('scanStatus: () => request<ScanJobStatus>("/scan/status")' in client, "scanStatus must target scan status endpoint")
    assert_true('listBatches: () => request<PaginatedResponse<BatchSummary>>("/batches?page_size=100", "GET", undefined, BATCH_LIST_TIMEOUT_MS)' in client, "listBatches must remain a timed DB/API reload")
    assert_true('listPending: () => request<PaginatedResponse<BatchSummary>>("/batches/pending?page_size=100", "GET", undefined, BATCH_LIST_TIMEOUT_MS)' in client, "listPending must remain a timed DB/API reload")

    load_batches = const_block(app, "loadBatches")
    handle_refresh = const_block(app, "handleRefresh")
    handle_scan = const_block(app, "handleScan")

    assert_true("api.listBatches()" in load_batches, "loadBatches must reload batches from DB/API")
    assert_true("api.listPending()" in load_batches, "loadBatches fallback must reload pending batches from DB/API")
    assert_true("api.scanMusic" not in load_batches, "loadBatches must not scan ingest")
    assert_true("batchLoadRequestId" in load_batches, "loadBatches must ignore stale overlapping responses")
    assert_true("setBatchLoadError" in load_batches, "loadBatches must settle to an error state on failure")

    assert_true('await loadBatches({ mode: "refresh" })' in handle_refresh, "Refresh must reload existing DB/API batches")
    assert_true("api.scanMusic" not in handle_refresh, "Refresh must not scan ingest")

    assert_true("api.scanMusic()" in handle_scan, "Only Scan ingest should call scan endpoint")
    assert_true("setIsScanningIngest(true)" in handle_scan, "Scan action must set scan-specific UI state")

    assert_true('"Scanning ingest:"' not in action_bar, "Static header must not say Scanning ingest:")
    assert_true('"Ingest path"' in action_bar, "Default header should identify the ingest path")
    assert_true("isScanningIngest" in action_bar, "Scan wording must be conditional on isScanningIngest")

    assert_true("isInitialLoading && batches.length === 0 && !hasLoaded" in batch_table, "Full batch loading state must be initial empty load only")
    assert_true("Loading saved batches..." in batch_table, "Batch loading copy must not use scan language")
    assert_true("Refreshing..." in batch_table, "Refresh should have a compact refresh indicator")
    assert_true("No batches found. Click Scan ingest to discover ready media." in batch_table, "Empty state must tell the user how to discover media")


def main() -> None:
    check_backend_routes()
    check_frontend_actions()
    print("AA-FLOW1 ready-folder scan boundary checks passed")


if __name__ == "__main__":
    main()
