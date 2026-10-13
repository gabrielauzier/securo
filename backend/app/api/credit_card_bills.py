import uuid
from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_async_session
from app.core.workspace_context import (
    WorkspaceContext,
    current_workspace,
    current_writable_workspace,
)
from app.models.account import Account
from app.models.transaction import Transaction
from app.schemas.account import (
    BillCandidateRead,
    BillMatchApply,
    BillMatchApplyRead,
    BillMatchPair,
    BillMatchProposalRead,
    BillPaymentLink,
    BillPaymentLinkRead,
    CreditCardBillCreate,
    CreditCardBillRead,
    CreditCardBillUpdate,
)
from app.services import bill_match_service, bill_payment_service, bill_service

router = APIRouter(prefix="/api/credit-card-bills", tags=["credit-card-bills"])


def _parse_month(value: Optional[str]) -> Optional[date]:
    if value is None:
        return None
    try:
        year, month = value.split("-")
        return date(int(year), int(month), 1)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="reference_month must be YYYY-MM",
        )


def _http_error(
    exc: bill_service.BillError | bill_payment_service.BillPaymentError,
) -> HTTPException:
    return HTTPException(status_code=exc.status_code, detail=exc.detail)


@router.get("", response_model=list[CreditCardBillRead])
async def list_bills(
    reference_month: Optional[str] = Query(None, description="YYYY-MM"),
    account_id: Optional[uuid.UUID] = None,
    ctx: WorkspaceContext = Depends(current_workspace),
    session: AsyncSession = Depends(get_async_session),
):
    bills = await bill_service.list_bills(
        session, ctx.workspace.id,
        reference_month=_parse_month(reference_month), account_id=account_id,
    )
    return await bill_service.describe_bills(session, bills)


async def _account_names(session: AsyncSession, workspace_id: uuid.UUID) -> dict[uuid.UUID, str]:
    rows = await session.execute(
        select(Account.id, Account.name).where(Account.workspace_id == workspace_id)
    )
    return {account_id: name for account_id, name in rows}


# Static paths are declared before `/{bill_id}` so they are not read as a bill id.


@router.get("/payment-candidates", response_model=list[BillCandidateRead])
async def payment_candidates(
    transaction_id: uuid.UUID,
    ctx: WorkspaceContext = Depends(current_workspace),
    session: AsyncSession = Depends(get_async_session),
):
    """The bills a payment may pay: candidates first, then the other unpaid bills."""
    payment = (
        await session.execute(
            select(Transaction).where(
                Transaction.id == transaction_id, Transaction.workspace_id == ctx.workspace.id
            )
        )
    ).scalar_one_or_none()
    if payment is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Transaction not found")
    candidates = await bill_match_service.candidates_for(session, payment)
    names = await _account_names(session, ctx.workspace.id)
    return [
        {
            "bill_id": c.bill.id,
            "account_id": c.bill.account_id,
            "account_name": names.get(c.bill.account_id, ""),
            "reference_month": c.bill.reference_month,
            "effective_due_date": c.bill.effective_due_date,
            "target_amount": float(bill_service.bill_amounts(c.bill).target),
            "remaining_amount": float(bill_service.bill_amounts(c.bill).remaining),
            "currency": c.bill.currency,
            "kind": c.kind,
            "reason": c.reason,
            "rank": c.rank,
        }
        for c in candidates
    ]


@router.get("/payment-matches/preview", response_model=list[BillMatchProposalRead])
async def preview_payment_matches(
    ctx: WorkspaceContext = Depends(current_workspace),
    session: AsyncSession = Depends(get_async_session),
):
    """Every proposed payment-bill link; writes nothing (BMATCH AC 10)."""
    proposals = await bill_match_service.propose_matches(session, ctx.workspace.id)
    names = await _account_names(session, ctx.workspace.id)
    return [
        {
            "transaction_id": p.payment.id,
            "bill_id": p.bill.id,
            "kind": p.kind,
            "reason": p.reason,
            "payment_account_id": p.payment.account_id,
            "payment_account_name": names.get(p.payment.account_id, ""),
            "payment_date": p.payment.date,
            "payment_description": p.payment.description,
            "payment_amount": float(abs(p.payment.amount)),
            "bill_account_id": p.bill.account_id,
            "bill_account_name": names.get(p.bill.account_id, ""),
            "reference_month": p.bill.reference_month,
            "effective_due_date": p.bill.effective_due_date,
            "remaining_amount": float(bill_service.bill_amounts(p.bill).remaining),
            "currency": p.bill.currency,
        }
        for p in proposals
    ]


@router.post("/payment-matches/apply", response_model=BillMatchApplyRead)
async def apply_payment_matches(
    data: BillMatchApply,
    ctx: WorkspaceContext = Depends(current_writable_workspace),
    session: AsyncSession = Depends(get_async_session),
):
    """Link the checked pairs; report the ones that failed (BMATCH AC 11)."""
    result = await bill_match_service.apply_matches(
        session, ctx.workspace.id, [(p.transaction_id, p.bill_id) for p in data.pairs]
    )
    await session.commit()
    return {
        "linked": result.linked,
        "failed": [
            {"transaction_id": tx_id, "bill_id": bill_id, "reason": reason}
            for tx_id, bill_id, reason in result.failed
        ],
    }


@router.post("/payment-suggestions/dismiss", status_code=status.HTTP_204_NO_CONTENT)
async def dismiss_payment_suggestion(
    data: BillMatchPair,
    ctx: WorkspaceContext = Depends(current_writable_workspace),
    session: AsyncSession = Depends(get_async_session),
):
    """Never suggest this payment-bill pair again (BMATCH AC 9)."""
    try:
        await bill_match_service.dismiss(session, ctx.workspace.id, data.transaction_id, data.bill_id)
    except bill_payment_service.BillPaymentError as exc:
        await session.rollback()
        raise _http_error(exc)
    await session.commit()


@router.get("/{bill_id}", response_model=CreditCardBillRead)
async def get_bill(
    bill_id: uuid.UUID,
    ctx: WorkspaceContext = Depends(current_workspace),
    session: AsyncSession = Depends(get_async_session),
):
    bill = await bill_service.get_bill(session, ctx.workspace.id, bill_id)
    if bill is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Bill not found")
    return (await bill_service.describe_bills(session, [bill]))[0]


@router.post("", response_model=CreditCardBillRead, status_code=status.HTTP_201_CREATED)
async def create_bill(
    data: CreditCardBillCreate,
    ctx: WorkspaceContext = Depends(current_writable_workspace),
    session: AsyncSession = Depends(get_async_session),
):
    try:
        bill = await bill_service.create_manual_bill(
            session, ctx.workspace.id, data.account_id,
            reference_month=data.reference_month, close_date=data.close_date,
            due_date=data.due_date, declared_total=data.declared_total,
        )
    except bill_service.BillError as exc:
        await session.rollback()
        raise _http_error(exc)
    await session.commit()
    return (await bill_service.describe_bills(session, [bill]))[0]


@router.patch("/{bill_id}", response_model=CreditCardBillRead)
async def update_bill(
    bill_id: uuid.UUID,
    data: CreditCardBillUpdate,
    ctx: WorkspaceContext = Depends(current_writable_workspace),
    session: AsyncSession = Depends(get_async_session),
):
    try:
        bill = await bill_service.update_bill(
            session, ctx.workspace.id, bill_id, data.model_dump(exclude_unset=True)
        )
    except bill_service.BillError as exc:
        await session.rollback()
        raise _http_error(exc)
    await session.commit()
    return (await bill_service.describe_bills(session, [bill]))[0]


@router.delete("/{bill_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_bill(
    bill_id: uuid.UUID,
    ctx: WorkspaceContext = Depends(current_writable_workspace),
    session: AsyncSession = Depends(get_async_session),
):
    try:
        await bill_service.delete_bill(session, ctx.workspace.id, bill_id)
    except bill_service.BillError as exc:
        await session.rollback()
        raise _http_error(exc)
    await session.commit()


@router.post("/{bill_id}/payments", response_model=BillPaymentLinkRead)
async def link_payment(
    bill_id: uuid.UUID,
    data: BillPaymentLink,
    ctx: WorkspaceContext = Depends(current_writable_workspace),
    session: AsyncSession = Depends(get_async_session),
):
    try:
        result = await bill_payment_service.link_payment(
            session, ctx.workspace.id, data.transaction_id, bill_id
        )
    except bill_payment_service.BillPaymentError as exc:
        await session.rollback()
        raise _http_error(exc)
    await session.commit()
    return {
        "transaction_id": result.payment.id,
        "bill": (await bill_service.describe_bills(session, [result.bill]))[0],
        "paired_credit_id": result.paired_credit_id,
        "needs_counterpart": result.needs_counterpart,
    }


@router.delete("/payments/{transaction_id}", response_model=CreditCardBillRead)
async def unlink_payment(
    transaction_id: uuid.UUID,
    ctx: WorkspaceContext = Depends(current_writable_workspace),
    session: AsyncSession = Depends(get_async_session),
):
    try:
        bill = await bill_payment_service.unlink_payment(session, ctx.workspace.id, transaction_id)
    except bill_payment_service.BillPaymentError as exc:
        await session.rollback()
        raise _http_error(exc)
    await session.commit()
    return (await bill_service.describe_bills(session, [bill]))[0]
