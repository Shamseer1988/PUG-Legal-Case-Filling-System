"""Security headers + a tiny in-memory per-IP rate limiter.

The rate limiter is intentionally simple - good enough for a
single-instance deployment behind nginx. Swap for Redis-backed
limits when scaling out.
"""

from __future__ import annotations

import time
from collections import defaultdict, deque
from threading import Lock

from fastapi import HTTPException, Request, status
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response

from app.core.config import get_settings

# ---------------- Security headers ----------------
DEFAULT_SECURITY_HEADERS = {
    # Force HTTPS for one year, include subdomains. Only emitted when the
    # request hit us over TLS so we don't break local HTTP dev.
    "Strict-Transport-Security": "max-age=31536000; includeSubDomains",
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "strict-origin-when-cross-origin",
    "Permissions-Policy": "geolocation=(), microphone=(), camera=()",
    "X-Permitted-Cross-Domain-Policies": "none",
}


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        response = await call_next(request)
        cfg = get_settings()
        if not cfg.security_headers_enabled:
            return response
        for k, v in DEFAULT_SECURITY_HEADERS.items():
            if k == "Strict-Transport-Security":
                if (
                    request.url.scheme == "https"
                    or request.headers.get("x-forwarded-proto") == "https"
                ):
                    response.headers[k] = v
            else:
                response.headers[k] = v
        return response


# ---------------- Rate limit ----------------
class _Bucket:
    """Simple sliding window per (ip, key) - keeps last 1h of hits."""

    def __init__(self) -> None:
        self.times: deque[float] = deque()

    def hit(self) -> None:
        self.times.append(time.time())

    def trim(self, oldest: float) -> None:
        while self.times and self.times[0] < oldest:
            self.times.popleft()

    def count_within(self, seconds: int) -> int:
        cutoff = time.time() - seconds
        self.trim(time.time() - 3600)
        return sum(1 for t in self.times if t >= cutoff)


class RateLimiter:
    def __init__(self) -> None:
        self._buckets: dict[tuple[str, str], _Bucket] = defaultdict(_Bucket)
        self._lock = Lock()

    def check(self, ip: str, key: str, per_minute: int, per_hour: int) -> None:
        if not ip:
            return
        with self._lock:
            b = self._buckets[(ip, key)]
            b.hit()
            m = b.count_within(60)
            h = b.count_within(3600)
        if m > per_minute or h > per_hour:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=(
                    "Too many attempts. Try again in a minute."
                    if m > per_minute
                    else "Hourly limit reached. Try again later."
                ),
            )

    def reset(self, ip: str, key: str) -> None:
        with self._lock:
            self._buckets.pop((ip, key), None)


_limiter = RateLimiter()


def login_rate_limit(request: Request) -> None:
    """FastAPI dep: throttles per (IP, route) - call before checking creds."""
    ip = (request.headers.get("x-forwarded-for", "") or "").split(",")[0].strip()
    if not ip and request.client:
        ip = request.client.host
    cfg = get_settings()
    _limiter.check(
        ip,
        "auth_login",
        per_minute=cfg.rate_limit_login_per_minute,
        per_hour=cfg.rate_limit_login_per_hour,
    )


def reset_login_rate(request: Request) -> None:
    ip = (request.headers.get("x-forwarded-for", "") or "").split(",")[0].strip()
    if not ip and request.client:
        ip = request.client.host
    _limiter.reset(ip, "auth_login")
