"""BILL-01 / AD-004: applying rules to existing transactions refreshes their bills."""

import uuid
from datetime import date
from decimal import Decimal

from app.models.account import Account
from app.models.category import Category
from app.models.rule import Rule
from app.models.transaction import Transaction
from app.services import bill_service, dashboard_service, rule_service
from app.services.credit_card_service import bill_period_for_month

SEP = date(2026, 9, 1)


def _row(user, workspace, account, description, amount, type_, on, **extra):
    return Transaction(
        id=uuid.uuid4(), user_id=user.id, workspace_id=workspace.id, account_id=account.id,
        description=description, amount=Decimal(amount), amount_primary=Decimal(amount),
        currency="BRL", date=on, effective_date=on, type=type_, source="manual",
        status="posted", **extra,
    )


async def _card_bill(session, user, workspace):
    card = Account(
        id=uuid.uuid4(), user_id=user.id, workspace_id=workspace.id,
        name="Cartão de Crédito Nubank", type="credit_card", currency="BRL",
        statement_close_day=5, payment_due_day=12,
    )
    session.add(card)
    await session.flush()
    bill, _ = await bill_service.get_or_create_bill(
        session, card, bill_period_for_month(SEP, 5, 12)
    )
    return card, bill


def _rule(user, workspace, contains, actions):
    return Rule(
        id=uuid.uuid4(), user_id=user.id, workspace_id=workspace.id, name="regra",
        conditions_op="and",
        conditions=[{"field": "description", "op": "contains", "value": contains}],
        actions=actions, priority=10, is_active=True,
    )


async def _ignored_purchase_setup(session, user, workspace):
    card, bill = await _card_bill(session, user, workspace)
    session.add(_row(user, workspace, card, "LOJA TESTE", "100.00", "debit",
                     date(2026, 8, 20), bill_id=bill.id))
    await bill_service.refresh_bills(session, [bill.id])
    rule = _rule(user, workspace, "LOJA TESTE", [{"op": "ignore"}])
    session.add(rule)
    await session.commit()
    assert bill.computed_total == Decimal("100.00")
    return bill, rule


async def test_apply_single_rule_ignoring_a_card_purchase_drops_the_bill_total(
    session, test_user, test_workspace
):
    bill, rule = await _ignored_purchase_setup(session, test_user, test_workspace)

    changed = await rule_service.apply_single_rule(session, test_workspace.id, rule)

    assert changed == 1
    await session.refresh(bill)
    assert bill.computed_total == Decimal("0.00")


async def test_apply_all_rules_ignoring_a_card_purchase_drops_the_bill_total(
    session, test_user, test_workspace
):
    bill, _ = await _ignored_purchase_setup(session, test_user, test_workspace)

    changed = await rule_service.apply_all_rules(session, test_workspace.id)

    assert changed == 1
    await session.refresh(bill)
    assert bill.computed_total == Decimal("0.00")


async def test_rule_filing_payments_under_a_bill_payment_category_refreshes_the_bill(
    session, test_user, test_workspace
):
    flagged = Category(
        id=uuid.uuid4(), user_id=test_user.id, workspace_id=test_workspace.id,
        name="Pagamento de fatura", is_bill_payment=True,
    )
    checking = Account(
        id=uuid.uuid4(), user_id=test_user.id, workspace_id=test_workspace.id,
        name="Nubank", type="checking", currency="BRL",
    )
    session.add_all([flagged, checking])
    card, bill = await _card_bill(session, test_user, test_workspace)
    session.add_all([
        _row(test_user, test_workspace, card, "Compra", "1000.00", "debit",
             date(2026, 8, 20), bill_id=bill.id),
        # The card side of the payment, not paired: it lowers the computed total.
        _row(test_user, test_workspace, card, "Pagamento recebido", "200.00", "credit",
             date(2026, 8, 25), bill_id=bill.id),
        _row(test_user, test_workspace, checking, "Pagamento fatura", "200.00", "debit",
             date(2026, 9, 14)),
    ])
    await bill_service.refresh_bills(session, [bill.id])
    rule = _rule(test_user, test_workspace, "Pagamento",
                 [{"op": "set_category", "value": str(flagged.id)}])
    session.add(rule)
    await session.commit()
    assert bill.computed_total == Decimal("800.00")
    before = await dashboard_service.get_summary(
        session, test_workspace.id, test_user.id, month=SEP
    )
    assert before.monthly_expenses == 200.0

    changed = await rule_service.apply_single_rule(session, test_workspace.id, rule)

    assert changed == 2
    await session.refresh(bill)
    assert bill.computed_total == Decimal("1000.00")
    after = await dashboard_service.get_summary(
        session, test_workspace.id, test_user.id, month=SEP
    )
    assert after.monthly_expenses == 0.0
