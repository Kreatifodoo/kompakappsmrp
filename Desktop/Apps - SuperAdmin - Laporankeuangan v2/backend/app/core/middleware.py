"""Request middleware: request ID, timing, structured logging, rate limiting."""

import time
import uuid

import structlog
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from app.config import settings
from app.core.exceptions import RateLimitError
from app.core.ratelimit import check_rate_limit

logger = structlog.get_logger()

# Paths that bypass rate limiting (health checks, docs, schema)
_RATE_LIMIT_SKIP_PATHS = frozenset({"/health", "/openapi.json", "/docs", "/redoc", "/docs/oauth2-redirect"})


class RequestIdMiddleware(BaseHTTPMiddleware):
    """Attach a unique request ID to every request and response."""

    async def dispatch(self, request: Request, call_next):
        request_id = request.headers.get("x-request-id") or str(uuid.uuid4())
        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(request_id=request_id)
        request.state.request_id = request_id

        start = time.perf_counter()
        try:
            response: Response = await call_next(request)
        except Exception:
            logger.exception("request_failed", path=request.url.path)
            raise
        elapsed_ms = (time.perf_counter() - start) * 1000
        response.headers["x-request-id"] = request_id
        logger.info(
            "request",
            method=request.method,
            path=request.url.path,
            status=response.status_code,
            duration_ms=round(elapsed_ms, 2),
        )
        return response


def _classify_request(request: Request) -> tuple[str, int] | None:
    """Return (rate-limit key, requests/window limit) for this request,
    or None if it should bypass rate limiting.

    Authenticated requests are bucketed per-tenant (with the per-user-id
    token's `sub` as fallback when no tenant context). Anonymous requests
    are bucketed per source IP at a tighter limit so login/register
    surfaces don't leak to brute force."""
    if request.url.path in _RATE_LIMIT_SKIP_PATHS:
        return None

    auth = request.headers.get("Authorization", "")
    if auth.startswith("Bearer "):
        # Best-effort decode — the actual auth dep enforces validity.
        # Bad/expired tokens fall through to IP-based bucketing so they
        # can't bypass the tighter anonymous quota.
        try:
            from app.core.security import decode_access_token

            payload = decode_access_token(auth[7:])
            tid = payload.get("tid") or payload.get("sub")
            if tid:
                # Plan-based variation can plug in here in the future
                return f"tenant:{tid}", settings.RATE_LIMIT_FREE
        except Exception:  # noqa: BLE001 — any decode failure → IP fallback
            pass

    ip = request.client.host if request.client else "unknown"
    return f"ip:{ip}", settings.RATE_LIMIT_ANONYMOUS


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Sliding-window-bucket rate limiter backed by Redis.

    - Authenticated requests bucketed per `tenant:<id>` at
      RATE_LIMIT_FREE/min by default
    - Anonymous requests bucketed per `ip:<addr>` at
      RATE_LIMIT_ANONYMOUS/min (tighter to slow down brute force on
      login / register)
    - Health, OpenAPI schema, and docs paths bypass entirely
    - Disabled when `RATE_LIMIT_ENABLED=false` (used in tests + when
      Redis is not provisioned)
    - On Redis errors, fails OPEN (logs a warning, allows the request)
      so a Redis outage doesn't take the API down
    """

    async def dispatch(self, request: Request, call_next):
        if not settings.RATE_LIMIT_ENABLED:
            return await call_next(request)

        classification = _classify_request(request)
        if classification is None:
            return await call_next(request)
        key, limit = classification
        window = settings.RATE_LIMIT_WINDOW_SEC

        try:
            await check_rate_limit(key, limit, window)
        except RateLimitError as exc:
            return JSONResponse(
                status_code=exc.status_code,
                content={
                    "error": {
                        "code": exc.code,
                        "message": exc.message,
                        "details": exc.details,
                    }
                },
                headers={"Retry-After": str(window)},
            )
        except Exception as exc:  # noqa: BLE001 — Redis hiccup, log + allow
            logger.warning(
                "rate_limit_check_failed",
                key=key,
                error=str(exc),
            )

        return await call_next(request)
