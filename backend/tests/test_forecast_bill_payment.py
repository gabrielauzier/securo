"""BPAY-03 AC 13 and BPAY-01 AC 2 in the forecast: a bill payment that has not
posted yet never adds to projected expenses, in every accounting mode.

The September dashboard of a checking account holds a 100.00 pending grocery
purchase, which is a projected expense, and the reference 1,283.20 bill
payment, either pending in a category flagged `is_bill_payment` or dated after
today and linked to the card's bill.
"""

import uuid
from datetime import date

import pytest

from app.models.account import Account
from app.models.category import Category
from app.services import bill_service, dashboard_service
from app.services.credit_card_service import bill_period_for_month
from tests.settlement_fixtures import SEP, freeze_today, set_mode, tx

MODES = ["cash", "accrual", "settlement"]


def _pending(row):
    row.status = "pending"
    return row


async def _seed(session, user, workspace):
    market = Category(id=uuid.uuid4(), user_id=user.id, workspace_id=workspace.id, name="Mercado")
    bill_payment = Category(
        id=uuid.uuid4(), user_id=user.id, workspace_id=workspace.id,
        name="Pagamento de fatura", is_bill_payment=True,
    )
    checking = Account(
        id=uuid.uuid4(), user_id=user.id, workspace_id=workspace.id,
        name="Nubank", type="checking", currency="BRL",
    )
    card = Account(
        id=uuid.uuid4(), user_id=user.id, workspace_id=workspace.id,
        name="Cartão de Crédito Nubank", type="credit_card", currency="BRL",
        statement_close_day=5, payment_due_day=12,
    )
    session.add_all([market, bill_payment, checking, card])
    await session.flush()
    bill, _ = await bill_service.get_or_create_bill(
        session, card, bill_period_for_month(SEP, 5, 12)
    )
    session.add(_pending(tx(checking, date(2026, 9, 3), "100.00", category_id=market.id)))
    await session.commit()
    return checking, bill_payment, bill


async def _projected(session, workspace, user):
    summary = await dashboard_service.get_summary(session, workspace.id, user.id, month=SEP)
    return summary.projected_expenses, summary.projected_expenses_primary


@pytest.mark.parametrize("mode", MODES)
async def test_pending_payment_in_bill_payment_category_is_not_projected(
    monkeypatch, session, test_user, test_workspace, mode
):
    """AC 13: the pending 1,283.20 'Pagamento de fatura' leaves the forecast at 100.00."""
    freeze_today(monkeypatch, date(2026, 9, 10))
    await set_mode(session, mode)
    checking, bill_payment, _ = await _seed(session, test_user, test_workspace)

    assert await _projected(session, test_workspace, test_user) == (100.0, 100.0)

    session.add(
        _pending(
            tx(
                checking, date(2026, 9, 14), "1283.20", category_id=bill_payment.id,
                description="Pagamento de fatura",
            )
        )
    )
    await session.commit()

    assert await _projected(session, test_workspace, test_user) == (100.0, 100.0)


@pytest.mark.parametrize("mode", MODES)
async def test_future_linked_payment_is_not_projected(
    monkeypatch, session, test_user, test_workspace, mode
):
    """AC 2: a payment linked to its bill and dated after today stays out of the forecast."""
    freeze_today(monkeypatch, date(2026, 9, 10))
    await set_mode(session, mode)
    checking, _, bill = await _seed(session, test_user, test_workspace)

    session.add(
        tx(checking, date(2026, 9, 14), "1283.20", paid_bill_id=bill.id, description="Pagamento")
    )
    await session.commit()

    assert await _projected(session, test_workspace, test_user) == (100.0, 100.0)
