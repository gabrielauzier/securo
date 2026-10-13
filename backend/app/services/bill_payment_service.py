"""Link and unlink a bill payment: a debit in a non-card account that pays a bill."""

import uuid
from dataclasses import dataclass
from datetime import timedelta
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.account import Account
from app.models.credit_card_bill import CreditCardBill
from app.models.transaction import Transaction
from app.services import bill_service, transaction_service
from app.services import reconciliation_rule_service as rule_service
from app.services.transfer_detection_service import NODE, _widest_window, unlink_transfer_pair

CENT = Decimal("0.01")


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


async def find_card_credit(
    session: AsyncSession, payment: Transaction, bill: CreditCardBill
) -> Transaction | None:
    """The unpaired credit on the bill's card with the payment's amount, inside
    the transfer rule's date window around the payment; the closest in date."""
    policy = await rule_service.resolve(session, payment.workspace_id, NODE)
    window = timedelta(days=_widest_window(policy))
    amount = abs(Decimal(payment.amount)).quantize(CENT)
    credits = (
        await session.execute(
            select(Transaction).where(
                Transaction.workspace_id == payment.workspace_id,
                Transaction.account_id == bill.account_id,
                Transaction.type == "credit",
                Transaction.transfer_pair_id.is_(None),
                func.abs(Transaction.amount) == amount,
                Transaction.date >= payment.date - window,
                Transaction.date <= payment.date + window,
            )
        )
    ).scalars().all()
    if not credits:
        return None
    return min(credits, key=lambda tx: (abs((tx.date - payment.date).days), tx.date, str(tx.id)))


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
    paired_credit_id = None
    if tx.transfer_pair_id is None:
        credit = await find_card_credit(session, tx, bill)
        if credit is not None:
            # BPAY AC 3: the payment and the card credit are the two legs of a transfer.
            await transaction_service.link_existing_as_transfer(
                session, workspace_id, [tx.id, credit.id]
            )
            tx.bill_payment_pair = True
            paired_credit_id = credit.id
    refresh = {bill.id}
    if tx.transfer_pair_id is not None:
        # The card leg, paired now or by the user before, leaves its bill's total.
        refresh |= await _pair_bill_ids(session, tx.transfer_pair_id)
    await bill_service.refresh_bills(session, refresh)
    return LinkResult(
        payment=tx,
        bill=bill,
        paired_credit_id=paired_credit_id,
        # BPAY AC 4: no card credit to pair with.
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
    refresh = {bill.id}
    if tx.transfer_pair_id is not None:
        # The card leg counts in its bill's total again.
        refresh |= await _pair_bill_ids(session, tx.transfer_pair_id)
    if tx.bill_payment_pair and tx.transfer_pair_id is not None:
        # Undo only the pair the link created, never one the user made.
        await unlink_transfer_pair(session, workspace_id, tx.transfer_pair_id)
    tx.bill_payment_pair = False
    await bill_service.refresh_bills(session, refresh)
    return bill


async def _pair_bill_ids(session: AsyncSession, pair_id: uuid.UUID) -> set[uuid.UUID]:
    rows = await session.execute(
        select(Transaction.id).where(Transaction.transfer_pair_id == pair_id)
    )
    return await bill_service.collect_bill_ids(session, [tx_id for (tx_id,) in rows])
