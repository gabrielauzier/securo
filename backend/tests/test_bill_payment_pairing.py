"""BPAY-02: a linked payment is paired with the card credit (AC 3, 4, 9)."""

import uuid
from datetime import date
from decimal import Decimal

import pytest_asyncio

from app.models.account import Account
from app.models.transaction import Transaction
from app.services import bill_service, transaction_service
from app.services.bill_payment_service import link_payment, unlink_payment
from app.services.credit_card_service import bill_period_for_month

SEP, OCT = date(2026, 9, 1), date(2026, 10, 1)
PAID_ON = date(2026, 9, 14)


def _account(user, workspace, name, type_, **extra) -> Account:
    return Account(
        id=uuid.uuid4(), user_id=user.id, workspace_id=workspace.id, name=name, type=type_,
        currency="BRL", **extra,
    )


def _tx(account, on, amount, type_="debit", **extra) -> Transaction:
    return Transaction(
        id=uuid.uuid4(), user_id=account.user_id, workspace_id=account.workspace_id,
        account_id=account.id, description="row", amount=Decimal(amount), currency="BRL",
        date=on, effective_date=on, type=type_, source="manual", **extra,
    )


@pytest_asyncio.fixture
async def setup(session, test_user, test_workspace):
    """The 1,283.20 September bill, and a 300.00 purchase on the October bill.

    The card's "Pagamento recebido" credit, dated after the close, lands on
    the October bill (period 09-05..10-04)."""
    card = _account(
        test_user, test_workspace, "Cartão de Crédito Nubank", "credit_card",
        statement_close_day=5, payment_due_day=12,
    )
    checking = _account(test_user, test_workspace, "Nubank", "checking")
    session.add_all([card, checking])
    await session.flush()
    september, _ = await bill_service.get_or_create_bill(
        session, card, bill_period_for_month(SEP, 5, 12)
    )
    october, _ = await bill_service.get_or_create_bill(
        session, card, bill_period_for_month(OCT, 5, 12)
    )
    session.add_all([
        _tx(card, date(2026, 8, 20), "1283.20", bill_id=september.id),
        _tx(card, date(2026, 9, 20), "300.00", bill_id=october.id),
    ])
    await bill_service.refresh_bills(session, [september.id, october.id])
    await session.commit()
    return {
        "ws": test_workspace, "card": card, "checking": checking,
        "september": september, "october": october,
    }


async def _credit(session, setup, on, amount="1283.20") -> Transaction:
    credit = _tx(setup["card"], on, amount, "credit", bill_id=setup["october"].id)
    session.add(credit)
    await bill_service.refresh_bills(session, [setup["october"].id])
    await session.commit()
    return credit


async def _payment(session, setup, amount="1283.20") -> Transaction:
    payment = _tx(setup["checking"], PAID_ON, amount)
    session.add(payment)
    await session.commit()
    return payment


async def _link(session, setup, payment):
    result = await link_payment(session, setup["ws"].id, payment.id, setup["september"].id)
    await session.commit()
    return result


async def _refresh(session, *rows):
    for row in rows:
        await session.refresh(row)


async def test_payment_is_paired_with_the_card_credit_inside_the_window(session, setup):
    credit = await _credit(session, setup, date(2026, 9, 15))
    payment = await _payment(session, setup)
    october = setup["october"]
    await session.refresh(october)
    assert october.computed_total == Decimal("-983.20")

    result = await _link(session, setup, payment)

    # BPAY AC 3: the payment and the credit are one transfer, made by the link.
    await _refresh(session, payment, credit, october, setup["september"])
    assert payment.transfer_pair_id is not None
    assert credit.transfer_pair_id == payment.transfer_pair_id
    assert payment.bill_payment_pair is True
    assert result.paired_credit_id == credit.id
    assert result.needs_counterpart is False
    # The paired card credit no longer counts in the computed total.
    assert october.computed_total == Decimal("300.00")
    assert setup["september"].computed_total == Decimal("1283.20")
    assert bill_service.bill_status(setup["september"], PAID_ON) == "paid"


async def test_without_a_card_credit_the_link_stays_and_needs_a_counterpart(session, setup):
    payment = await _payment(session, setup)

    result = await _link(session, setup, payment)

    # BPAY AC 4
    await session.refresh(payment)
    assert payment.paid_bill_id == setup["september"].id
    assert payment.transfer_pair_id is None
    assert result.paired_credit_id is None
    assert result.needs_counterpart is True


async def test_a_credit_outside_the_window_or_of_another_amount_is_not_paired(session, setup):
    # The default transfer rule reaches 2 days around the payment date.
    late = await _credit(session, setup, date(2026, 9, 17))
    other_amount = await _credit(session, setup, date(2026, 9, 14), "1283.21")
    payment = await _payment(session, setup)

    result = await _link(session, setup, payment)

    await _refresh(session, late, other_amount)
    assert result.needs_counterpart is True
    assert late.transfer_pair_id is None
    assert other_amount.transfer_pair_id is None


async def test_a_credit_on_the_window_edge_is_paired(session, setup):
    edge = await _credit(session, setup, date(2026, 9, 16))
    payment = await _payment(session, setup)

    result = await _link(session, setup, payment)

    assert result.paired_credit_id == edge.id


async def test_unlinking_removes_the_pair_the_link_created(session, setup):
    credit = await _credit(session, setup, date(2026, 9, 15))
    payment = await _payment(session, setup)
    await _link(session, setup, payment)

    await unlink_payment(session, setup["ws"].id, payment.id)
    await session.commit()

    # BPAY AC 9: link removed, pair undone, totals and status recomputed.
    september, october = setup["september"], setup["october"]
    await _refresh(session, payment, credit, september, october)
    assert payment.paid_bill_id is None
    assert payment.transfer_pair_id is None
    assert credit.transfer_pair_id is None
    assert payment.bill_payment_pair is False
    assert october.computed_total == Decimal("-983.20")
    assert september.paid_amount == Decimal("0.00")
    assert bill_service.bill_status(september, PAID_ON) == "closed"


async def test_a_pair_the_user_made_before_linking_survives_the_unlink(session, setup):
    credit = await _credit(session, setup, date(2026, 9, 15))
    payment = await _payment(session, setup)
    await transaction_service.link_existing_as_transfer(
        session, setup["ws"].id, [payment.id, credit.id]
    )
    pair_id = payment.transfer_pair_id

    result = await _link(session, setup, payment)
    october = setup["october"]
    await _refresh(session, payment, october)
    assert payment.bill_payment_pair is False
    assert result.needs_counterpart is False
    assert october.computed_total == Decimal("300.00")

    await unlink_payment(session, setup["ws"].id, payment.id)
    await session.commit()

    await _refresh(session, payment, credit, october)
    assert payment.transfer_pair_id == pair_id
    assert credit.transfer_pair_id == pair_id
    # Without the payment link the credit is no longer the card leg of a bill payment.
    assert october.computed_total == Decimal("-983.20")


async def test_pairing_a_linked_payment_by_hand_refreshes_the_card_bill(session, setup):
    credit = await _credit(session, setup, date(2026, 9, 25))  # outside the window
    payment = await _payment(session, setup)
    await _link(session, setup, payment)

    await transaction_service.link_existing_as_transfer(
        session, setup["ws"].id, [payment.id, credit.id]
    )

    october = setup["october"]
    await session.refresh(october)
    assert october.computed_total == Decimal("300.00")


async def test_deleting_the_bill_removes_the_pair_its_link_created(session, setup):
    credit = await _credit(session, setup, date(2026, 9, 15))
    payment = await _payment(session, setup)
    await _link(session, setup, payment)

    await bill_service.delete_bill(session, setup["ws"].id, setup["september"].id)
    await session.commit()

    # P1 AC 11 unlinks the payment, which undoes the pair as in BPAY AC 9.
    await _refresh(session, payment, credit)
    assert payment.paid_bill_id is None
    assert payment.transfer_pair_id is None
    assert credit.transfer_pair_id is None
