"""Reject changing requests that come from a web page on another site.

Any web page you have open can make your browser send a POST to
http://127.0.0.1:<port>. Browsers attach an Origin header to those requests, so
the server checks it. A request with no Origin header (curl, scripts, tests) is
not a browser request and passes.

An Origin is allowed when it is a loopback address on any port, or is listed in
ALLOWED_ORIGINS (comma separated, for example a LAN or Tailscale address).

The middleware is plain ASGI and only looks at changing methods, so reads and
media streaming pass straight through with no extra work.
"""

from __future__ import annotations

from typing import Callable, Iterable
from urllib.parse import urlsplit

from fastapi.responses import JSONResponse

UNSAFE_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})
LOOPBACK_HOSTS = frozenset({"127.0.0.1", "localhost", "::1"})


def _normalize(origin: str) -> str:
    return origin.strip().rstrip("/").lower()


def parse_origin_list(raw: str | None) -> tuple[str, ...]:
    if not raw:
        return ()
    return tuple(dict.fromkeys(_normalize(part) for part in raw.split(",") if part.strip()))


def origin_allowed(origin: str, extra_origins: Iterable[str] = (), *, allow_loopback: bool = True) -> bool:
    value = _normalize(origin)
    if value in {_normalize(item) for item in extra_origins}:
        return True
    if not allow_loopback:
        return False
    try:
        parts = urlsplit(value)
        hostname = parts.hostname
    except ValueError:
        return False
    if parts.scheme not in {"http", "https"}:
        return False
    if parts.username or parts.password or parts.path or parts.query or parts.fragment:
        return False
    return hostname in LOOPBACK_HOSTS


def request_allowed(
    method: str,
    origin: str | None,
    sec_fetch_site: str | None,
    extra_origins: Iterable[str] = (),
    *,
    allow_loopback: bool = True,
) -> tuple[bool, str]:
    """Return (allowed, reason). Only changing methods are checked."""
    if method.upper() not in UNSAFE_METHODS:
        return True, ""
    if origin is None:
        if (sec_fetch_site or "").lower() == "cross-site":
            return False, "Cross-site requests are not allowed"
        return True, ""
    if origin_allowed(origin, extra_origins, allow_loopback=allow_loopback):
        return True, ""
    return False, f"Origin not allowed: {origin[:200]}"


class OriginGuardMiddleware:
    def __init__(
        self,
        app,
        get_extra_origins: Callable[[], Iterable[str]] = lambda: (),
        allow_loopback: bool = True,
    ) -> None:
        self.app = app
        self.get_extra_origins = get_extra_origins
        self.allow_loopback = allow_loopback

    async def __call__(self, scope, receive, send) -> None:
        if scope["type"] != "http" or scope["method"] not in UNSAFE_METHODS:
            await self.app(scope, receive, send)
            return
        headers = {
            name.decode("latin-1").lower(): value.decode("latin-1")
            for name, value in scope.get("headers", [])
        }
        allowed, reason = request_allowed(
            scope["method"],
            headers.get("origin"),
            headers.get("sec-fetch-site"),
            tuple(self.get_extra_origins()),
            allow_loopback=self.allow_loopback,
        )
        if allowed:
            await self.app(scope, receive, send)
            return
        await JSONResponse({"detail": reason}, status_code=403)(scope, receive, send)
