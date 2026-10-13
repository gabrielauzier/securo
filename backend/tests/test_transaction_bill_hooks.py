"""AD-004 / BIMP-01: transaction CRUD keeps card bills current.

One test per write path of `transaction_service`, asserting the bill links
and stored aggregates after the call. Card: close 5, due 12, so a purchase
on 2026-08-10 belongs to the 2026-09 bill and one on 2026-09-10 to 2026-10.
"""

import uuid
from datetime import date
from decimal import Decimal

import pytest_asyncio
from sqlalchemy import select

from app.models.account import Account
from app.models.category import Category
from app.models.credit_card_bill import CreditCardBill
from app.models.transaction import Transaction
from app.schemas.transaction import (
    InstallmentSeriesCreate,
    TransactionCreate,
    TransactionUpdate,
    TransferCreate,
)
from app.services import bill_service
from app.services.transaction_service import (
    bulk_delete_transactions,
    bulk_set_ignored,
    bulk_update_category,
    create_installment_series,
    create_transaction,
    create_transfer,
    create_transfer_counterpart,
    delete_transaction,
    toggle_ignore_transaction,
    update_transaction,
)

SEP = date(2026, 9, 1)
OCT = date(2026, 10, 1)


async def _account(session, user, workspace, name, type_="credit_card", cycle=(5, 12)) -> Account:
    account = Account(
        id=uuid.uuid4(),
        user_id=user.id,
        workspace_id=workspace.id,
        name=name,
        type=type_,
        currency="BRL",
        statement_close_day=cycle[0] if type_ == "credit_card" else None,
        payment_due_day=cycle[1] if type_ == "credit_card" else None,
    )
    session.add(account)
    await session.commit()
    return account


@pytest_asyncio.fixture
async def card(session, test_user, test_workspace) -> Account:
    return await _account(session, test_user, test_workspace, "Cartão de Crédito Nubank")


@pytest_asyncio.fixture
async def other_card(session, test_user, test_workspace) -> Account:
    return await _account(session, test_user, test_workspace, "Cartão Itaú")


@pytest_asyncio.fixture
async def checking(session, test_user, test_workspace) -> Account:
    return await _account(session, test_user, test_workspace, "Nubank", type_="checking")


async def _bills(session, account) -> dict[date, CreditCardBill]:
    rows = (
        await session.execute(select(CreditCardBill).where(CreditCardBill.account_id == account.id))
    ).scalars().all()
    for bill in rows:
        await session.refresh(bill)
    return {b.reference_month: b for b in rows}


async def _create(session, ws, user, account, on, amount="100.00", **extra) -> Transaction:
    return await create_transaction(
        session,
        ws.id,
        user.id,
        TransactionCreate(
            account_id=account.id,
            description=extra.pop("description", "MERCADO"),
            amount=Decimal(amount),
            date=on,
            type=extra.pop("type", "debit"),
            **extra,
        ),
    )


async def test_create_transaction_links_the_row_and_creates_its_bill(
    session, test_user, test_workspace, card
):
    # BIMP AC 1, 2.
    tx = await _create(session, test_workspace, test_user, card, date(2026, 8, 10))
    bills = await _bills(session, card)
    assert list(bills) == [SEP]
    assert bills[SEP].source == "auto"
    assert tx.bill_id == bills[SEP].id
    assert bills[SEP].computed_total == Decimal("100.00")


async def test_create_installment_series_links_each_parcel_to_its_own_bill(
    session, test_user, test_workspace, card
):
    # BIMP AC 8: parcels on 08-10 and 09-10 land on the 2026-09 and 2026-10 bills.
    rows = await create_installment_series(
        session,
        test_workspace.id,
        test_user.id,
        InstallmentSeriesCreate(
            base=TransactionCreate(
                account_id=card.id, description="TV", amount=Decimal("50.00"),
                date=date(2026, 8, 10), type="debit",
            ),
            installments=2,
        ),
    )
    bills = await _bills(session, card)
    assert [r.bill_id for r in rows] == [bills[SEP].id, bills[OCT].id]
    assert bills[SEP].computed_total == bills[OCT].computed_total == Decimal("50.00")


async def test_update_transaction_date_change_relinks_and_refreshes_both_bills(
    session, test_user, test_workspace, card
):
    # BIMP AC 5 (date).
    tx = await _create(session, test_workspace, test_user, card, date(2026, 8, 10))
    await update_transaction(
        session, tx.id, test_workspace.id, test_user.id, TransactionUpdate(date=date(2026, 9, 10))
    )
    bills = await _bills(session, card)
    assert tx.bill_id == bills[OCT].id
    assert bills[SEP].computed_total == Decimal("0.00")
    assert bills[OCT].computed_total == Decimal("100.00")


async def test_update_transaction_account_change_moves_the_row_to_the_new_cards_bill(
    session, test_user, test_workspace, card, other_card, checking
):
    # BIMP AC 5 (account): card -> other card, then other card -> checking.
    tx = await _create(session, test_workspace, test_user, card, date(2026, 8, 10))
    await update_transaction(
        session, tx.id, test_workspace.id, test_user.id, TransactionUpdate(account_id=other_card.id)
    )
    old, new = await _bills(session, card), await _bills(session, other_card)
    assert tx.bill_id == new[SEP].id
    assert old[SEP].computed_total == Decimal("0.00")
    assert new[SEP].computed_total == Decimal("100.00")

    await update_transaction(
        session, tx.id, test_workspace.id, test_user.id, TransactionUpdate(account_id=checking.id)
    )
    assert tx.bill_id is None
    assert (await _bills(session, other_card))[SEP].computed_total == Decimal("0.00")


async def test_update_transaction_override_links_to_the_bill_with_that_due_date(
    session, test_user, test_workspace, card
):
    # BIMP AC 4: the override names a bill by its effective (2026-09-14) or
    # nominal due date; a date matching no bill leaves the row unlinked and
    # creates no bill.
    await _create(session, test_workspace, test_user, card, date(2026, 8, 10))
    tx = await _create(session, test_workspace, test_user, card, date(2026, 9, 10), amount="30.00")
    bills = await _bills(session, card)
    assert tx.bill_id == bills[OCT].id

    await update_transaction(
        session, tx.id, test_workspace.id, test_user.id,
        TransactionUpdate(effective_bill_date=date(2026, 9, 14)),
    )
    bills = await _bills(session, card)
    assert tx.bill_id == bills[SEP].id
    assert bills[SEP].computed_total == Decimal("130.00")
    assert bills[OCT].computed_total == Decimal("0.00")

    await update_transaction(
        session, tx.id, test_workspace.id, test_user.id,
        TransactionUpdate(effective_bill_date=date(2027, 3, 3)),
    )
    assert tx.bill_id is None
    assert sorted(await _bills(session, card)) == [SEP, OCT]
    assert (await _bills(session, card))[SEP].computed_total == Decimal("100.00")


async def test_create_transfer_links_the_card_leg(
    session, test_user, test_workspace, card, checking
):
    await _create(session, test_workspace, test_user, card, date(2026, 8, 10), amount="300.00")
    debit, credit = await create_transfer(
        session, test_workspace.id, test_user.id,
        TransferCreate(
            from_account_id=checking.id, to_account_id=card.id, amount=Decimal("100.00"),
            date=date(2026, 8, 20), description="Pagamento",
        ),
    )
    bills = await _bills(session, card)
    assert credit.bill_id == bills[SEP].id
    assert debit.bill_id is None
    assert bills[SEP].computed_total == Decimal("200.00")


async def test_create_transfer_counterpart_links_a_counterpart_on_the_card(
    session, test_user, test_workspace, card, checking
):
    anchor = await _create(session, test_workspace, test_user, checking, date(2026, 8, 20), amount="40.00")
    _, credit = await create_transfer_counterpart(
        session, test_workspace.id, test_user.id, anchor.id, card.id
    )
    bills = await _bills(session, card)
    assert credit.account_id == card.id
    assert credit.bill_id == bills[SEP].id
    assert bills[SEP].computed_total == Decimal("-40.00")


async def test_toggle_ignore_transaction_refreshes_the_bill(
    session, test_user, test_workspace, card
):
    tx = await _create(session, test_workspace, test_user, card, date(2026, 8, 10))
    await toggle_ignore_transaction(session, tx.id, test_workspace.id)
    bill = (await _bills(session, card))[SEP]
    assert tx.bill_id == bill.id  # ignored rows stay linked
    assert bill.computed_total == Decimal("0.00")
    await toggle_ignore_transaction(session, tx.id, test_workspace.id)
    assert (await _bills(session, card))[SEP].computed_total == Decimal("100.00")


async def test_bulk_set_ignored_refreshes_the_bills(session, test_user, test_workspace, card):
    a = await _create(session, test_workspace, test_user, card, date(2026, 8, 10))
    b = await _create(session, test_workspace, test_user, card, date(2026, 8, 11), amount="20.00")
    assert await bulk_set_ignored(session, test_workspace.id, [a.id, b.id], True) == 2
    assert (await _bills(session, card))[SEP].computed_total == Decimal("0.00")


async def test_bulk_update_category_to_a_bill_payment_category_refreshes_the_bill(
    session, test_user, test_workspace, card
):
    category = Category(
        id=uuid.uuid4(), user_id=test_user.id, workspace_id=test_workspace.id,
        name="Pagamento de fatura", is_bill_payment=True,
    )
    session.add(category)
    await session.commit()
    a = await _create(session, test_workspace, test_user, card, date(2026, 8, 10))
    await _create(session, test_workspace, test_user, card, date(2026, 8, 11), amount="20.00")
    assert await bulk_update_category(session, test_workspace.id, [a.id], category.id) == 1
    assert (await _bills(session, card))[SEP].computed_total == Decimal("20.00")


async def test_delete_transaction_refreshes_the_bill(session, test_user, test_workspace, card):
    a = await _create(session, test_workspace, test_user, card, date(2026, 8, 10))
    await _create(session, test_workspace, test_user, card, date(2026, 8, 11), amount="20.00")
    assert await delete_transaction(session, a.id, test_workspace.id) is True
    assert (await _bills(session, card))[SEP].computed_total == Decimal("20.00")


async def test_deleting_a_linked_payment_recomputes_the_bill(
    session, test_user, test_workspace, card, checking
):
    # Edge case: a deleted payment drops its link and the bill's paid amount.
    await _create(session, test_workspace, test_user, card, date(2026, 8, 10))
    bill = (await _bills(session, card))[SEP]
    payment = await _create(session, test_workspace, test_user, checking, date(2026, 9, 14))
    payment.paid_bill_id = bill.id
    await bill_service.touch(session, [payment.id])
    await session.commit()
    assert (await _bills(session, card))[SEP].paid_amount == Decimal("100.00")

    assert await delete_transaction(session, payment.id, test_workspace.id) is True
    bill = (await _bills(session, card))[SEP]
    assert bill.paid_amount == Decimal("0.00")
    assert bill.settled_on is None


async def test_bulk_delete_transactions_refreshes_the_bills(
    session, test_user, test_workspace, card, checking
):
    a = await _create(session, test_workspace, test_user, card, date(2026, 8, 10))
    await _create(session, test_workspace, test_user, card, date(2026, 8, 11), amount="20.00")
    bill = (await _bills(session, card))[SEP]
    payment = await _create(session, test_workspace, test_user, checking, date(2026, 9, 14), amount="120.00")
    payment.paid_bill_id = bill.id
    await bill_service.touch(session, [payment.id])
    await session.commit()

    assert await bulk_delete_transactions(session, test_workspace.id, [a.id, payment.id]) == 2
    bill = (await _bills(session, card))[SEP]
    assert bill.computed_total == Decimal("20.00")
    assert bill.paid_amount == Decimal("0.00")
