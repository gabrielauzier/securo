"""BILL-01 / AD-004: deleting a category and moving its rows refreshes their bills."""

import uuid
from datetime import date
from decimal import Decimal

from app.models.account import Account
from app.models.category import Category
from app.models.transaction import Transaction
from app.services import bill_service, category_service
from app.services.credit_card_service import bill_period_for_month


async def _bill_with_purchase(session, user, workspace, category):
    card = Account(
        id=uuid.uuid4(), user_id=user.id, workspace_id=workspace.id,
        name="Cartão de Crédito Nubank", type="credit_card", currency="BRL",
        statement_close_day=5, payment_due_day=12,
    )
    session.add(card)
    await session.flush()
    bill, _ = await bill_service.get_or_create_bill(
        session, card, bill_period_for_month(date(2026, 9, 1), 5, 12)
    )
    session.add(Transaction(
        id=uuid.uuid4(), user_id=user.id, workspace_id=workspace.id, account_id=card.id,
        description="Compra", amount=Decimal("100.00"), currency="BRL", date=date(2026, 8, 20),
        effective_date=date(2026, 8, 20), type="debit", source="manual",
        category_id=category.id, bill_id=bill.id,
    ))
    await bill_service.refresh_bills(session, [bill.id])
    await session.commit()
    return bill


async def _categories(session, user, workspace):
    ignored = Category(
        id=uuid.uuid4(), user_id=user.id, workspace_id=workspace.id,
        name="Ignorada", is_ignored=True,
    )
    market = Category(
        id=uuid.uuid4(), user_id=user.id, workspace_id=workspace.id, name="Mercado",
    )
    session.add_all([ignored, market])
    await session.commit()
    return ignored, market


async def test_moving_rows_out_of_an_ignored_category_raises_the_bill_total(
    session, test_user, test_workspace
):
    ignored, market = await _categories(session, test_user, test_workspace)
    bill = await _bill_with_purchase(session, test_user, test_workspace, ignored)
    assert bill.computed_total == Decimal("0.00")

    deleted = await category_service.delete_category(
        session, ignored.id, test_workspace.id, transfer_to_id=market.id
    )

    assert deleted is True
    await session.refresh(bill)
    assert bill.computed_total == Decimal("100.00")


async def test_moving_rows_into_an_ignored_category_lowers_the_bill_total(
    session, test_user, test_workspace
):
    ignored, market = await _categories(session, test_user, test_workspace)
    bill = await _bill_with_purchase(session, test_user, test_workspace, market)
    assert bill.computed_total == Decimal("100.00")

    deleted = await category_service.delete_category(
        session, market.id, test_workspace.id, transfer_to_id=ignored.id
    )

    assert deleted is True
    await session.refresh(bill)
    assert bill.computed_total == Decimal("0.00")
