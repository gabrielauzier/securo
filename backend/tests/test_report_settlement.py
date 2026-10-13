"""BREP-01 on the reports in the `settlement` accounting mode (T34).

The reference 1,000.00 bill (BREP AC 5: 600.00 Mercado, 400.00 Restaurantes,
bought in August, effective due date 2026-09-14) reports in September only:
realized once paid, projected while unpaid. The reports group by `to_char`,
so they run on PostgreSQL.
"""

from datetime import date

import pytest
import pytest_asyncio

from app.services import report_service
from tests.settlement_fixtures import freeze_today, pay, seed_reference, set_mode


@pytest_asyncio.fixture
async def session(postgres_sessions):
    async with postgres_sessions() as session:
        yield session
        await session.rollback()


@pytest.fixture
def clean_db(postgres_sessions):
    """Each test starts in a fresh PostgreSQL schema."""


@pytest_asyncio.fixture
async def ref(monkeypatch, session, test_user, test_workspace):
    freeze_today(monkeypatch, date(2026, 9, 25))
    await set_mode(session, "settlement")
    return await seed_reference(session, test_user, test_workspace)


async def _monthly(session, ws, user):
    report = await report_service.get_income_expenses_report(
        session, ws.id, user.id, months=3, interval="monthly", currency="BRL",
    )
    return report, {point.date: point.breakdowns for point in report.trend}


def _expense_composition(report):
    return {item.label: item.value for item in report.composition if item.group == "expenses"}


async def test_paid_bill_reports_realized_in_september_only(
    session, test_user, test_workspace, ref
):
    await pay(session, ref, "1000.00", date(2026, 9, 14))

    report, months = await _monthly(session, test_workspace, test_user)

    assert months["2026-09"]["expenses"] == 1000.0
    assert months["2026-09"]["projectedExpenses"] == 0.0
    assert months["2026-08"]["expenses"] == 0.0
    assert months["2026-08"]["projectedExpenses"] == 0.0
    assert _expense_composition(report) == {"Mercado": 600.0, "Restaurantes": 400.0}


async def test_unpaid_bill_reports_projected_in_september_only(
    session, test_user, test_workspace, ref
):
    report, months = await _monthly(session, test_workspace, test_user)

    assert months["2026-09"]["expenses"] == 0.0
    assert months["2026-09"]["projectedExpenses"] == 1000.0
    assert months["2026-08"]["expenses"] == 0.0
    assert months["2026-08"]["projectedExpenses"] == 0.0


async def test_partially_paid_bill_stays_projected_in_the_report(
    session, test_user, test_workspace, ref
):
    await pay(session, ref, "500.00", date(2026, 9, 14))

    _, months = await _monthly(session, test_workspace, test_user)

    assert months["2026-09"]["expenses"] == 0.0
    assert months["2026-09"]["projectedExpenses"] == 1000.0


async def _cash_flow_outflows(session, ws, user):
    report = await report_service.get_cash_flow_report(
        session, ws.id, user.id, months=1, interval="daily", currency="BRL",
    )
    return {point.date: point.breakdowns["outflow"] for point in report.trend}


async def test_cash_flow_moves_paid_purchases_to_the_payment_date(
    session, test_user, test_workspace, ref
):
    await pay(session, ref, "1000.00", date(2026, 9, 14))

    outflows = await _cash_flow_outflows(session, test_workspace, test_user)

    assert outflows["2026-09-14"] == 1000.0


async def test_cash_flow_projects_unpaid_purchases_at_the_due_date(
    monkeypatch, session, test_user, test_workspace, ref
):
    freeze_today(monkeypatch, date(2026, 9, 10))

    outflows = await _cash_flow_outflows(session, test_workspace, test_user)

    assert outflows["2026-09-14"] == 1000.0
    assert outflows.get("2026-08-20", 0.0) == 0.0
