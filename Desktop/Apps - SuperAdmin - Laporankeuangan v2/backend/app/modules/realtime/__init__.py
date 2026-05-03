"""Realtime module — WebSocket endpoint + event-bus → broadcaster bridge.

Importing this module registers the bridge subscribers via side-effect.
"""

from app.modules.realtime import bridge  # noqa: F401  side-effect: subscribe
