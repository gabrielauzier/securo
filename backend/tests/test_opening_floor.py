"""within_opening_floor: transactions dated before an account's opening
balance stay out of its balance (spec BAL-01 / BAL-03)."""
import uuid
from datetime import date, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.app_clock import app_today
from app.models.account import Account
from app.models.transaction import Transaction
from app.services._query_filters import within_opening_floor


async def _account(session: AsyncSession, user_id: uuid.UUID) -> Account:
    account = Account(
        id=uuid.uuid4(), user_id=user_id, name="Acc", type="checking",
        balance=Decimal("0"), currency="BRL",
    )
    session.add(account)
    await session.commit()
    return account


async def _tx(
    session: AsyncSession, account: Account, when: date, source: str = "manual",
) -> uuid.UUID:
    tx = Transaction(
        id=uuid.uuid4(), user_id=account.user_id, account_id=account.id,
        description="t", amount=Decimal("10"), date=when, type="debit",
        source=source, status="posted", currency="BRL",
    )
    session.add(tx)
    await session.commit()
    if source == "opening_balance":
        # AD-002: the floor reads the account's saved date, which the service
        # keeps in step with its opening row; mirror that for fixtures.
        owner = await session.get(Account, account.id)
        if owner is not None and owner.connection_id is None:
            owner.balance_date = max(owner.balance_date or when, when)
            await session.commit()
    return tx.id


async def _counted(session: AsyncSession, account: Account, cutoff: date) -> set[uuid.UUID]:
    rows = await session.execute(
        select(Transaction.id).where(
            Transaction.account_id == account.id,
            Transaction.date <= cutoff,
            within_opening_floor(cutoff),
        )
    )
    return set(rows.scalars().all())


@pytest.mark.asyncio
async def test_rows_before_opening_date_are_excluded_when_cutoff_is_after_it(session, test_user):
    acc = await _account(session, test_user.id)
    today = app_today()
    opening_day = today - timedelta(days=5)
    opening = await _tx(session, acc, opening_day, source="opening_balance")
    before = await _tx(session, acc, opening_day - timedelta(days=5))
    after = await _tx(session, acc, opening_day + timedelta(days=2))

    counted = await _counted(session, acc, today)

    assert counted == {opening, after}
    assert before not in counted


@pytest.mark.asyncio
async def test_row_dated_on_the_opening_date_is_included(session, test_user):
    acc = await _account(session, test_user.id)
    today = app_today()
    opening_day = today - timedelta(days=5)
    await _tx(session, acc, opening_day, source="opening_balance")
    same_day = await _tx(session, acc, opening_day)

    assert same_day in await _counted(session, acc, today)


@pytest.mark.asyncio
async def test_all_rows_up_to_cutoff_count_when_cutoff_is_before_the_opening_date(session, test_user):
    acc = await _account(session, test_user.id)
    today = app_today()
    opening_day = today - timedelta(days=5)
    await _tx(session, acc, opening_day, source="opening_balance")
    early = await _tx(session, acc, opening_day - timedelta(days=10))
    older = await _tx(session, acc, opening_day - timedelta(days=8))

    counted = await _counted(session, acc, opening_day - timedelta(days=1))

    assert counted == {early, older}


@pytest.mark.asyncio
async def test_account_without_opening_row_is_unaffected(session, test_user):
    acc = await _account(session, test_user.id)
    today = app_today()
    old = await _tx(session, acc, today - timedelta(days=400))
    recent = await _tx(session, acc, today - timedelta(days=1))

    assert await _counted(session, acc, today) == {old, recent}


@pytest.mark.asyncio
async def test_latest_opening_date_wins_when_there_are_two_opening_rows(session, test_user):
    acc = await _account(session, test_user.id)
    today = app_today()
    first_opening = today - timedelta(days=20)
    last_opening = today - timedelta(days=10)
    await _tx(session, acc, first_opening, source="opening_balance")
    await _tx(session, acc, last_opening, source="opening_balance")
    between = await _tx(session, acc, today - timedelta(days=15))
    after = await _tx(session, acc, today - timedelta(days=3))

    counted = await _counted(session, acc, today)

    assert after in counted
    assert between not in counted


@pytest.mark.asyncio
async def test_floor_is_evaluated_per_account(session, test_user):
    with_opening = await _account(session, test_user.id)
    without_opening = await _account(session, test_user.id)
    today = app_today()
    await _tx(session, with_opening, today - timedelta(days=5), source="opening_balance")
    old_in_other = await _tx(session, without_opening, today - timedelta(days=30))

    assert old_in_other in await _counted(session, without_opening, today)


async def _dated_account(
    session: AsyncSession, user_id: uuid.UUID, balance_date: date | None,
    connection_id: uuid.UUID | None = None,
) -> Account:
    account = Account(
        id=uuid.uuid4(), user_id=user_id, name="Dated", type="checking",
        balance=Decimal("0"), currency="BRL", balance_date=balance_date,
        connection_id=connection_id,
    )
    session.add(account)
    await session.commit()
    return account


@pytest.mark.asyncio
async def test_floor_applies_from_the_saved_date_without_any_opening_row(session, test_user):
    """ABD-02 AC1/AC4: balance_date alone floors the account (balance 0 at D)."""
    today = app_today()
    saved = today - timedelta(days=5)
    acc = await _dated_account(session, test_user.id, saved)
    before = await _tx(session, acc, saved - timedelta(days=3))
    on_day = await _tx(session, acc, saved)
    after = await _tx(session, acc, saved + timedelta(days=2))

    assert await _counted(session, acc, today) == {on_day, after}
    assert before not in await _counted(session, acc, today)


@pytest.mark.asyncio
async def test_cutoff_before_the_saved_date_reads_full_history(session, test_user):
    """ABD-02 AC2: a cutoff earlier than balance_date keeps every row up to it."""
    today = app_today()
    saved = today - timedelta(days=5)
    acc = await _dated_account(session, test_user.id, saved)
    early = await _tx(session, acc, saved - timedelta(days=10))
    older = await _tx(session, acc, saved - timedelta(days=8))

    assert await _counted(session, acc, saved - timedelta(days=1)) == {early, older}


@pytest.mark.asyncio
async def test_null_saved_date_means_no_floor(session, test_user):
    """ABD-02 AC3: balance_date NULL counts every row."""
    today = app_today()
    acc = await _dated_account(session, test_user.id, None)
    old = await _tx(session, acc, today - timedelta(days=500))
    recent = await _tx(session, acc, today - timedelta(days=1))

    assert await _counted(session, acc, today) == {old, recent}


@pytest.mark.asyncio
async def test_changing_the_saved_date_changes_the_next_read(session, test_user):
    """ABD-02 AC5: the next read reflects the new balance_date."""
    today = app_today()
    saved = today - timedelta(days=10)
    acc = await _dated_account(session, test_user.id, saved)
    middle = await _tx(session, acc, today - timedelta(days=6))
    assert middle in await _counted(session, acc, today)

    acc.balance_date = today - timedelta(days=3)
    await session.commit()
    assert middle not in await _counted(session, acc, today)

    acc.balance_date = today - timedelta(days=20)
    await session.commit()
    assert middle in await _counted(session, acc, today)


@pytest.mark.asyncio
async def test_connected_account_without_saved_date_is_not_floored(
    session, test_user, test_connection
):
    """ABD-02 AC6: a bank-connected account (balance_date NULL) reads as before,
    even with an opening_balance row present."""
    today = app_today()
    acc = await _dated_account(session, test_user.id, None, connection_id=test_connection.id)
    await _tx(session, acc, today - timedelta(days=5), source="opening_balance")
    old = await _tx(session, acc, today - timedelta(days=60))

    assert old in await _counted(session, acc, today)
    assert acc.balance_date is None
