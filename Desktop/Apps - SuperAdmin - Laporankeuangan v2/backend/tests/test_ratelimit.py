"""Rate limit middleware: classification logic + 429 response shape."""

from unittest.mock import AsyncMock

import pytest
from httpx import ASGITransport, AsyncClient
from starlette.requests import Request

from app.core.exceptions import RateLimitError
from app.core.middleware import _classify_request


def _build_request(path: str = "/api/v1/auth/me", auth: str | None = None) -> Request:
    """Construct a minimal Starlette Request for unit-testing the
    classifier without spinning up the full ASGI stack."""
    headers = []
    if auth is not None:
        headers.append((b"authorization", auth.encode()))
    scope = {
        "type": "http",
        "method": "GET",
        "path": path,
        "raw_path": path.encode(),
        "headers": headers,
        "client": ("203.0.113.7", 12345),
        "query_string": b"",
        "scheme": "http",
        "server": ("test", 80),
    }
    return Request(scope)


# ─── Classifier unit tests ─────────────────────────────────
def test_classify_skips_health_and_docs():
    assert _classify_request(_build_request("/health")) is None
    assert _classify_request(_build_request("/openapi.json")) is None
    assert _classify_request(_build_request("/docs")) is None


def test_classify_anonymous_uses_ip_bucket_and_anonymous_limit():
    from app.config import settings

    key, limit = _classify_request(_build_request("/api/v1/auth/login"))
    assert key.startswith("ip:")
    assert "203.0.113.7" in key
    assert limit == settings.RATE_LIMIT_ANONYMOUS


def test_classify_authenticated_uses_tenant_bucket_and_free_limit(tenant_token: dict):
    from app.config import settings

    auth = f"Bearer {tenant_token['access_token']}"
    key, limit = _classify_request(_build_request(auth=auth))
    assert key.startswith("tenant:")
    assert limit == settings.RATE_LIMIT_FREE


def test_classify_invalid_token_falls_back_to_ip():
    """A malformed JWT should not block the request; the auth dependency
    rejects it later. Here the rate limiter just degrades to IP-based."""
    key, _limit = _classify_request(_build_request(auth="Bearer not-a-real-token"))
    assert key.startswith("ip:")


# ─── End-to-end middleware behavior ────────────────────────
@pytest.fixture
def rl_app(monkeypatch):
    """Spin up the FastAPI app with rate limiting forcibly enabled,
    irrespective of conftest's env-var disable. We patch the imported
    `settings` reference inside the middleware module."""
    from app.config import settings as settings_obj
    from app.core import middleware as mw

    monkeypatch.setattr(settings_obj, "RATE_LIMIT_ENABLED", True)
    monkeypatch.setattr(mw.settings, "RATE_LIMIT_ENABLED", True)

    from app.main import app  # noqa: F401

    return app


async def test_rate_limit_returns_429_with_retry_after(rl_app, monkeypatch):
    """Mock check_rate_limit to raise; verify the middleware translates
    it into a 429 response with the right error envelope and
    Retry-After header."""
    raiser = AsyncMock(
        side_effect=RateLimitError(
            "Rate limit exceeded (60/60s)",
            details={"limit": 60, "window": 60, "current": 61},
        )
    )
    monkeypatch.setattr("app.core.middleware.check_rate_limit", raiser)

    async with AsyncClient(transport=ASGITransport(app=rl_app), base_url="http://test") as client:
        r = await client.get("/api/v1/auth/me")
    assert r.status_code == 429
    body = r.json()
    assert body["error"]["code"] == "rate_limit_exceeded"
    assert body["error"]["details"]["limit"] == 60
    assert r.headers.get("retry-after") == "60"
    raiser.assert_awaited_once()


async def test_rate_limit_redis_failure_fails_open(rl_app, monkeypatch):
    """If Redis is unreachable, the middleware logs and lets the request
    through — better than a hard 5xx that takes the API down with the
    cache. The request then reaches the auth dep which returns 401
    (no Bearer token), confirming we passed the rate limiter."""
    fake = AsyncMock(side_effect=RuntimeError("redis: connection refused"))
    monkeypatch.setattr("app.core.middleware.check_rate_limit", fake)

    async with AsyncClient(transport=ASGITransport(app=rl_app), base_url="http://test") as client:
        r = await client.get("/api/v1/auth/me")
    # Past the rate limiter; the auth dep then rejects the (missing) token
    assert r.status_code == 401
    fake.assert_awaited_once()


async def test_rate_limit_disabled_passes_all_requests(monkeypatch):
    """With RATE_LIMIT_ENABLED=false (the conftest default), even a
    raising mock should be skipped — middleware short-circuits before
    calling check_rate_limit."""
    from app.main import app

    fake = AsyncMock(side_effect=RateLimitError("nope", details={"window": 60}))
    monkeypatch.setattr("app.core.middleware.check_rate_limit", fake)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        r = await client.get("/api/v1/auth/me")
    # Auth dep rejects (no token), but we got past the rate limiter
    assert r.status_code == 401
    fake.assert_not_called()
