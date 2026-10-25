"""Bounded check: changing requests from other sites are refused."""

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
os.environ["DEBUG"] = "true"
sys.path.insert(0, str(ROOT / "backend"))

from app.core.config import Settings  # noqa: E402
from app.core.origin_guard import (  # noqa: E402
    OriginGuardMiddleware,
    origin_allowed,
    parse_origin_list,
    request_allowed,
)


def run_request(
    method: str,
    origin: str | None = None,
    sec_fetch_site: str | None = None,
    extra: tuple[str, ...] = (),
    scope_type: str = "http",
) -> tuple[int | None, bool]:
    """Send one request through the middleware. Returns (status, reached_app)."""
    reached = {"app": False}
    sent: list[dict] = []

    async def downstream(scope, receive, send):
        reached["app"] = True
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b"ok"})

    async def receive():
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(message):
        sent.append(message)

    headers = []
    if origin is not None:
        headers.append((b"origin", origin.encode("latin-1")))
    if sec_fetch_site is not None:
        headers.append((b"sec-fetch-site", sec_fetch_site.encode("latin-1")))
    scope = {"type": scope_type, "method": method, "path": "/api/move/approved", "headers": headers}
    middleware = OriginGuardMiddleware(downstream, get_extra_origins=lambda: extra)
    asyncio.run(middleware(scope, receive, send))
    status = next((m["status"] for m in sent if m["type"] == "http.response.start"), None)
    return status, reached["app"]


def check_origin_rules() -> None:
    for origin in (
        "http://127.0.0.1:5173",
        "http://localhost:5173",
        "https://localhost",
        "http://[::1]:8001",
        "HTTP://LOCALHOST:5173/",
    ):
        assert origin_allowed(origin), origin
    for origin in (
        "https://evil.example",
        "http://127.0.0.1.evil.example",
        "http://localhost.evil.example:5173",
        "http://127.0.0.1@evil.example",
        "http://evil.example#@127.0.0.1",
        "http://192.168.1.50:5173",
        "null",
        "file://",
        "http://127.0.0.1:5173/path",
        "",
    ):
        assert not origin_allowed(origin), origin

    extra = parse_origin_list("http://192.168.1.50:5173/, https://nas.example.ts.net")
    assert origin_allowed("http://192.168.1.50:5173", extra)
    assert origin_allowed("https://NAS.example.ts.net", extra)
    assert not origin_allowed("http://192.168.1.50:9999", extra)

    assert request_allowed("GET", "https://evil.example", None) == (True, "")
    assert request_allowed("POST", None, None) == (True, "")
    assert request_allowed("POST", None, "cross-site")[0] is False


def check_middleware() -> None:
    # A page on another site is refused before the route runs.
    for method in ("POST", "PUT", "PATCH", "DELETE"):
        assert run_request(method, "https://evil.example") == (403, False), method
    assert run_request("POST", "null") == (403, False)
    assert run_request("POST", None, "cross-site") == (403, False)

    # The dashboard (through the Vite proxy), scripts, and reads still work.
    assert run_request("POST", "http://127.0.0.1:5173") == (200, True)
    assert run_request("POST", "http://localhost:5173") == (200, True)
    assert run_request("POST") == (200, True)
    assert run_request("GET", "https://evil.example") == (200, True)
    assert run_request("OPTIONS", "https://evil.example") == (200, True)

    # A listed LAN address works; a neighbouring one does not.
    extra = parse_origin_list("http://192.168.1.50:5173")
    assert run_request("POST", "http://192.168.1.50:5173", extra=extra) == (200, True)
    assert run_request("POST", "http://192.168.1.51:5173", extra=extra) == (403, False)

    # Non-HTTP traffic passes straight through.
    assert run_request("POST", "https://evil.example", scope_type="lifespan")[1] is True


def check_settings_and_wiring() -> None:
    os.environ.pop("ALLOWED_ORIGINS", None)
    assert Settings(_env_file=None).allowed_origin_list == ()
    configured = Settings(_env_file=None, allowed_origins="http://192.168.1.50:5173/, https://nas.example.ts.net")
    assert configured.allowed_origin_list == ("http://192.168.1.50:5173", "https://nas.example.ts.net")

    from app.main import app

    assert any(item.cls is OriginGuardMiddleware for item in app.user_middleware), (
        "OriginGuardMiddleware is not installed on the Archive Assistant app"
    )


def main() -> None:
    check_origin_rules()
    check_middleware()
    check_settings_and_wiring()
    print("PASS - changing requests from other sites are refused; the dashboard and scripts still work")


if __name__ == "__main__":
    main()
