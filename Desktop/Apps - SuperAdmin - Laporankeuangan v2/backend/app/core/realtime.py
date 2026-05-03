"""Real-time broadcaster: tenant-scoped WebSocket fan-out via Redis pub/sub.

Architecture (works across uvicorn workers):

  Worker A         Worker B         Worker C
  ┌──────┐         ┌──────┐         ┌──────┐
  │ ws₁  │◄────────┤ ws₂  │         │ ws₃  │   ← clients
  │ ws₂  │         │ ws₃  │         │ ws₄  │
  └──┬───┘         └──┬───┘         └──┬───┘
     │                │                │
     └─── Redis pub/sub ────────────────┘
              channel: kompak:rt:<tenant_id>

Each worker keeps an in-memory `connections` dict (tenant_id → set[ws]) and
also subscribes to Redis. When `broadcast()` is called from any worker:
  1. Local connections in same tenant are notified directly.
  2. The event is also PUBLISHed to Redis so other workers' subscribers
     deliver it to their own local connections.
"""

from __future__ import annotations

import asyncio
import json
import logging
from collections import defaultdict
from typing import Any
from uuid import UUID

import redis.asyncio as aioredis
from fastapi import WebSocket

from app.config import settings

logger = logging.getLogger(__name__)


def _channel(tenant_id: UUID | str) -> str:
    return f"kompak:rt:{tenant_id}"


class RealtimeBroadcaster:
    """One instance per process (worker). Holds local WS connections and a
    single Redis pub/sub subscriber that fans out to those connections."""

    def __init__(self) -> None:
        # tenant_id (str) → set[WebSocket]
        self._conns: dict[str, set[WebSocket]] = defaultdict(set)
        # tenant_id (str) → asyncio.Task (Redis subscribe loop)
        self._sub_tasks: dict[str, asyncio.Task] = {}
        self._redis: aioredis.Redis | None = None
        self._lock = asyncio.Lock()

    async def _redis_client(self) -> aioredis.Redis:
        if self._redis is None:
            self._redis = aioredis.from_url(settings.REDIS_URL, decode_responses=True)
        return self._redis

    async def connect(self, ws: WebSocket, tenant_id: UUID) -> None:
        """Register a WS connection for a tenant. Starts the Redis subscriber
        loop on first connection for that tenant in this worker."""
        tid = str(tenant_id)
        async with self._lock:
            first = tid not in self._sub_tasks
            self._conns[tid].add(ws)
            if first:
                self._sub_tasks[tid] = asyncio.create_task(self._subscribe_loop(tid))
        logger.info("realtime_connect tenant=%s total=%d", tid, len(self._conns[tid]))

    async def disconnect(self, ws: WebSocket, tenant_id: UUID) -> None:
        tid = str(tenant_id)
        async with self._lock:
            self._conns[tid].discard(ws)
            if not self._conns[tid]:
                # No more local subscribers — stop Redis loop for this tenant
                task = self._sub_tasks.pop(tid, None)
                if task and not task.done():
                    task.cancel()
                self._conns.pop(tid, None)
        logger.info("realtime_disconnect tenant=%s remaining=%d", tid, len(self._conns.get(tid, [])))

    async def broadcast(self, tenant_id: UUID, event_type: str, data: dict[str, Any]) -> None:
        """Publish to Redis (which fans out to ALL workers including this one).
        Same-worker subscribers will receive it via the Redis loop just like
        peers in other workers, so we don't double-deliver here."""
        payload = json.dumps({"type": event_type, "data": data}, default=str)
        try:
            r = await self._redis_client()
            await r.publish(_channel(tenant_id), payload)
        except Exception as exc:
            logger.warning("realtime_publish_failed tenant=%s error=%s", tenant_id, exc)

    async def _subscribe_loop(self, tenant_id: str) -> None:
        """Long-running task: subscribe to Redis channel for this tenant and
        forward each message to all local WS connections."""
        try:
            r = await self._redis_client()
            pubsub = r.pubsub()
            await pubsub.subscribe(_channel(tenant_id))
            logger.info("realtime_subscribed tenant=%s", tenant_id)
            async for msg in pubsub.listen():
                if msg.get("type") != "message":
                    continue
                payload = msg.get("data") or "{}"
                # Snapshot so disconnects during iteration don't break
                conns = list(self._conns.get(tenant_id, []))
                if not conns:
                    continue
                for ws in conns:
                    try:
                        await ws.send_text(payload)
                    except Exception:
                        # Client probably gone — let the WS endpoint clean it up
                        pass
        except asyncio.CancelledError:
            logger.info("realtime_subscribe_cancelled tenant=%s", tenant_id)
            raise
        except Exception as exc:
            logger.exception("realtime_subscribe_loop_failed tenant=%s error=%s", tenant_id, exc)


# Singleton per worker process
broadcaster = RealtimeBroadcaster()
