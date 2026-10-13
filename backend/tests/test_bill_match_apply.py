"""BMATCH-01 / BMATCH-03: propose, auto-match and apply (AC 4, 5, 6, 11, 13)."""

import uuid
from datetime import date
from decimal import Decimal

import pytest_asyncio

from app.models.account import Account
from app.models.transaction import Transaction
from app.services import bill_service
from app.services.bill_match_service import apply_matches, propose_matches, run_auto_match
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


async def _card_with_bill(session, user, workspace, name, total="1283.20"):
    card = _account(
        user, workspace, name, "credit_card", statement_close_day=5, payment_due_day=12,
    )
    session.add(card)
    await session.flush()
    bill, _ = await bill_service.get_or_create_bill(
        session, card, bill_period_for_month(SEP, 5, 12)
    )
    session.add(_tx(card, date(2026, 8, 20), total, bill_id=bill.id))
    await bill_service.refresh_bills(session, [bill.id])
    await session.commit()
    return card, bill


@pytest_asyncio.fixture
async def setup(session, test_user, test_workspace):
    card, bill = await _card_with_bill(session, test_user, test_workspace, "Cartão de Crédito Nubank")
    checking = _account(test_user, test_workspace, "Nubank", "checking")
    session.add(checking)
    await session.commit()
    return {"card": card, "checking": checking, "bill": bill, "ws": test_workspace}


async def _pay(session, setup, amount, on=DUE, **extra) -> Transaction:
    tx = _tx(setup["checking"], on, amount, **extra)
    session.add(tx)
    await session.commit()
    return tx


async def _paid_bill_id(session, tx):
    await session.refresh(tx)
    return tx.paid_bill_id


async def test_single_exact_pair_links_automatically(session, setup):
    payment = await _pay(session, setup, "1283.20")

    linked = await run_auto_match(session, setup["ws"].id)
    await session.commit()

    # BMATCH AC 4: one candidate bill at the exact remaining amount, one payment.
    bill = setup["bill"]
    await session.refresh(bill)
    assert linked == 1
    assert await _paid_bill_id(session, payment) == bill.id
    assert bill_service.bill_status(bill, DUE) == "paid"


async def test_two_bills_at_the_payment_amount_are_only_suggested(
    session, setup, test_user, test_workspace
):
    _, other_bill = await _card_with_bill(session, test_user, test_workspace, "Cartão Inter")
    payment = await _pay(session, setup, "1283.20")

    proposals = await propose_matches(session, setup["ws"].id)
    linked = await run_auto_match(session, setup["ws"].id)

    # BMATCH AC 6: more than one bill qualifies.
    assert linked == 0
    assert await _paid_bill_id(session, payment) is None
    assert sorted((p.payment_id, p.bill_id, p.kind) for p in proposals) == sorted(
        [
            (payment.id, setup["bill"].id, "suggestion"),
            (payment.id, other_bill.id, "suggestion"),
        ]
    )


async def test_two_payments_at_the_bill_amount_are_only_suggested(session, setup):
    first = await _pay(session, setup, "1283.20")
    second = await _pay(session, setup, "1283.20", on=date(2026, 9, 15))

    proposals = await propose_matches(session, setup["ws"].id)
    linked = await run_auto_match(session, setup["ws"].id)

    # BMATCH AC 6: more than one payment qualifies.
    assert linked == 0
    assert await _paid_bill_id(session, first) is None
    assert await _paid_bill_id(session, second) is None
    assert [(p.payment_id, p.kind) for p in proposals] == [
        (first.id, "suggestion"),
        (second.id, "suggestion"),
    ]


async def test_partial_payment_is_proposed_but_not_linked(session, setup):
    payment = await _pay(session, setup, "500.00")

    proposals = await propose_matches(session, setup["ws"].id)
    linked = await run_auto_match(session, setup["ws"].id)

    # BMATCH AC 5
    assert linked == 0
    assert await _paid_bill_id(session, payment) is None
    assert [(p.payment_id, p.bill_id, p.kind) for p in proposals] == [
        (payment.id, setup["bill"].id, "partial")
    ]


async def test_payment_after_the_window_is_not_linked(session, setup):
    payment = await _pay(session, setup, "1283.20", on=date(2026, 9, 20))

    linked = await run_auto_match(session, setup["ws"].id)

    # BMATCH AC 13
    assert linked == 0
    assert await _paid_bill_id(session, payment) is None
    assert await propose_matches(session, setup["ws"].id) == []


async def test_propose_writes_nothing(session, setup):
    payment = await _pay(session, setup, "1283.20")

    proposals = await propose_matches(session, setup["ws"].id)
    await session.commit()

    # BMATCH AC 10 (service side): the preview links nothing.
    assert [p.kind for p in proposals] == ["exact"]
    assert await _paid_bill_id(session, payment) is None


async def test_apply_links_the_checked_pairs_and_reports_failures(session, setup):
    first = await _pay(session, setup, "500.00")
    second = await _pay(session, setup, "783.20")
    refund = await _pay(session, setup, "100.00", type_="credit")
    bill, missing = setup["bill"], uuid.uuid4()

    result = await apply_matches(
        session, setup["ws"].id,
        [(first.id, bill.id), (refund.id, bill.id), (second.id, missing)],
    )
    await session.commit()

    # BMATCH AC 11: only valid checked pairs land; each failure carries a reason.
    await session.refresh(bill)
    assert result.linked == 1
    assert result.failed == [
        (refund.id, bill.id, "A bill payment must be a debit"),
        (second.id, missing, "Bill not found"),
    ]
    assert await _paid_bill_id(session, first) == bill.id
    assert await _paid_bill_id(session, refund) is None
    assert await _paid_bill_id(session, second) is None
    assert bill.paid_amount == Decimal("500.00")


async def test_auto_match_pairs_the_payment_with_the_card_credit(session, setup):
    credit = _tx(setup["card"], DUE, "1283.20", type_="credit")
    session.add(credit)
    await session.commit()
    payment = await _pay(session, setup, "1283.20")

    linked = await run_auto_match(session, setup["ws"].id)
    await session.commit()

    # BMATCH AC 4 through BPAY AC 3: the auto link pairs the card credit too.
    await session.refresh(credit)
    bill = setup["bill"]
    await session.refresh(bill)
    assert linked == 1
    assert await _paid_bill_id(session, payment) == bill.id
    assert payment.transfer_pair_id is not None
    assert credit.transfer_pair_id == payment.transfer_pair_id
    assert bill.computed_total == Decimal("1283.20")
