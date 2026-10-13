"""Deleting an account keeps the bills consistent (BPAY-01 edge cases, AD-004).

- WHEN a linked payment transaction is deleted THEN the system SHALL drop the link
  and recompute the bill status (here: deleted with its account).
- WHEN a card account is deleted THEN the system SHALL delete its bills and unlink
  their payments.
"""

from datetime import date
from decimal import Decimal

import pytest
import pytest_asyncio
from sqlalchemy import select

from app.models.credit_card_bill import CreditCardBill
from app.models.transaction import Transaction
from app.services import account_service, bill_payment_service, bill_service
from tests.test_credit_card_bills_api import SEP, _bill, _card, _checking, _tx

TODAY = date(2026, 9, 14)  # effective due date of the 2026-09 bill (close 5, due 12)


@pytest.fixture(autouse=True)
def _today(monkeypatch):
    monkeypatch.setattr("app.services.bill_service.app_today", lambda: TODAY)


async def _paid_reference(session, user, workspace):
    """A 2026-09 bill of 100.00 fully paid by a checking payment paired with the card credit."""
    card = await _card(session, user, workspace)
    checking = await _checking(session, user, workspace)
    bill = await _bill(session, card, SEP)
    purchase = _tx(card, date(2026, 9, 1), "100.00", bill_id=bill.id)
    credit = _tx(card, TODAY, "100.00", type_="credit", description="PAGAMENTO RECEBIDO")
    payment = _tx(checking, TODAY, "100.00", description="PAGAMENTO FATURA")
    session.add_all([purchase, credit, payment])
    await session.commit()
    result = await bill_payment_service.link_payment(session, workspace.id, payment.id, bill.id)
    await session.commit()
    assert result.paired_credit_id == credit.id
    assert bill_service.bill_status(bill, TODAY) == "paid"
    return card, checking, bill, credit, payment


async def test_deleting_the_paying_account_unpays_the_bill(session, test_user, test_workspace):
    card, checking, bill, credit, _ = await _paid_reference(session, test_user, test_workspace)
    bill_id, credit_id = bill.id, credit.id

    assert await account_service.delete_account(session, checking.id, test_workspace.id) is True

    session.expire_all()
    bill = await session.get(CreditCardBill, bill_id)
    assert bill.paid_amount == Decimal("0.00")
    assert bill.settled_on is None
    assert bill_service.bill_status(bill, TODAY) == "closed"
    # The pair the link created goes with the payment (BPAY AC 9).
    assert (await session.get(Transaction, credit_id)).transfer_pair_id is None


class TestCardDeletionOnPostgres:
    """SQLite does not enforce foreign keys, so the card deletion runs on PostgreSQL."""

    @pytest_asyncio.fixture
    async def session(self, postgres_sessions):
        async with postgres_sessions() as session:
            yield session
            await session.rollback()

    @pytest.fixture
    def clean_db(self, postgres_sessions):
        """Each test starts in a fresh PostgreSQL schema."""

    async def test_deleting_a_card_deletes_its_bills_and_unlinks_their_payments(
        self, session, test_user, test_workspace
    ):
        card, _, _, _, payment = await _paid_reference(session, test_user, test_workspace)
        card_id, payment_id = card.id, payment.id

        assert await account_service.delete_account(session, card_id, test_workspace.id) is True

        session.expire_all()
        bills = (
            await session.execute(
                select(CreditCardBill.id).where(CreditCardBill.account_id == card_id)
            )
        ).all()
        assert bills == []
        payment = await session.get(Transaction, payment_id)
        assert payment is not None
        assert payment.paid_bill_id is None
        assert payment.bill_payment_pair is False
        assert payment.transfer_pair_id is None
