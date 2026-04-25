"""Lightweight in-process event bus for cross-module communication.

For inter-process events (API ↔ Celery worker), use Redis Pub/Sub or LISTEN/NOTIFY.
"""
import asyncio
from collections.abc import Awaitable, Callable
from typing import Any

import structlog

logger = structlog.get_logger()

EventHandler = Callable[[dict[str, Any]], Awaitable[None]]
_subscribers: dict[str, list[EventHandler]] = {}


def subscribe(event_type: str) -> Callable[[EventHandler], EventHandler]:
    """Decorator to register a handler for an event type."""

    def decorator(fn: EventHandler) -> EventHandler:
        _subscribers.setdefault(event_type, []).append(fn)
        return fn

    return decorator


async def publish(event_type: str, payload: dict[str, Any]) -> None:
    """Fire-and-forget event publish. Handlers run in background tasks."""
    handlers = _subscribers.get(event_type, [])
    if not handlers:
        return
    asyncio.create_task(_dispatch(event_type, handlers, payload))


async def _dispatch(
    event_type: str, handlers: list[EventHandler], payload: dict[str, Any]
) -> None:
    results = await asyncio.gather(
        *(h(payload) for h in handlers), return_exceptions=True
    )
    for handler, result in zip(handlers, results, strict=True):
        if isinstance(result, Exception):
            logger.error(
                "event_handler_failed",
                event=event_type,
                handler=handler.__name__,
                error=str(result),
            )
