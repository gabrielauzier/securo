import uuid
from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_async_session
from app.core.workspace_context import (
    WorkspaceContext,
    current_workspace,
    current_writable_workspace,
)
from app.schemas.account import (
    BillPaymentLink,
    BillPaymentLinkRead,
    CreditCardBillCreate,
    CreditCardBillRead,
    CreditCardBillUpdate,
)
from app.services import bill_payment_service, bill_service

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
