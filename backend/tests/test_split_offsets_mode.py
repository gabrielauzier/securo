"""BREP-01 AC 10: split adjustments follow the accounting mode (T36).

The reference bill's 600.00 Mercado purchase (2026-08-10, nominal due
2026-09-12) is split: the owner keeps 360.00 and a friend owes 240.00. The
240.00 offset must leave the owner's spending in the same month the purchase
is counted in.
"""

import uuid
from datetime import date
from decimal import Decimal

import pytest
import pytest_asyncio

from app.models.budget import Budget
from app.models.group import Group, GroupMember
from app.models.transaction_split import TransactionSplit
from app.services import budget_service, dashboard_service, report_service
from tests.settlement_fixtures import AUG, SEP, freeze_today, pay, seed_reference, set_mode


async def _split_market_purchase(session, user, workspace, ref):
    group = Group(
        id=uuid.uuid4(), user_id=user.id, workspace_id=workspace.id,
        name="Casa", default_currency="BRL",
    )
    session.add(group)
    await session.flush()
    me = GroupMember(
        id=uuid.uuid4(), group_id=group.id, workspace_id=workspace.id,
        name="Eu", linked_user_id=user.id, is_self=True,
    )
    friend = GroupMember(
        id=uuid.uuid4(), group_id=group.id, workspace_id=workspace.id, name="Ana",
    )
    session.add_all([me, friend])
    await session.flush()
    for member, share in ((me, "360.00"), (friend, "240.00")):
        session.add(TransactionSplit(
            id=uuid.uuid4(), transaction_id=ref.market_purchase.id, workspace_id=workspace.id,
            group_member_id=member.id, share_amount=Decimal(share), share_type="exact",
        ))
    session.add(Budget(
        id=uuid.uuid4(), user_id=user.id, workspace_id=workspace.id,
        category_id=ref.market.id, amount=Decimal("800"), currency="BRL", month=SEP,
    ))
    await session.commit()


@pytest_asyncio.fixture
async def ref(monkeypatch, session, test_user, test_workspace):
    freeze_today(monkeypatch, date(2026, 9, 25))
    ref = await seed_reference(session, test_user, test_workspace)
    await _split_market_purchase(session, test_user, test_workspace, ref)
    return ref


async def _summary_expenses(session, ws, user, month):
    summary = await dashboard_service.get_summary(session, ws.id, user.id, month=month)
    return summary.monthly_expenses


async def _mercado_spending(session, ws, user, ref, month):
    rows = await dashboard_service.get_spending_by_category(session, ws.id, user.id, month=month)
    return next((row.total for row in rows if row.category_id == str(ref.market.id)), 0.0)


async def _mercado_budget(session, ws, user, ref, month):
    rows = await budget_service.get_budget_vs_actual(session, ws.id, user.id, month)
    return next(
        (float(row.actual_amount) for row in rows if row.category_id == ref.market.id), 0.0
    )


async def test_cash_offsets_in_the_purchase_month(session, test_user, test_workspace, ref):
    await set_mode(session, "cash")

    assert await _summary_expenses(session, test_workspace, test_user, AUG) == 760.0
    assert await _mercado_spending(session, test_workspace, test_user, ref, AUG) == 360.0
    assert await _summary_expenses(session, test_workspace, test_user, SEP) == 0.0


async def test_accrual_offsets_in_the_due_month(session, test_user, test_workspace, ref):
    await set_mode(session, "accrual")

    assert await _mercado_spending(session, test_workspace, test_user, ref, SEP) == 360.0
    assert await _mercado_budget(session, test_workspace, test_user, ref, SEP) == 360.0
    assert await _mercado_spending(session, test_workspace, test_user, ref, AUG) == 0.0


async def test_settlement_offsets_in_the_month_the_bill_is_paid(
    session, test_user, test_workspace, ref
):
    await set_mode(session, "settlement")
    await pay(session, ref, "1000.00", date(2026, 9, 14))

    assert await _summary_expenses(session, test_workspace, test_user, SEP) == 760.0
    assert await _mercado_spending(session, test_workspace, test_user, ref, SEP) == 360.0
    assert await _mercado_budget(session, test_workspace, test_user, ref, SEP) == 360.0
    assert await _summary_expenses(session, test_workspace, test_user, AUG) == 0.0


async def test_settlement_holds_the_offset_while_the_bill_is_unpaid(
    session, test_user, test_workspace, ref
):
    await set_mode(session, "settlement")

    assert await _summary_expenses(session, test_workspace, test_user, AUG) == 0.0
    assert await _summary_expenses(session, test_workspace, test_user, SEP) == 0.0
    assert await _mercado_budget(session, test_workspace, test_user, ref, SEP) == 0.0


class TestOnPostgres:
    """The trend and the income/expense report group by `to_char`."""

    @pytest_asyncio.fixture
    async def session(self, postgres_sessions):
        async with postgres_sessions() as session:
            yield session
            await session.rollback()

    @pytest.fixture
    def clean_db(self, postgres_sessions):
        """Each test starts in a fresh PostgreSQL schema."""

    async def test_settlement_trend_and_report_offset_in_the_paid_month(
        self, session, test_user, test_workspace, ref
    ):
        await set_mode(session, "settlement")
        await pay(session, ref, "1000.00", date(2026, 9, 14))

        trend = await dashboard_service.get_monthly_trend(
            session, test_workspace.id, test_user.id, months=6
        )
        expenses = {point.month: point.expenses for point in trend}
        assert expenses.get("2026-09") == 760.0
        assert expenses.get("2026-08", 0.0) == 0.0

        report = await report_service.get_income_expenses_report(
            session, test_workspace.id, test_user.id, months=3, interval="monthly",
            currency="BRL",
        )
        months = {point.date: point.breakdowns for point in report.trend}
        assert months["2026-09"]["expenses"] == 760.0
        assert months["2026-08"]["expenses"] == 0.0
        composition = {
            item.label: item.value for item in report.composition if item.group == "expenses"
        }
        assert composition["Mercado"] == 360.0
