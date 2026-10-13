"""Undoing an import refreshes the bills its rows belonged to or paid (BILL-01, BPAY-01, AD-004)."""

import uuid
from datetime import date
from decimal import Decimal

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app.models.credit_card_bill import CreditCardBill
from app.models.import_log import ImportLog
from app.models.transaction import Transaction
from tests.test_credit_card_bills_api import SEP, _bill, _card, _checking, _tx


@pytest.fixture(autouse=True)
def _today(monkeypatch):
    # 2026-09-14 is the effective due date of the 2026-09 bill (close 5, due 12).
    monkeypatch.setattr("app.services.bill_service.app_today", lambda: date(2026, 9, 14))


async def _import(client, auth_headers, account, filename, rows) -> str:
    resp = await client.post(
        "/api/transactions/import",
        headers=auth_headers,
        json={
            "account_id": str(account.id),
            "transactions": rows,
            "filename": filename,
            "detected_format": "csv",
        },
    )
    assert resp.status_code == 201
    logs = (await client.get("/api/import-logs", headers=auth_headers)).json()
    return next(log["id"] for log in logs if log["filename"] == filename)


async def _get_bill(client, auth_headers, bill_id) -> dict:
    resp = await client.get(f"/api/credit-card-bills/{bill_id}", headers=auth_headers)
    assert resp.status_code == 200
    return resp.json()


async def test_undoing_a_card_import_drops_its_rows_from_the_bill_total(
    client: AsyncClient, auth_headers, session, test_user, test_workspace
):
    card = await _card(session, test_user, test_workspace)
    undone = await _import(client, auth_headers, card, "a.csv", [
        {"description": "MERCADO", "amount": "100.00", "date": "2026-09-01", "type": "debit"},
    ])
    await _import(client, auth_headers, card, "b.csv", [
        {"description": "FARMACIA", "amount": "50.00", "date": "2026-09-02", "type": "debit"},
    ])
    bill = (
        await session.execute(
            select(CreditCardBill).where(
                CreditCardBill.account_id == card.id, CreditCardBill.reference_month == SEP
            )
        )
    ).scalar_one()
    assert Decimal(str((await _get_bill(client, auth_headers, bill.id))["computed_total"])) == Decimal(
        "150.00"
    )

    resp = await client.delete(f"/api/import-logs/{undone}", headers=auth_headers)
    assert resp.status_code == 204

    data = await _get_bill(client, auth_headers, bill.id)
    assert Decimal(str(data["computed_total"])) == Decimal("50.00")


async def test_undoing_a_checking_import_unlinks_its_payment_from_the_bill(
    client: AsyncClient, auth_headers, session, test_user, test_workspace
):
    card = await _card(session, test_user, test_workspace)
    checking = await _checking(session, test_user, test_workspace)
    bill = await _bill(session, card, SEP)
    purchase = _tx(card, date(2026, 9, 1), "100.00", bill_id=bill.id)
    credit = _tx(card, date(2026, 9, 14), "100.00", type_="credit", description="PAGAMENTO RECEBIDO")
    log = ImportLog(
        id=uuid.uuid4(), user_id=test_user.id, workspace_id=test_workspace.id,
        account_id=checking.id, filename="extrato.csv", format="csv", transaction_count=1,
    )
    session.add(log)
    await session.flush()
    payment = _tx(checking, date(2026, 9, 14), "100.00", description="PAGAMENTO FATURA",
                  import_id=log.id)
    session.add_all([purchase, credit, payment])
    await session.commit()

    resp = await client.post(
        f"/api/credit-card-bills/{bill.id}/payments", headers=auth_headers,
        json={"transaction_id": str(payment.id)},
    )
    assert resp.status_code == 200
    assert resp.json()["paired_credit_id"] == str(credit.id)
    before = await _get_bill(client, auth_headers, bill.id)
    assert (Decimal(str(before["paid_amount"])), before["status"]) == (Decimal("100.00"), "paid")
    assert before["settled_on"] == "2026-09-14"

    resp = await client.delete(f"/api/import-logs/{log.id}", headers=auth_headers)
    assert resp.status_code == 204

    after = await _get_bill(client, auth_headers, bill.id)
    assert Decimal(str(after["paid_amount"])) == Decimal("0.00")
    assert after["settled_on"] is None
    assert after["status"] == "closed"
    # The transfer pair the link created is undone with the payment (BPAY AC 9).
    credit_id = credit.id
    session.expire_all()
    remaining_credit = await session.get(Transaction, credit_id)
    assert remaining_credit is not None
    assert remaining_credit.transfer_pair_id is None
