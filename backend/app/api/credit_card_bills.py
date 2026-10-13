import uuid
from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_async_session
from app.core.workspace_context import WorkspaceContext, current_workspace
from app.schemas.account import CreditCardBillRead
from app.services import bill_service

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
