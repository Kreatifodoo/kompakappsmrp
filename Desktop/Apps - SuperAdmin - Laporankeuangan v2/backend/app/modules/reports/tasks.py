"""Celery tasks for async report generation and export."""

from __future__ import annotations

import asyncio
import json
from datetime import date
from typing import Any
from uuid import UUID

import redis as redis_lib

from app.config import settings
from app.worker.celery_app import celery_app


# ─── Redis client (sync, for task results) ───────────────────────────────────

def _redis() -> redis_lib.Redis:
    return redis_lib.from_url(settings.REDIS_URL, decode_responses=True)


JOB_TTL = 3600  # 1 hour


def _job_key(job_id: str) -> str:
    return f"report_job:{job_id}"


def _set_job(job_id: str, status: str, result: Any = None, error: str | None = None) -> None:
    r = _redis()
    payload = {"status": status}
    if result is not None:
        payload["result"] = result
    if error is not None:
        payload["error"] = error
    r.setex(_job_key(job_id), JOB_TTL, json.dumps(payload))


def get_job(job_id: str) -> dict | None:
    r = _redis()
    raw = r.get(_job_key(job_id))
    return json.loads(raw) if raw else None


# ─── Async DB helper ─────────────────────────────────────────────────────────

async def _run_report(report_type: str, tenant_id: str, params: dict) -> dict:
    """Open an async DB session and call the appropriate report service method."""
    from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
    from sqlalchemy.orm import sessionmaker

    from app.modules.reports.service import ReportsService

    engine = create_async_engine(settings.DB_PRIMARY_URL, pool_size=2, max_overflow=0)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with async_session() as session:
        svc = ReportsService(session, UUID(tenant_id))
        tid = UUID(tenant_id)

        if report_type == "trial-balance":
            as_of = date.fromisoformat(params.get("as_of", date.today().isoformat()))
            include_zero = params.get("include_zero", False)
            result = await svc.trial_balance(as_of=as_of, include_zero=include_zero)

        elif report_type == "profit-loss":
            result = await svc.profit_loss(
                date_from=date.fromisoformat(params["date_from"]),
                date_to=date.fromisoformat(params["date_to"]),
                cash_basis=params.get("cash_basis", False),
            )

        elif report_type == "balance-sheet":
            as_of = date.fromisoformat(params.get("as_of", date.today().isoformat()))
            result = await svc.balance_sheet(as_of=as_of)

        elif report_type == "aged-receivables":
            as_of = date.fromisoformat(params.get("as_of", date.today().isoformat()))
            result = await svc.aged_receivables(as_of=as_of)

        elif report_type == "aged-payables":
            as_of = date.fromisoformat(params.get("as_of", date.today().isoformat()))
            result = await svc.aged_payables(as_of=as_of)

        elif report_type == "cash-flow":
            result = await svc.cash_flow_statement(
                date_from=date.fromisoformat(params["date_from"]),
                date_to=date.fromisoformat(params["date_to"]),
            )

        elif report_type == "ppn":
            result = await svc.ppn_report(year=int(params["year"]), month=int(params["month"]))

        else:
            raise ValueError(f"Unknown report type: {report_type}")

    await engine.dispose()
    return result.model_dump(mode="json")


# ─── Celery task ─────────────────────────────────────────────────────────────

@celery_app.task(bind=True, name="reports.generate")
def generate_report_task(self, report_type: str, tenant_id: str, params: dict) -> None:
    """Run a report in the background. Result stored in Redis."""
    job_id = self.request.id
    _set_job(job_id, "running")
    try:
        result = asyncio.run(_run_report(report_type, tenant_id, params))
        _set_job(job_id, "done", result=result)
    except Exception as exc:
        _set_job(job_id, "failed", error=str(exc))
        raise


@celery_app.task(bind=True, name="reports.export")
def export_report_task(self, report_type: str, tenant_id: str, params: dict, fmt: str) -> None:
    """Generate report + export to PDF or Excel. Result bytes stored in Redis as base64."""
    import base64

    from app.modules.reports.export import export_report

    job_id = self.request.id
    _set_job(job_id, "running")
    try:
        data = asyncio.run(_run_report(report_type, tenant_id, params))
        content, filename, content_type = export_report(report_type, data, fmt)
        _set_job(job_id, "done", result={
            "filename": filename,
            "content_type": content_type,
            "data_b64": base64.b64encode(content).decode(),
        })
    except Exception as exc:
        _set_job(job_id, "failed", error=str(exc))
        raise
