"""WebSocket endpoint: /api/v1/ws?token=<JWT>.

Per-tenant fan-out using app.core.realtime.broadcaster.
"""

from __future__ import annotations

import asyncio
import json
import logging
from uuid import UUID

from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect, status
from jose import JWTError

from app.core.realtime import broadcaster
from app.core.security import decode_access_token

logger = logging.getLogger(__name__)
router = APIRouter(tags=["realtime"])


def _decode_jwt_to_tenant(token: str) -> tuple[UUID, UUID] | None:
    """Validate a JWT and return (user_id, tenant_id) — or None if invalid."""
    try:
        payload = decode_access_token(token)
    except JWTError:
        return None
    if payload.get("type") != "access":
        return None
    tid = payload.get("tid")
    sub = payload.get("sub")
    if not tid or not sub:
        return None
    try:
        return UUID(sub), UUID(tid)
    except (ValueError, TypeError):
        return None


@router.websocket("/ws")
async def realtime_ws(
    websocket: WebSocket,
    token: str = Query(..., description="Bearer JWT access token"),
) -> None:
    """Tenant-scoped WebSocket. Client passes JWT via ?token=. After accept
    we forward all events on this tenant's Redis channel to the client."""
    auth = _decode_jwt_to_tenant(token)
    if not auth:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    user_id, tenant_id = auth
    await websocket.accept()
    await broadcaster.connect(websocket, tenant_id)

    # Send a hello so client knows the link is live
    try:
        await websocket.send_text(json.dumps({
            "type": "connected",
            "data": {"user_id": str(user_id), "tenant_id": str(tenant_id)},
        }))
    except Exception:
        pass

    # Heartbeat task: ping every 30s so idle connections don't die
    async def _heartbeat() -> None:
        try:
            while True:
                await asyncio.sleep(30)
                await websocket.send_text(json.dumps({"type": "ping"}))
        except Exception:
            pass

    hb_task = asyncio.create_task(_heartbeat())

    try:
        # Drain incoming messages (mostly ignored; client may send pongs)
        while True:
            msg = await websocket.receive_text()
            # Client-initiated commands could go here. For now just log pings.
            try:
                obj = json.loads(msg)
                if obj.get("type") == "pong":
                    continue
            except Exception:
                pass
    except WebSocketDisconnect:
        pass
    except Exception as exc:
        logger.warning("ws_unexpected_error tenant=%s err=%s", tenant_id, exc)
    finally:
        hb_task.cancel()
        await broadcaster.disconnect(websocket, tenant_id)
