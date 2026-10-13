"""BIMP-01 / AD-004: recurring charges generated on a card land on their bill."""

import uuid
from datetime import date
from decimal import Decimal

from sqlalchemy import select

from app.models.account import Account
from app.models.credit_card_bill import CreditCardBill
from app.models.recurring_transaction import RecurringTransaction
from app.models.transaction import Transaction
from app.services.recurring_transaction_service import generate_pending


async def test_generated_card_charges_join_the_bill_of_their_date(session, test_user, test_workspace):
    # Card close 5, due 12: 2026-08-10 -> bill 2026-09, 2026-09-10 -> bill 2026-10.
    card = Account(
        id=uuid.uuid4(), user_id=test_user.id, workspace_id=test_workspace.id,
        name="Cartão de Crédito Nubank", type="credit_card", currency="BRL",
        statement_close_day=5, payment_due_day=12,
    )
    session.add(card)
    session.add(
        RecurringTransaction(
            id=uuid.uuid4(), user_id=test_user.id, workspace_id=test_workspace.id,
            account_id=card.id, description="Streaming", amount=Decimal("39.90"),
            currency="BRL", type="debit", frequency="monthly", start_date=date(2026, 8, 10),
            next_occurrence=date(2026, 8, 10), day_of_month=10,
        )
    )
    await session.commit()

    assert await generate_pending(session, test_user.id, up_to=date(2026, 9, 15)) == 2

    bills = {
        b.reference_month: b
        for b in (
            await session.execute(select(CreditCardBill).where(CreditCardBill.account_id == card.id))
        ).scalars()
    }
    rows = (
        await session.execute(
            select(Transaction).where(Transaction.account_id == card.id).order_by(Transaction.date)
        )
    ).scalars().all()
    assert sorted(bills) == [date(2026, 9, 1), date(2026, 10, 1)]
    assert [r.bill_id for r in rows] == [bills[date(2026, 9, 1)].id, bills[date(2026, 10, 1)].id]
    assert bills[date(2026, 9, 1)].source == "auto"
    assert bills[date(2026, 9, 1)].computed_total == Decimal("39.90")
    assert bills[date(2026, 10, 1)].computed_total == Decimal("39.90")
