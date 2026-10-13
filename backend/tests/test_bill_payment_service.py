"""BPAY-01: link and unlink bill payments (AC 1, 5-8, 10-12 and edge cases)."""

import uuid
from datetime import date
from decimal import Decimal

import pytest
import pytest_asyncio

from app.models.account import Account
from app.models.credit_card_bill import CreditCardBill
from app.models.transaction import Transaction
from app.models.workspace import Workspace
from app.services import bill_service
from app.services.bill_payment_service import BillPaymentError, link_payment, unlink_payment
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
        account_id=account.id, description="row", amount=Decimal(amount),
        currency=extra.pop("currency", "BRL"), date=on, effective_date=on, type=type_,
        source="manual", **extra,
    )


@pytest_asyncio.fixture
async def setup(session, test_user, test_workspace):
    """The reference case: a 1,283.20 September bill on "Cartão de Crédito Nubank"."""
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


async def _link(session, setup, tx, bill=None):
    result = await link_payment(session, setup["ws"].id, tx.id, (bill or setup["bill"]).id)
    await session.commit()
    return result


async def test_reference_payment_marks_the_bill_paid(session, setup):
    payment = await _pay(session, setup, "1283.20")

    result = await _link(session, setup, payment)

    # BPAY AC 1 and 5: the link is recorded; paid, remaining 0.
    bill = setup["bill"]
    await session.refresh(payment)
    await session.refresh(bill)
    assert payment.paid_bill_id == bill.id
    assert result.bill.id == bill.id
    assert bill.paid_amount == Decimal("1283.20")
    assert bill_service.bill_status(bill, DUE) == "paid"
    assert bill_service.bill_amounts(bill).remaining == Decimal("0.00")


async def test_partial_payment_is_partially_paid(session, setup):
    await _link(session, setup, await _pay(session, setup, "500.00"))

    # BPAY AC 6
    bill = setup["bill"]
    await session.refresh(bill)
    assert bill_service.bill_status(bill, DUE) == "partially_paid"
    assert bill_service.bill_amounts(bill).remaining == Decimal("783.20")


async def test_two_partial_payments_summing_the_target_are_paid(session, setup):
    await _link(session, setup, await _pay(session, setup, "500.00", on=date(2026, 9, 10)))
    await _link(session, setup, await _pay(session, setup, "783.20"))

    # BPAY AC 7
    bill = setup["bill"]
    await session.refresh(bill)
    assert bill_service.bill_status(bill, DUE) == "paid"
    assert bill.settled_on == DUE


async def test_overpayment_is_paid_with_the_overpaid_amount(session, setup):
    await _link(session, setup, await _pay(session, setup, "1300.00"))

    # BPAY AC 8
    bill = setup["bill"]
    await session.refresh(bill)
    assert bill_service.bill_status(bill, DUE) == "paid"
    assert bill_service.bill_amounts(bill).overpaid == Decimal("16.80")


async def test_unlinking_removes_the_link_and_recomputes_status(session, setup):
    payment = await _pay(session, setup, "1283.20")
    await _link(session, setup, payment)

    bill = await unlink_payment(session, setup["ws"].id, payment.id)
    await session.commit()

    await session.refresh(payment)
    await session.refresh(bill)
    assert payment.paid_bill_id is None
    assert bill.paid_amount == Decimal("0.00")
    assert bill_service.bill_status(bill, DUE) == "closed"


@pytest.mark.parametrize(
    "case",
    ["credit", "card_account", "ignored", "currency", "zero", "negative"],
)
async def test_ineligible_payments_are_refused_with_422(session, setup, case):
    if case == "card_account":
        tx = _tx(setup["card"], DUE, "100.00")
        session.add(tx)
        await session.commit()
    else:
        extra = {
            "credit": {"type_": "credit"},
            "ignored": {"is_ignored": True},
            "currency": {"currency": "USD"},
        }.get(case, {})
        amount = {"zero": "0.00", "negative": "-10.00"}.get(case, "100.00")
        tx = await _pay(session, setup, amount, **extra)

    # BPAY AC 10 and the zero/negative amount edge case.
    with pytest.raises(BillPaymentError) as exc:
        await link_payment(session, setup["ws"].id, tx.id, setup["bill"].id)
    assert exc.value.status_code == 422
    assert tx.paid_bill_id is None


async def test_a_payment_of_another_bill_is_refused_with_409(session, setup):
    payment = await _pay(session, setup, "1283.20")
    await _link(session, setup, payment)
    october, _ = await bill_service.get_or_create_bill(
        session, setup["card"], bill_period_for_month(date(2026, 10, 1), 5, 12)
    )
    await session.commit()

    # BPAY AC 11
    with pytest.raises(BillPaymentError) as exc:
        await link_payment(session, setup["ws"].id, payment.id, october.id)
    assert exc.value.status_code == 409
    assert payment.paid_bill_id == setup["bill"].id


async def test_bill_or_transaction_of_another_workspace_is_404(session, setup, test_user):
    other = Workspace(
        id=uuid.uuid4(), name="Outro", kind="shared", created_by_user_id=test_user.id,
        default_currency="BRL", locale="pt-BR",
    )
    session.add(other)
    await session.flush()
    foreign_card = _account(
        test_user, other, "Outro cartão", "credit_card", statement_close_day=5, payment_due_day=12
    )
    foreign_checking = _account(test_user, other, "Outra conta", "checking")
    session.add_all([foreign_card, foreign_checking])
    await session.flush()
    foreign_bill, _ = await bill_service.get_or_create_bill(
        session, foreign_card, bill_period_for_month(SEP, 5, 12)
    )
    foreign_payment = _tx(foreign_checking, DUE, "100.00")
    session.add(foreign_payment)
    await session.commit()
    own_payment = await _pay(session, setup, "100.00")

    # BPAY AC 12
    with pytest.raises(BillPaymentError) as bill_exc:
        await link_payment(session, setup["ws"].id, own_payment.id, foreign_bill.id)
    with pytest.raises(BillPaymentError) as tx_exc:
        await link_payment(session, setup["ws"].id, foreign_payment.id, setup["bill"].id)
    assert (bill_exc.value.status_code, tx_exc.value.status_code) == (404, 404)


async def test_payments_still_link_to_bills_of_a_closed_card(session, setup):
    setup["card"].is_closed = True
    await session.commit()

    await _link(session, setup, await _pay(session, setup, "1283.20"))

    bill: CreditCardBill = setup["bill"]
    await session.refresh(bill)
    assert bill.paid_amount == Decimal("1283.20")
