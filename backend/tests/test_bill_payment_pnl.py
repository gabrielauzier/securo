"""BPAY-01 AC 2 and BPAY-03 AC 13: bill payments leave income and expense totals.

A payment linked to a bill (`paid_bill_id`) and a payment in a category
flagged `is_bill_payment` are excluded from the dashboard totals, category
spending, reports and budgets, in `cash` and `accrual`."""

import uuid
from datetime import date, datetime, timezone
from decimal import Decimal

import pytest
import pytest_asyncio

from app.models.account import Account
from app.models.budget import Budget
from app.models.category import Category
from app.models.transaction import Transaction
from app.services import admin_service, bill_service, budget_service, dashboard_service, report_service
from app.services.credit_card_service import bill_period_for_month

SEP = date(2026, 9, 1)


def _tx(user_id, account_id, on, amount, *, category_id=None, **extra) -> Transaction:
    return Transaction(
        id=uuid.uuid4(), user_id=user_id, account_id=account_id, description="row",
        amount=Decimal(amount), amount_primary=Decimal(amount), currency="BRL",
        date=on, effective_date=on, type="debit", source="manual", status="posted",
        category_id=category_id, created_at=datetime.now(timezone.utc), **extra,
    )


@pytest_asyncio.fixture
async def seeded(session, test_user, test_workspace):
    """September on the checking account: a 100.00 grocery purchase, the
    reference 1,283.20 payment linked to the card's bill (filed under
    groceries by mistake), and a 200.00 payment in a bill-payment category
    that is not linked yet."""
    market = Category(id=uuid.uuid4(), user_id=test_user.id, name="Mercado")
    bill_payment = Category(
        id=uuid.uuid4(), user_id=test_user.id, name="Pagamento de fatura", is_bill_payment=True
    )
    checking = Account(
        id=uuid.uuid4(), user_id=test_user.id, workspace_id=test_workspace.id,
        name="Nubank", type="checking", currency="BRL",
    )
    card = Account(
        id=uuid.uuid4(), user_id=test_user.id, workspace_id=test_workspace.id,
        name="Cartão de Crédito Nubank", type="credit_card", currency="BRL",
        statement_close_day=5, payment_due_day=12,
    )
    session.add_all([market, bill_payment, checking, card])
    await session.flush()
    bill, _ = await bill_service.get_or_create_bill(
        session, card, bill_period_for_month(SEP, 5, 12)
    )
    session.add_all([
        _tx(test_user.id, checking.id, date(2026, 9, 3), "100.00", category_id=market.id),
        _tx(
            test_user.id, checking.id, date(2026, 9, 14), "1283.20",
            category_id=market.id, paid_bill_id=bill.id,
        ),
        _tx(test_user.id, checking.id, date(2026, 9, 15), "200.00", category_id=bill_payment.id),
        Budget(
            id=uuid.uuid4(), user_id=test_user.id, category_id=market.id,
            amount=Decimal("500"), currency="BRL", month=SEP,
        ),
        Budget(
            id=uuid.uuid4(), user_id=test_user.id, category_id=bill_payment.id,
            amount=Decimal("500"), currency="BRL", month=SEP,
        ),
    ])
    await session.commit()
    return {"market": market, "bill_payment": bill_payment}


MODES = ["cash", "accrual"]


@pytest.mark.parametrize("mode", MODES)
async def test_dashboard_expenses_exclude_bill_payments(
    session, test_user, test_workspace, seeded, mode
):
    await admin_service.set_app_setting(session, "credit_card_accounting_mode", mode)
    summary = await dashboard_service.get_summary(
        session, test_workspace.id, test_user.id, month=SEP
    )
    assert summary.monthly_expenses == 100.0
    assert summary.monthly_income == 0.0


@pytest.mark.parametrize("mode", MODES)
async def test_category_spending_excludes_bill_payments(
    session, test_user, test_workspace, seeded, mode
):
    await admin_service.set_app_setting(session, "credit_card_accounting_mode", mode)
    spending = await dashboard_service.get_spending_by_category(
        session, test_workspace.id, test_user.id, month=SEP
    )
    totals = {row.category_id: row.total for row in spending}
    assert totals.get(str(seeded["market"].id)) == 100.0
    assert totals.get(str(seeded["bill_payment"].id), 0.0) == 0.0
    assert sum(totals.values()) == 100.0


@pytest.mark.parametrize("mode", MODES)
async def test_budgets_exclude_bill_payments(session, test_user, test_workspace, seeded, mode):
    await admin_service.set_app_setting(session, "credit_card_accounting_mode", mode)
    rows = await budget_service.get_budget_vs_actual(
        session, test_workspace.id, test_user.id, SEP
    )
    actual = {row.category_id: float(row.actual_amount) for row in rows}
    assert actual[seeded["market"].id] == 100.0
    assert actual[seeded["bill_payment"].id] == 0.0


class TestReportsOnPostgres:
    """The income/expense report groups by `to_char`, so it runs on PostgreSQL."""

    @pytest_asyncio.fixture
    async def session(self, postgres_sessions):
        async with postgres_sessions() as session:
            yield session
            await session.rollback()

    @pytest.fixture
    def clean_db(self, postgres_sessions):
        """Each test starts in a fresh PostgreSQL schema."""

    @pytest.mark.parametrize("mode", MODES)
    async def test_income_expense_report_excludes_bill_payments(
        self, session, test_user, test_workspace, seeded, mode
    ):
        await admin_service.set_app_setting(session, "credit_card_accounting_mode", mode)
        report = await report_service.get_income_expenses_report(
            session, test_workspace.id, test_user.id, interval="monthly", currency="BRL",
            start_date=SEP, end_date=date(2026, 9, 30),
        )
        september = next(p for p in report.trend if p.date.startswith("2026-09"))
        assert september.breakdowns["expenses"] == 100.0
        assert september.breakdowns["income"] == 0.0
