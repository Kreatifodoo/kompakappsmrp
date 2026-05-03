"""Email notifications module.

Sends transactional emails via SMTP through Celery (async).
Triggers via the in-process event bus (app.core.events.publish).

Auto-loads subscribers when the module is imported.
"""

from app.modules.notifications import subscribers  # noqa: F401  side-effect: register
