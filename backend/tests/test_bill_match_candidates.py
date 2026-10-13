"""BMATCH-01: candidate bills for a payment (AC 3, 5, 12, 13, 15)."""

import uuid
from datetime import date
from decimal import Decimal

import pytest_asyncio

from app.models.account import Account
from app.models.category import Category
from app.models.transaction import Transaction
from app.services import bill_service
from app.services.bill_match_service import candidates_for, eligible_payments
from app.services.bill_payment_service import link_payment
from app.services.credit_card_service import bill_period_for_month

SEP = date(2026, 9, 1)
# The 2026-09 bill (close 5, due 12): close 2026-09-05, nominal due 2026-09-12
# (Saturday), effective due 2026-09-14, window end 2026-09-19.
CLOSE, NOMINAL_DUE, DUE, WINDOW_END = (
    date(2026, 9, 5), date(2026, 9, 12), date(2026, 9, 14), date(2026, 9, 19),
)


def _account(user, workspace, name, type_, **extra) -> Account:
    return Account(
        id=uuid.uuid4(), user_id=user.id, workspace_id=workspace.id, name=name, type=type_,
        currency="BRL", **extra,
    )


def _tx(account, on, amount, *, type_="debit", description="row", **extra) -> Transaction:
    return Transaction(
        id=uuid.uuid4(), user_id=account.user_id, workspace_id=account.workspace_id,
        account_id=account.id, description=description, amount=Decimal(amount),
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
    assert (bill.close_date, bill.due_date, bill.effective_due_date) == (CLOSE, NOMINAL_DUE, DUE)
    return {"card": card, "checking": checking, "bill": bill, "ws": test_workspace}


async def _pay(session, setup, amount, on, **extra) -> Transaction:
    tx = _tx(setup["checking"], on, amount, **extra)
    session.add(tx)
    await session.commit()
    return tx


async def test_reference_payment_on_the_effective_due_date_is_an_exact_candidate(session, setup):
    payment = await _pay(session, setup, "1283.20", DUE)

    candidates = await candidates_for(session, payment)

    # BMATCH AC 12: 2026-09-14 is inside the window of the bill due 2026-09-12.
    assert [(c.bill.id, c.kind, c.reason, c.rank) for c in candidates] == [
        (setup["bill"].id, "exact", "exact_amount", 1)
    ]


async def test_window_bounds_are_close_date_and_effective_due_plus_five(session, setup):
    # BMATCH AC 3: [close date, effective due date + 5 days].
    expected = {
        date(2026, 9, 4): "other",
        CLOSE: "exact",
        WINDOW_END: "exact",
        date(2026, 9, 20): "other",
    }
    for on, kind in expected.items():
        payment = await _pay(session, setup, "1283.20", on)
        candidates = await candidates_for(session, payment)
        assert [c.kind for c in candidates] == [kind], on


async def test_payment_after_the_window_is_listed_among_the_other_unpaid_bills(session, setup):
    payment = await _pay(session, setup, "1283.20", date(2026, 9, 20))

    candidates = await candidates_for(session, payment)

    # BMATCH AC 13: effective due 2026-09-14; 2026-09-20 is not a candidate,
    # the bill is offered as another unpaid bill.
    assert [(c.bill.id, c.kind, c.reason) for c in candidates] == [
        (setup["bill"].id, "other", "outside_window")
    ]


async def test_payment_below_the_remaining_amount_is_a_partial_candidate(session, setup):
    payment = await _pay(session, setup, "500.00", DUE)

    candidates = await candidates_for(session, payment)

    # BMATCH AC 5
    assert [(c.kind, c.reason) for c in candidates] == [("partial", "partial_amount")]


async def test_bill_with_nothing_remaining_is_no_candidate(session, setup):
    paid = await _pay(session, setup, "1283.20", DUE)
    await link_payment(session, setup["ws"].id, paid.id, setup["bill"].id)
    await session.commit()
    payment = await _pay(session, setup, "1283.20", DUE)

    # BMATCH AC 3: the remaining amount must be greater than 0.
    assert await candidates_for(session, payment) == []


async def test_candidates_come_before_the_other_unpaid_bills(session, setup):
    card = setup["card"]
    october, _ = await bill_service.get_or_create_bill(
        session, card, bill_period_for_month(date(2026, 10, 1), 5, 12)
    )
    session.add(_tx(card, date(2026, 9, 20), "300.00", bill_id=october.id))
    await bill_service.refresh_bills(session, [october.id])
    await session.commit()
    payment = await _pay(session, setup, "1283.20", DUE)

    candidates = await candidates_for(session, payment)

    # BMATCH AC 8 (service side): candidates first, then other unpaid bills.
    assert [(c.bill.id, c.kind) for c in candidates] == [
        (setup["bill"].id, "exact"),
        (october.id, "other"),
    ]


async def test_hinted_payments_rank_above_others_at_equal_amount_and_distance(
    session, setup, test_user, test_workspace
):
    flagged = Category(
        id=uuid.uuid4(), user_id=test_user.id, workspace_id=test_workspace.id,
        name="Pagamento de fatura", is_bill_payment=True,
    )
    session.add(flagged)
    await session.commit()
    plain = await _pay(session, setup, "1283.20", DUE, description="PIX enviado")
    by_word = await _pay(session, setup, "1283.20", DUE, description="Pagamento FATURA")
    by_accent = await _pay(session, setup, "1283.20", DUE, description="pgto cartão")
    by_category = await _pay(
        session, setup, "1283.20", DUE, description="PIX enviado", category_id=flagged.id
    )

    keys = {
        name: (await candidates_for(session, tx))[0].sort_key
        for name, tx in {
            "plain": plain, "word": by_word, "accent": by_accent, "category": by_category,
        }.items()
    }

    # BMATCH AC 15: a bill-payment category or "fatura"/"cartão" ranks higher.
    assert keys["word"] < keys["plain"]
    assert keys["accent"] < keys["plain"]
    assert keys["category"] < keys["plain"]


async def test_eligible_payments_are_unlinked_posted_debits_of_non_card_accounts(
    session, setup
):
    checking, card = setup["checking"], setup["card"]
    good = await _pay(session, setup, "100.00", DUE)
    rows = [
        _tx(checking, DUE, "100.00", type_="credit"),
        _tx(checking, DUE, "100.00", is_ignored=True),
        _tx(checking, DUE, "100.00", status="pending"),
        _tx(checking, DUE, "100.00", paid_bill_id=setup["bill"].id),
        _tx(card, DUE, "100.00"),
    ]
    session.add_all(rows)
    await session.commit()

    # Spec assumption "Payment eligibility".
    payments = await eligible_payments(session, setup["ws"].id)
    assert [tx.id for tx in payments] == [good.id]
