"""BMATCH-02: dismissed suggestions and the list indicator (AC 9, 14 service side)."""

import uuid
from datetime import date
from decimal import Decimal

import pytest
import pytest_asyncio
from sqlalchemy import func, select

from app.models.account import Account
from app.models.bill_payment_dismissal import BillPaymentDismissal
from app.models.transaction import Transaction
from app.models.workspace import Workspace
from app.services import bill_service
from app.services.bill_match_service import (
    candidates_for,
    dismiss,
    has_suggestion,
    propose_matches,
    run_auto_match,
)
from app.services.bill_payment_service import BillPaymentError
from app.services.credit_card_service import bill_period_for_month

SEP = date(2026, 9, 1)
DUE = date(2026, 9, 14)  # effective due date of the 2026-09 bill (close 5, due 12)


def _account(user, workspace, name, type_, **extra) -> Account:
    return Account(
        id=uuid.uuid4(), user_id=user.id, workspace_id=workspace.id, name=name, type=type_,
        currency="BRL", **extra,
    )


def _tx(account, on, amount, *, type_="debit", **extra) -> Transaction:
    return Transaction(
        id=uuid.uuid4(), user_id=account.user_id, workspace_id=account.workspace_id,
        account_id=account.id, description="row", amount=Decimal(amount), currency="BRL",
        date=on, effective_date=on, type=type_, source="manual", **extra,
    )


@pytest_asyncio.fixture
async def setup(session, test_user, test_workspace):
    card = _account(
        test_user, test_workspace, "Cartão de Crédito Nubank", "credit_card",
        statement_close_day=5, payment_due_day=12,
    )
    checking = _account(test_user, test_workspace, "Nubank", "checking")
    session.add_all([card, checking])
    await session.flush()
    bill, _ = await bill_service.get_or_create_bill(
        session, card, bill_period_for_month(SEP, 5, 12)
    )
    session.add(_tx(card, date(2026, 8, 20), "1283.20", bill_id=bill.id))
    await bill_service.refresh_bills(session, [bill.id])
    await session.commit()
    return {"card": card, "checking": checking, "bill": bill, "ws": test_workspace}


async def _pay(session, setup, amount, on=DUE, **extra) -> Transaction:
    tx = _tx(setup["checking"], on, amount, **extra)
    session.add(tx)
    await session.commit()
    return tx


async def _dismiss(session, setup, payment):
    await dismiss(session, setup["ws"].id, payment.id, setup["bill"].id)
    await session.commit()


async def test_dismissed_pair_is_never_proposed_or_linked_again(session, setup):
    payment = await _pay(session, setup, "1283.20")
    await _dismiss(session, setup, payment)

    proposals = await propose_matches(session, setup["ws"].id)
    linked = await run_auto_match(session, setup["ws"].id)

    # BMATCH AC 9
    await session.refresh(payment)
    assert proposals == []
    assert linked == 0
    assert payment.paid_bill_id is None


async def test_dismissed_bill_stays_selectable_among_the_other_bills(session, setup):
    payment = await _pay(session, setup, "1283.20")
    await _dismiss(session, setup, payment)

    candidates = await candidates_for(session, payment)

    # BMATCH AC 9: not suggested; the dialog still lists it as another unpaid bill.
    assert [(c.bill.id, c.kind) for c in candidates] == [(setup["bill"].id, "other")]


async def test_dismissing_one_pair_keeps_other_payments_suggested(session, setup):
    dismissed = await _pay(session, setup, "500.00")
    kept = await _pay(session, setup, "400.00")
    await _dismiss(session, setup, dismissed)

    proposals = await propose_matches(session, setup["ws"].id)

    assert [(p.payment_id, p.bill_id) for p in proposals] == [(kept.id, setup["bill"].id)]


async def test_has_suggestion_is_true_only_for_undismissed_window_candidates(session, setup):
    suggested = await _pay(session, setup, "500.00")
    dismissed = await _pay(session, setup, "400.00")
    late = await _pay(session, setup, "500.00", on=date(2026, 9, 20))
    credit = await _pay(session, setup, "500.00", type_="credit")
    await _dismiss(session, setup, dismissed)

    flagged = await has_suggestion(
        session, setup["ws"].id, [suggested.id, dismissed.id, late.id, credit.id]
    )

    # BMATCH AC 14 (service side)
    assert flagged == {suggested.id}


async def test_dismiss_is_idempotent(session, setup):
    payment = await _pay(session, setup, "500.00")
    await _dismiss(session, setup, payment)
    await _dismiss(session, setup, payment)

    count = await session.scalar(select(func.count()).select_from(BillPaymentDismissal))
    assert count == 1


async def test_dismiss_refuses_a_bill_of_another_workspace(
    session, setup, test_user
):
    other = Workspace(
        id=uuid.uuid4(), name="Outro", kind="shared", created_by_user_id=test_user.id,
        default_currency="BRL", locale="pt-BR",
    )
    session.add(other)
    await session.commit()
    payment = await _pay(session, setup, "500.00")

    # BPAY AC 12 applied to dismissals: other-workspace rows are not found.
    with pytest.raises(BillPaymentError) as exc:
        await dismiss(session, other.id, payment.id, setup["bill"].id)
    assert exc.value.status_code == 404
