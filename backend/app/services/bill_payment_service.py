"""Link and unlink a bill payment: a debit in a non-card account that pays a bill."""

import uuid
from dataclasses import dataclass
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.account import Account
from app.models.credit_card_bill import CreditCardBill
from app.models.transaction import Transaction
from app.services import bill_service


class BillPaymentError(Exception):
    """A payment link the service refuses; `status_code` is the HTTP answer."""

    def __init__(self, status_code: int, detail: str) -> None:
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail


@dataclass(frozen=True)
class LinkResult:
    payment: Transaction
    bill: CreditCardBill
    paired_credit_id: uuid.UUID | None
    needs_counterpart: bool


def validate_payment(tx: Transaction, account: Account, bill: CreditCardBill) -> None:
    """Raise unless `tx` may pay `bill` (BPAY AC 10, 11 and the amount edge case)."""
    if tx.paid_bill_id is not None and tx.paid_bill_id != bill.id:
        raise BillPaymentError(409, "The transaction already pays another bill")
    if tx.type != "debit":
        raise BillPaymentError(422, "A bill payment must be a debit")
    if account.type == "credit_card":
        raise BillPaymentError(422, "A bill payment cannot come from a credit card account")
    if tx.is_ignored:
        raise BillPaymentError(422, "An ignored transaction cannot pay a bill")
    if tx.status != "posted":
        raise BillPaymentError(422, "A pending transaction cannot pay a bill")
    if tx.currency != bill.currency:
        raise BillPaymentError(422, "The payment and the bill have different currencies")
    if Decimal(tx.amount) <= 0:
        raise BillPaymentError(422, "A bill payment must have a positive amount")


async def _transaction(
    session: AsyncSession, workspace_id: uuid.UUID, transaction_id: uuid.UUID
) -> Transaction:
    tx = (
        await session.execute(
            select(Transaction).where(
                Transaction.id == transaction_id, Transaction.workspace_id == workspace_id
            )
        )
    ).scalar_one_or_none()
    if tx is None:
        raise BillPaymentError(404, "Transaction not found")
    return tx


async def link_payment(
    session: AsyncSession,
    workspace_id: uuid.UUID,
    transaction_id: uuid.UUID,
    bill_id: uuid.UUID,
) -> LinkResult:
    """Record that the transaction pays the bill and refresh the bill (BPAY AC 1)."""
    bill = await bill_service.get_bill(session, workspace_id, bill_id)
    if bill is None:
        raise BillPaymentError(404, "Bill not found")
    tx = await _transaction(session, workspace_id, transaction_id)
    account = await session.get(Account, tx.account_id)
    if account is None:
        raise BillPaymentError(404, "Transaction not found")
    validate_payment(tx, account, bill)
    tx.paid_bill_id = bill.id
    await bill_service.refresh_bills(session, [bill.id])
    return LinkResult(
        payment=tx,
        bill=bill,
        paired_credit_id=None,
        needs_counterpart=tx.transfer_pair_id is None,
    )


async def unlink_payment(
    session: AsyncSession, workspace_id: uuid.UUID, transaction_id: uuid.UUID
) -> CreditCardBill:
    """Remove the payment link and refresh the bill it paid (BPAY AC 9)."""
    tx = await _transaction(session, workspace_id, transaction_id)
    if tx.paid_bill_id is None:
        raise BillPaymentError(404, "The transaction pays no bill")
    bill = await bill_service.get_bill(session, workspace_id, tx.paid_bill_id)
    if bill is None:
        raise BillPaymentError(404, "Bill not found")
    tx.paid_bill_id = None
    await bill_service.refresh_bills(session, [bill.id])
    return bill
