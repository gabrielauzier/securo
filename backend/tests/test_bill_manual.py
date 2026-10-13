"""BILL-02: manual bill create, edit and delete (P1 AC 7-11)."""

import uuid
from datetime import date
from decimal import Decimal

import pytest
import pytest_asyncio
from sqlalchemy import func, select

from app.models.account import Account
from app.models.credit_card_bill import CreditCardBill
from app.models.transaction import Transaction
from app.services import bill_service
from app.services.bill_service import (
    BillConflictError,
    BillValidationError,
    create_manual_bill,
    delete_bill,
    update_bill,
)
from app.services.credit_card_service import bill_period_for_month

SEP = date(2026, 9, 1)


@pytest_asyncio.fixture
async def card(session, test_user, test_workspace) -> Account:
    # No cycle configured: only manual bills exist for this card.
    account = Account(
        id=uuid.uuid4(), user_id=test_user.id, workspace_id=test_workspace.id,
        name="Cartão de Crédito Nubank", type="credit_card", currency="BRL",
    )
    session.add(account)
    await session.commit()
    return account


@pytest_asyncio.fixture
async def checking(session, test_user, test_workspace) -> Account:
    account = Account(
        id=uuid.uuid4(), user_id=test_user.id, workspace_id=test_workspace.id,
        name="Nubank", type="checking", currency="BRL",
    )
    session.add(account)
    await session.commit()
    return account


def _tx(account, on, amount, **extra) -> Transaction:
    return Transaction(
        id=uuid.uuid4(), user_id=account.user_id, workspace_id=account.workspace_id,
        account_id=account.id, description="row", amount=Decimal(amount), currency="BRL",
        date=on, effective_date=on, type="debit", source="manual", **extra,
    )


async def _manual(session, ws, card, **extra) -> CreditCardBill:
    bill = await create_manual_bill(
        session, ws.id, card.id, reference_month=SEP,
        close_date=date(2026, 9, 5), due_date=date(2026, 9, 12), **extra,
    )
    await session.commit()
    await session.refresh(bill)
    return bill


async def _bill_count(session, card_id) -> int:
    return await session.scalar(
        select(func.count()).select_from(CreditCardBill).where(CreditCardBill.account_id == card_id)
    )


async def test_manual_bill_is_stored_and_links_rows_of_its_period(
    session, test_workspace, card
):
    first = _tx(card, date(2026, 8, 5), "100.00")
    last = _tx(card, date(2026, 9, 4), "50.00")
    close_day = _tx(card, date(2026, 9, 5), "30.00")
    overridden = _tx(card, date(2026, 8, 20), "20.00", effective_bill_date=date(2026, 10, 12))
    session.add_all([first, last, close_day, overridden])
    await session.commit()

    bill = await _manual(session, test_workspace, card)

    # P1 AC 7: source manual, period [previous close, close - 1].
    assert bill.source == "manual"
    assert (bill.reference_month, bill.close_date, bill.due_date) == (
        SEP, date(2026, 9, 5), date(2026, 9, 12)
    )
    assert (bill.period_start, bill.period_end) == (date(2026, 8, 5), date(2026, 9, 4))
    assert bill.effective_due_date == date(2026, 9, 14)
    for tx in (first, last, close_day, overridden):
        await session.refresh(tx)
    assert first.bill_id == bill.id
    assert last.bill_id == bill.id
    assert close_day.bill_id is None
    assert overridden.bill_id is None
    assert bill.computed_total == Decimal("150.00")


async def test_manual_bill_takes_rows_from_an_auto_bill_of_another_month(
    session, test_workspace, card
):
    card.statement_close_day, card.payment_due_day = 25, 2
    auto, _ = await bill_service.get_or_create_bill(
        session, card, bill_period_for_month(SEP, 25, 2)  # period 07-25..08-24
    )
    row = _tx(card, date(2026, 8, 10), "80.00", bill_id=auto.id)
    session.add(row)
    await bill_service.refresh_bills(session, [auto.id])
    await session.commit()

    bill = await create_manual_bill(
        session, test_workspace.id, card.id, reference_month=date(2026, 10, 1),
        close_date=date(2026, 8, 15), due_date=date(2026, 10, 1),  # period 07-25..08-14
    )
    await session.commit()

    await session.refresh(row)
    await session.refresh(auto)
    assert row.bill_id == bill.id
    assert auto.computed_total == Decimal("0.00")
    assert bill.computed_total == Decimal("80.00")


async def test_second_bill_for_the_same_reference_month_conflicts(
    session, test_workspace, card
):
    card_id = card.id
    await _manual(session, test_workspace, card)

    with pytest.raises(BillConflictError) as exc:
        await create_manual_bill(
            session, test_workspace.id, card.id, reference_month=SEP,
            close_date=date(2026, 9, 4), due_date=date(2026, 9, 11),
        )
    # P1 AC 8: HTTP 409, nothing stored.
    assert exc.value.status_code == 409
    await session.rollback()
    assert await _bill_count(session, card_id) == 1


async def test_manual_bill_rejects_a_negative_declared_total(session, test_workspace, card):
    card_id = card.id
    with pytest.raises(BillValidationError) as exc:
        await _manual(session, test_workspace, card, declared_total=Decimal("-1.00"))
    assert exc.value.status_code == 422
    await session.rollback()
    assert await _bill_count(session, card_id) == 0


async def test_editing_the_declared_total_recomputes_target_remaining_and_status(
    session, test_workspace, card, checking
):
    bill = await _manual(session, test_workspace, card)
    session.add(_tx(card, date(2026, 8, 20), "1283.20", bill_id=bill.id))
    session.add(_tx(checking, date(2026, 9, 14), "-500.00", paid_bill_id=bill.id))
    await bill_service.refresh_bills(session, [bill.id])
    await session.commit()
    today = date(2026, 9, 14)
    assert bill_service.bill_status(bill, today) == "partially_paid"

    # P1 AC 9: declared total 500.00 now is the target, fully paid on 09-14.
    await update_bill(session, test_workspace.id, bill.id, {"declared_total": Decimal("500.00")})
    await session.commit()
    await session.refresh(bill)

    assert bill.declared_total == Decimal("500.00")
    amounts = bill_service.bill_amounts(bill)
    assert amounts.target == Decimal("500.00")
    assert amounts.remaining == Decimal("0.00")
    assert bill_service.bill_status(bill, today) == "paid"
    assert bill.settled_on == date(2026, 9, 14)


async def test_declared_total_of_a_provider_bill_is_editable_but_not_its_dates(
    session, test_workspace, card
):
    provider = CreditCardBill(
        user_id=card.user_id, workspace_id=card.workspace_id, account_id=card.id,
        external_id="pluggy-1", due_date=date(2026, 9, 12), total_amount=Decimal("900.00"),
        currency="BRL",
    )
    session.add(provider)
    await session.commit()

    await update_bill(session, test_workspace.id, provider.id, {"declared_total": Decimal("950.00")})
    await session.commit()
    await session.refresh(provider)
    assert provider.declared_total == Decimal("950.00")

    # P1 AC 10: editing a provider bill's dates is refused.
    with pytest.raises(BillValidationError) as exc:
        await update_bill(session, test_workspace.id, provider.id, {"due_date": date(2026, 9, 15)})
    assert exc.value.status_code == 422
    await session.rollback()
    await session.refresh(provider)
    assert provider.due_date == date(2026, 9, 12)


async def test_editing_a_negative_declared_total_is_refused(session, test_workspace, card):
    bill = await _manual(session, test_workspace, card)
    with pytest.raises(BillValidationError):
        await update_bill(session, test_workspace.id, bill.id, {"declared_total": Decimal("-5.00")})
    await session.rollback()
    await session.refresh(bill)
    assert bill.declared_total is None


async def test_editing_manual_bill_dates_moves_its_period_rows(session, test_workspace, card):
    early = _tx(card, date(2026, 8, 6), "10.00")
    late = _tx(card, date(2026, 9, 7), "20.00")
    session.add_all([early, late])
    await session.commit()
    bill = await _manual(session, test_workspace, card)
    await session.refresh(early)
    assert early.bill_id == bill.id

    await update_bill(
        session, test_workspace.id, bill.id,
        {"close_date": date(2026, 9, 10), "due_date": date(2026, 9, 17)},
    )
    await session.commit()
    await session.refresh(bill)
    await session.refresh(early)
    await session.refresh(late)

    assert (bill.period_start, bill.period_end) == (date(2026, 8, 10), date(2026, 9, 9))
    assert bill.effective_due_date == date(2026, 9, 17)
    assert early.bill_id is None
    assert late.bill_id == bill.id
    assert bill.computed_total == Decimal("20.00")


async def test_deleting_a_bill_unlinks_rows_and_payments_and_keeps_them(
    session, test_workspace, card, checking
):
    card_id = card.id
    bill = await _manual(session, test_workspace, card)
    purchase = _tx(card, date(2026, 8, 20), "100.00", bill_id=bill.id)
    payment = _tx(checking, date(2026, 9, 14), "-100.00", paid_bill_id=bill.id)
    session.add_all([purchase, payment])
    await session.commit()

    await delete_bill(session, test_workspace.id, bill.id)
    await session.commit()

    # P1 AC 11: the bill is gone, both transactions remain, unlinked.
    assert await _bill_count(session, card_id) == 0
    await session.refresh(purchase)
    await session.refresh(payment)
    assert purchase.bill_id is None
    assert payment.paid_bill_id is None


async def test_deleting_a_provider_bill_is_refused(session, test_workspace, card):
    card_id = card.id
    provider = CreditCardBill(
        user_id=card.user_id, workspace_id=card.workspace_id, account_id=card.id,
        external_id="pluggy-2", due_date=date(2026, 9, 12), total_amount=Decimal("1.00"),
        currency="BRL",
    )
    session.add(provider)
    await session.commit()

    with pytest.raises(BillValidationError) as exc:
        await delete_bill(session, test_workspace.id, provider.id)
    assert exc.value.status_code == 422
    assert await _bill_count(session, card_id) == 1
