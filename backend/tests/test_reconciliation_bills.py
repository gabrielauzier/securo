"""BPAY-02: accepting a reconciliation transfer keeps the paid bill current.

Verifier round 3 gap 1. `accept_suggestion` pairs the two legs with a plain
ORM write (`leg.transfer_pair_id = pair_id`) and never calls `bill_service`.
The AD-005 session listener (T76) refreshes the bill at that commit, so the
route needs no explicit `touch`, and the T64 guard (`test_ad004_guard.py`) is
not extended: it covers Core bulk statements, which bypass ORM events, while
every ORM `transfer_pair_id` assignment is now covered by the listener.
"""

from datetime import date
from decimal import Decimal

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app.models.reconciliation import ReconciliationSuggestion
from app.models.transaction import Transaction
from app.services import bill_service
from app.services.transfer_detection_service import detect_transfer_pairs
from tests.test_credit_card_bills_api import SEP, _bill, _card, _checking, _tx


@pytest.fixture(autouse=True)
def _today(monkeypatch):
    # 2026-09-14 is the effective due date of the 2026-09 bill (close 5, due 12).
    monkeypatch.setattr("app.services.bill_service.app_today", lambda: date(2026, 9, 14))


async def test_accepting_the_transfer_of_a_linked_payment_keeps_the_bill_total(
    client: AsyncClient, auth_headers, session, test_user, test_workspace
):
    card = await _card(session, test_user, test_workspace)
    checking = await _checking(session, test_user, test_workspace)
    bill = await _bill(session, card, SEP)
    session.add(_tx(card, date(2026, 8, 20), "1000.00", bill_id=bill.id))
    payment = _tx(checking, date(2026, 9, 4), "600.00", description="PAGAMENTO FATURA")
    session.add(payment)
    await session.commit()

    # Linked before the card credit arrives, so it waits for a counterpart.
    resp = await client.post(
        f"/api/credit-card-bills/{bill.id}/payments",
        json={"transaction_id": str(payment.id)},
        headers=auth_headers,
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["needs_counterpart"] is True

    # The card credit lands, next to a second, indistinguishable debit.
    credit = _tx(
        card, date(2026, 9, 4), "600.00", type_="credit",
        description="PAGAMENTO RECEBIDO", bill_id=bill.id,
    )
    session.add_all(
        [credit, _tx(checking, date(2026, 9, 4), "600.00", description="PAGAMENTO FATURA")]
    )
    # The write path refreshes the bill, as every transaction write does (AD-004).
    await bill_service.touch(session, [credit.id])
    await session.commit()
    # Unpaired, the credit is a refund: 1,000.00 - 600.00.
    await session.refresh(bill)
    assert bill.computed_total == Decimal("400.00")

    # Ambiguous, so it becomes a question rather than a link.
    assert await detect_transfer_pairs(session, test_workspace.id) == 0
    await session.commit()
    queue = (
        await session.execute(
            select(ReconciliationSuggestion).where(
                ReconciliationSuggestion.workspace_id == test_workspace.id,
                ReconciliationSuggestion.status == "pending",
            )
        )
    ).scalars().all()
    question = next(
        row for row in queue
        if {row.transaction_id, row.expectation_id} == {payment.id, credit.id}
    )

    resp = await client.post(
        f"/api/reconciliation/suggestions/{question.id}/accept", headers=auth_headers
    )
    assert resp.status_code == 200, resp.text

    pair_ids = (
        await session.execute(
            select(Transaction.transfer_pair_id).where(Transaction.id.in_([payment.id, credit.id]))
        )
    ).scalars().all()
    assert len(set(pair_ids)) == 1 and pair_ids[0] is not None

    resp = await client.get(f"/api/credit-card-bills/{bill.id}", headers=auth_headers)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    # The credit is the card leg of the payment now, not a refund.
    assert Decimal(str(body["computed_total"])) == Decimal("1000.00")
    assert Decimal(str(body["paid_amount"])) == Decimal("600.00")
    # 600.00 of 1,000.00 paid: the bill is not paid.
    assert body["status"] == "partially_paid"
