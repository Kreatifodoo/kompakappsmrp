"""Celery application instance.

Tasks live next to their owning module under app/modules/<x>/tasks.py and
are auto-discovered via `celery_app.autodiscover_tasks`.
"""
from celery import Celery

from app.config import settings

celery_app = Celery(
    "kompak",
    broker=settings.REDIS_CELERY_BROKER,
    backend=settings.REDIS_CELERY_BACKEND,
)

celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    enable_utc=True,
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    task_time_limit=600,        # 10 min hard
    task_soft_time_limit=540,   # 9 min soft
)

# Auto-discover tasks in modules: app.modules.<name>.tasks
celery_app.autodiscover_tasks(
    [
        "app.modules.identity",
        "app.modules.accounting",
    ]
)
