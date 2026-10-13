from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from app.core.database import get_async_session
from app.core.workspace_context import (
    WorkspaceContext,
    current_workspace,
    current_writable_workspace,
)
from app.models.import_log import ImportLog
from app.models.transaction import Transaction
from app.schemas.import_log import ImportLogRead
from app.services import asset_import_service, bill_service
from app.services.transfer_detection_service import unlink_transfer_pair

router = APIRouter(prefix="/api/import-logs", tags=["import-logs"])


@router.get("", response_model=list[ImportLogRead])
async def list_import_logs(
    ctx: WorkspaceContext = Depends(current_workspace),
    session: AsyncSession = Depends(get_async_session),
):
    result = await session.execute(
        select(ImportLog)
        .options(joinedload(ImportLog.account))
        .where(ImportLog.workspace_id == ctx.workspace.id)
        .order_by(ImportLog.created_at.desc())
    )
    logs = result.scalars().unique().all()
    return [
        ImportLogRead(
            id=log.id,
            user_id=log.user_id,
            account_id=log.account_id,
            account_name=log.account.name if log.account else None,
            account_currency=log.account.currency if log.account else None,
            entity=log.entity,
            filename=log.filename,
            format=log.format,
            transaction_count=log.transaction_count,
            total_credit=log.total_credit,
            total_debit=log.total_debit,
            created_at=log.created_at,
        )
        for log in logs
    ]


@router.delete("/{import_log_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_import_log(
    import_log_id: str,
    ctx: WorkspaceContext = Depends(current_writable_workspace),
    session: AsyncSession = Depends(get_async_session),
):
    import uuid as _uuid
    log_id = _uuid.UUID(import_log_id)

    result = await session.execute(
        select(ImportLog).where(
            ImportLog.id == log_id, ImportLog.workspace_id == ctx.workspace.id
        )
    )
    log = result.scalar_one_or_none()
    if not log:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Import log not found")

    if log.entity == "asset_orders":
        # Orders derive a position, so undoing them is more than a delete:
        # the service recomputes what is left and drops holdings the import
        # itself created.
        await asset_import_service.undo_import(session, ctx.workspace.id, log)
        return

    # Clean up attachment files before deleting transactions
    from app.services.attachment_service import cleanup_attachment_files
    tx_result = await session.execute(
        select(Transaction.id).where(Transaction.import_id == log_id)
    )
    tx_ids = [row[0] for row in tx_result.all()]
    await cleanup_attachment_files(session, tx_ids)

    # Also delete attachment DB records (raw SQL delete bypasses ORM cascade)
    from app.models.transaction_attachment import TransactionAttachment
    if tx_ids:
        await session.execute(
            delete(TransactionAttachment).where(
                TransactionAttachment.transaction_id.in_(tx_ids)
            )
        )

    # Bills the rows belong to or pay are refreshed after the delete (AD-004).
    bill_ids = await bill_service.collect_bill_ids(session, tx_ids)
    # A deleted payment takes the transfer pair its bill link created with it (BPAY AC 9).
    pair_ids = (
        await session.execute(
            select(Transaction.transfer_pair_id).where(
                Transaction.import_id == log_id,
                Transaction.bill_payment_pair.is_(True),
                Transaction.transfer_pair_id.is_not(None),
            )
        )
    ).scalars().all()
    for pair_id in pair_ids:
        if pair_id is not None:
            await unlink_transfer_pair(session, ctx.workspace.id, pair_id)

    # Delete all transactions from this import
    await session.execute(
        delete(Transaction).where(Transaction.import_id == log_id)
    )
    await bill_service.refresh_bills(session, bill_ids)
    await session.delete(log)
    await session.commit()
