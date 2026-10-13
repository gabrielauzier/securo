"""Deleting a user refreshes the shared bills their rows paid (BPAY-01, AD-004).

- WHEN a linked payment transaction is deleted THEN the system SHALL drop the link
  and recompute the bill status (here: deleted with the user who owns it, while
  the card and its bill belong to another member of the shared workspace).
"""

import uuid
from datetime import date
from decimal import Decimal

import pytest

from app.models.credit_card_bill import CreditCardBill
from app.models.user import User
from app.services import admin_service, bill_payment_service, bill_service
from tests.test_credit_card_bills_api import SEP, _bill, _card, _checking, _tx

TODAY = date(2026, 9, 14)  # effective due date of the 2026-09 bill (close 5, due 12)


@pytest.fixture(autouse=True)
def _today(monkeypatch):
    monkeypatch.setattr("app.services.bill_service.app_today", lambda: TODAY)


async def test_deleting_the_paying_user_unpays_the_other_users_bill(
    session, test_user, test_workspace
):
    # User B (test_user) owns the card and its bill; user A pays it from A's checking.
    payer = User(
        id=uuid.uuid4(), email="payer@example.com", hashed_password="x",
        is_active=True, is_superuser=False, is_verified=True,
    )
    session.add(payer)
    await session.commit()
    card = await _card(session, test_user, test_workspace)
    checking = await _checking(session, payer, test_workspace)
    bill = await _bill(session, card, SEP)
    purchase = _tx(card, date(2026, 9, 1), "100.00", bill_id=bill.id)
    payment = _tx(checking, TODAY, "100.00", description="PAGAMENTO FATURA")
    session.add_all([purchase, payment])
    await session.commit()
    await bill_payment_service.link_payment(session, test_workspace.id, payment.id, bill.id)
    await session.commit()
    bill_id = bill.id
    assert bill.paid_amount == Decimal("100.00")
    assert bill_service.bill_status(bill, TODAY) == "paid"

    assert await admin_service.delete_user(session, payer.id, test_user.id) is True

    session.expire_all()
    bill = await session.get(CreditCardBill, bill_id)
    assert bill.paid_amount == Decimal("0.00")
    assert bill.settled_on is None
    assert bill_service.bill_status(bill, TODAY) == "closed"
