"""BPAY-02 / AD-004: automatic transfer pairing keeps the card bill current.

A bill payment linked without a counterpart leaves the card's payment credit
counted as a refund in its bill. Pairing the two legs automatically, by
`apply_pairs` or `detect_transfer_pairs`, must drop that credit from the
bill's computed total right away.
"""

import uuid
from datetime import date
from decimal import Decimal

import pytest_asyncio

from app.models.account import Account
from app.models.transaction import Transaction
from app.services import bill_service
from app.services.bill_payment_service import link_payment
from app.services.credit_card_service import bill_period_for_month
from app.services.transfer_detection_service import apply_pairs, detect_transfer_pairs

SEP, OCT = date(2026, 9, 1), date(2026, 10, 1)


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
    """September bill of 1,283.20 paid by an unpaired payment; the card's
    1,283.20 payment credit sits on the October bill (300.00 of purchases)."""
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
    payment = _tx(checking, date(2026, 9, 14), "1283.20")
    session.add_all([
        _tx(card, date(2026, 8, 20), "1283.20", bill_id=september.id),
        _tx(card, date(2026, 9, 20), "300.00", bill_id=october.id),
        payment,
    ])
    await bill_service.refresh_bills(session, [september.id, october.id])
    await session.commit()
    # Linked with no card credit yet: needs_counterpart.
    result = await link_payment(session, test_workspace.id, payment.id, september.id)
    assert result.needs_counterpart is True
    credit = _tx(card, date(2026, 9, 14), "1283.20", type_="credit", bill_id=october.id)
    session.add(credit)
    await bill_service.refresh_bills(session, [october.id])
    await session.commit()
    await session.refresh(october)
    assert october.computed_total == Decimal("-983.20")  # counted as a refund
    return {"ws": test_workspace, "payment": payment, "credit": credit, "october": october}


async def _october_total(session, setup) -> Decimal:
    await session.refresh(setup["october"])
    return setup["october"].computed_total


async def test_apply_pairs_drops_the_paired_credit_from_the_bill_total(session, setup):
    result = await apply_pairs(
        session, setup["ws"].id, [(setup["payment"].id, setup["credit"].id)]
    )
    await session.commit()

    assert result.linked == 1
    assert await _october_total(session, setup) == Decimal("300.00")


async def test_detect_transfer_pairs_drops_the_paired_credit_from_the_bill_total(
    session, setup
):
    created = await detect_transfer_pairs(
        session, setup["ws"].id, candidate_ids=[setup["credit"].id]
    )
    await session.commit()

    assert created == 1
    await session.refresh(setup["credit"])
    assert setup["credit"].transfer_pair_id is not None
    assert await _october_total(session, setup) == Decimal("300.00")
