"""HTTP routes for Reports: trial balance, P&L, balance sheet."""

from datetime import date
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_read_session
from app.core.exceptions import ValidationError
from app.deps import CurrentUser, require_permission
from app.modules.reports.schemas import (
    AgedReport,
    BalanceSheet,
    BankReconciliation,
    BankReconciliationRequest,
    ProfitLoss,
    Statement,
    TrialBalance,
)
from app.modules.reports.service import ReportsService

router = APIRouter(prefix="/reports", tags=["reports"])


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
