"""HTTP routes for Reports: trial balance, P&L, balance sheet."""

import base64
from datetime import date
from typing import Any, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_read_session
from app.core.exceptions import ValidationError
from app.deps import CurrentUser, require_permission
from app.modules.reports.schemas import (
    AgedReport,
    BalanceSheet,
    BankReconciliation,
    BankReconciliationRequest,
    CashFlowStatement,
    PPNReport,
    ProfitLoss,
    Statement,
    TrialBalance,
)
from app.modules.reports.service import ReportsService
from app.modules.reports.tasks import export_report_task, generate_report_task, get_job

router = APIRouter(prefix="/reports", tags=["reports"])


# ─── Async job schemas ────────────────────────────────────────

class AsyncReportRequest(BaseModel):
    params: dict[str, Any] = {}
    fmt: Literal["json", "excel", "pdf"] = "json"


class JobSubmitted(BaseModel):
    job_id: str
    status: str = "queued"


class JobStatus(BaseModel):
    job_id: str
    status: str
    error: str | None = None


# ─── Async job endpoints ──────────────────────────────────────

@router.post(
    "/{report_type}/async",
    response_model=JobSubmitted,
    summary="Submit a report as a background job; poll /jobs/{job_id}/status for completion",
)
async def submit_async_report(
    report_type: str,
    body: AsyncReportRequest,
    current: CurrentUser = Depends(require_permission("report.read")),
) -> JobSubmitted:
    allowed = {
        "trial-balance", "profit-loss", "balance-sheet",
        "aged-receivables", "aged-payables", "cash-flow", "ppn",
    }
    if report_type not in allowed:
        raise HTTPException(status_code=404, detail=f"Unknown report type: {report_type}")

    if body.fmt == "json":
        task = generate_report_task.delay(report_type, str(current.tenant_id), body.params)
    else:
        task = export_report_task.delay(report_type, str(current.tenant_id), body.params, body.fmt)

    return JobSubmitted(job_id=task.id)


@router.get("/jobs/{job_id}/status", response_model=JobStatus, summary="Poll async job status")
async def job_status(
    job_id: str,
    current: CurrentUser = Depends(require_permission("report.read")),
) -> JobStatus:
    job = get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found or expired")
    return JobStatus(job_id=job_id, status=job["status"], error=job.get("error"))


@router.get("/jobs/{job_id}/result", summary="Retrieve completed job result (JSON)")
async def job_result(
    job_id: str,
    current: CurrentUser = Depends(require_permission("report.read")),
) -> Any:
    job = get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found or expired")
    if job["status"] != "done":
        raise HTTPException(status_code=409, detail=f"Job status: {job['status']}")
    return job.get("result")


@router.get("/jobs/{job_id}/download", summary="Download completed export as PDF or Excel file")
async def job_download(
    job_id: str,
    format: Literal["pdf", "excel"] = Query(...),  # noqa: A002
    current: CurrentUser = Depends(require_permission("report.read")),
) -> Response:
    job = get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found or expired")
    if job["status"] != "done":
        raise HTTPException(status_code=409, detail=f"Job status: {job['status']}")
    result = job.get("result", {})
    if "data_b64" not in result:
        raise HTTPException(status_code=422, detail="Job result is not a file export")
    content = base64.b64decode(result["data_b64"])
    return Response(
        content=content,
        media_type=result.get("content_type", "application/octet-stream"),
        headers={"Content-Disposition": f'attachment; filename="{result.get("filename", "report")}"'},
    )


@router.get(
    "/trial-balance",
    response_model=TrialBalance,
    summary="Trial balance — all accounts with cumulative debit/credit through `as_of`",
)
async def trial_balance(
    as_of: date = Query(default_factory=date.today),
    include_zero: bool = Query(default=False, description="Include accounts with no activity"),
    current: CurrentUser = Depends(require_permission("report.read")),
    session: AsyncSession = Depends(get_read_session),
) -> TrialBalance:
    svc = ReportsService(session, current.tenant_id)
    return await svc.trial_balance(as_of=as_of, include_zero=include_zero)


@router.get(
    "/profit-loss",
    response_model=ProfitLoss,
    summary="Income statement for a date range",
)
async def profit_loss(
    date_from: date = Query(...),
    date_to: date = Query(...),
    cash_basis: bool = Query(
        default=False,
        description=(
            "When true, restricts to journals that touch a cash account "
            "(accounts.is_cash=true). Captures direct cash sales/purchases "
            "but NOT credit sales paid later — see README for details."
        ),
    ),
    current: CurrentUser = Depends(require_permission("report.read")),
    session: AsyncSession = Depends(get_read_session),
) -> ProfitLoss:
    if date_from > date_to:
        raise ValidationError("date_from must be <= date_to")
    svc = ReportsService(session, current.tenant_id)
    return await svc.profit_loss(date_from=date_from, date_to=date_to, cash_basis=cash_basis)


@router.get(
    "/balance-sheet",
    response_model=BalanceSheet,
    summary="Balance sheet snapshot as of `as_of` (incl. computed retained earnings)",
)
async def balance_sheet(
    as_of: date = Query(default_factory=date.today),
    current: CurrentUser = Depends(require_permission("report.read")),
    session: AsyncSession = Depends(get_read_session),
) -> BalanceSheet:
    svc = ReportsService(session, current.tenant_id)
    return await svc.balance_sheet(as_of=as_of)


@router.get(
    "/aged-receivables",
    response_model=AgedReport,
    summary="Aged AR — outstanding sales invoices bucketed by days overdue",
)
async def aged_receivables(
    as_of: date = Query(default_factory=date.today),
    current: CurrentUser = Depends(require_permission("report.read")),
    session: AsyncSession = Depends(get_read_session),
) -> AgedReport:
    svc = ReportsService(session, current.tenant_id)
    return await svc.aged_receivables(as_of=as_of)


@router.get(
    "/aged-payables",
    response_model=AgedReport,
    summary="Aged AP — outstanding purchase invoices bucketed by days overdue",
)
async def aged_payables(
    as_of: date = Query(default_factory=date.today),
    current: CurrentUser = Depends(require_permission("report.read")),
    session: AsyncSession = Depends(get_read_session),
) -> AgedReport:
    svc = ReportsService(session, current.tenant_id)
    return await svc.aged_payables(as_of=as_of)


@router.get(
    "/customer-statement/{customer_id}",
    response_model=Statement,
    summary="Per-customer statement: chronological invoices + receipts with running balance",
)
async def customer_statement(
    customer_id: UUID,
    date_from: date = Query(...),
    date_to: date = Query(...),
    current: CurrentUser = Depends(require_permission("report.read")),
    session: AsyncSession = Depends(get_read_session),
) -> Statement:
    if date_from > date_to:
        raise ValidationError("date_from must be <= date_to")
    svc = ReportsService(session, current.tenant_id)
    return await svc.customer_statement(customer_id=customer_id, date_from=date_from, date_to=date_to)


@router.get(
    "/supplier-statement/{supplier_id}",
    response_model=Statement,
    summary="Per-supplier statement: chronological purchases + disbursements with running balance",
)
async def supplier_statement(
    supplier_id: UUID,
    date_from: date = Query(...),
    date_to: date = Query(...),
    current: CurrentUser = Depends(require_permission("report.read")),
    session: AsyncSession = Depends(get_read_session),
) -> Statement:
    if date_from > date_to:
        raise ValidationError("date_from must be <= date_to")
    svc = ReportsService(session, current.tenant_id)
    return await svc.supplier_statement(supplier_id=supplier_id, date_from=date_from, date_to=date_to)


@router.post(
    "/bank-reconciliation",
    response_model=BankReconciliation,
    summary="Match a bank statement against the book entries on a cash account",
)
async def bank_reconciliation(
    payload: BankReconciliationRequest,
    current: CurrentUser = Depends(require_permission("report.read")),
    session: AsyncSession = Depends(get_read_session),
) -> BankReconciliation:
    if payload.date_from > payload.date_to:
        raise ValidationError("date_from must be <= date_to")
    svc = ReportsService(session, current.tenant_id)
    return await svc.bank_reconciliation(payload)


@router.get(
    "/ppn",
    response_model=PPNReport,
    summary="Indonesian VAT (PPN) report — monthly output vs input VAT",
)
async def ppn_report(
    year: int = Query(..., ge=2000, le=2100),
    month: int = Query(..., ge=1, le=12),
    current: CurrentUser = Depends(require_permission("report.read")),
    session: AsyncSession = Depends(get_read_session),
) -> PPNReport:
    svc = ReportsService(session, current.tenant_id)
    return await svc.ppn_report(year=year, month=month)


@router.get(
    "/cash-flow",
    response_model=CashFlowStatement,
    summary=(
        "Indirect-method Statement of Cash Flows for a date range. "
        "Accounts must have cf_section set (operating/investing/financing) "
        "to appear in the report."
    ),
)
async def cash_flow_statement(
    date_from: date = Query(..., description="Period start (inclusive)"),
    date_to: date = Query(..., description="Period end (inclusive)"),
    current: CurrentUser = Depends(require_permission("report.read")),
    session: AsyncSession = Depends(get_read_session),
) -> CashFlowStatement:
    if date_from > date_to:
        raise ValidationError("date_from must not be after date_to")
    svc = ReportsService(session, current.tenant_id)
    return await svc.cash_flow_statement(date_from=date_from, date_to=date_to)
