"""Credit card bills API (BILL-01 read API, BILL-02 manual bills, BPAY-01 payments)."""

import uuid
from datetime import date
from decimal import Decimal

import pytest
import pytest_asyncio
from httpx import AsyncClient

from app.models.account import Account
from app.models.credit_card_bill import CreditCardBill
from app.models.transaction import Transaction
from app.models.workspace import Workspace
from app.services import bill_service
from app.services.credit_card_service import bill_period_for_month

SEP, OCT = date(2026, 9, 1), date(2026, 10, 1)


@pytest.fixture(autouse=True)
def _today(monkeypatch):
    # 2026-09-14 is the effective due date of the 2026-09 bill (close 5, due 12).
    monkeypatch.setattr("app.services.bill_service.app_today", lambda: date(2026, 9, 14))


async def _card(session, user, workspace, name="Cartão de Crédito Nubank") -> Account:
    account = Account(
        id=uuid.uuid4(), user_id=user.id, workspace_id=workspace.id,
        name=name, type="credit_card", currency="BRL",
        statement_close_day=5, payment_due_day=12,
    )
    session.add(account)
    await session.commit()
    return account


async def _checking(session, user, workspace, name="Nubank") -> Account:
    account = Account(
        id=uuid.uuid4(), user_id=user.id, workspace_id=workspace.id,
        name=name, type="checking", currency="BRL",
    )
    session.add(account)
    await session.commit()
    return account


async def _bill(session, account, month) -> CreditCardBill:
    bill, _ = await bill_service.get_or_create_bill(
        session, account, bill_period_for_month(month, 5, 12)
    )
    await session.commit()
    return bill


def _tx(account, on, amount, *, type_="debit", description="row", **extra) -> Transaction:
    return Transaction(
        id=uuid.uuid4(), user_id=account.user_id, workspace_id=account.workspace_id,
        account_id=account.id, description=description, amount=Decimal(amount),
        currency="BRL", date=on, effective_date=on, type=type_, source="manual", **extra,
    )


@pytest_asyncio.fixture
async def other_workspace(session, test_user) -> Workspace:
    workspace = Workspace(
        id=uuid.uuid4(), name="Outro", kind="shared", created_by_user_id=test_user.id,
        default_currency="BRL", locale="pt-BR",
    )
    session.add(workspace)
    await session.commit()
    return workspace


# --- T13: read API -----------------------------------------------------------


async def test_list_filters_by_reference_month_and_account(
    client: AsyncClient, auth_headers, session, test_user, test_workspace
):
    nubank = await _card(session, test_user, test_workspace)
    itau = await _card(session, test_user, test_workspace, "Itaú")
    nubank_sep = await _bill(session, nubank, SEP)
    nubank_oct = await _bill(session, nubank, OCT)
    itau_sep = await _bill(session, itau, SEP)

    resp = await client.get(
        "/api/credit-card-bills", headers=auth_headers, params={"reference_month": "2026-09"}
    )
    assert resp.status_code == 200
    assert {b["id"] for b in resp.json()} == {str(nubank_sep.id), str(itau_sep.id)}

    resp = await client.get(
        "/api/credit-card-bills", headers=auth_headers, params={"account_id": str(nubank.id)}
    )
    assert resp.status_code == 200
    assert [b["id"] for b in resp.json()] == [str(nubank_oct.id), str(nubank_sep.id)]

    resp = await client.get(
        "/api/credit-card-bills", headers=auth_headers,
        params={"reference_month": "2026-10", "account_id": str(itau.id)},
    )
    assert resp.status_code == 200
    assert resp.json() == []


async def test_list_rejects_a_malformed_reference_month(client: AsyncClient, auth_headers):
    resp = await client.get(
        "/api/credit-card-bills", headers=auth_headers, params={"reference_month": "setembro"}
    )
    assert resp.status_code == 422


async def test_bill_returns_period_amounts_status_and_payments(
    client: AsyncClient, auth_headers, session, test_user, test_workspace
):
    card = await _card(session, test_user, test_workspace)
    checking = await _checking(session, test_user, test_workspace)
    bill = await _bill(session, card, SEP)
    session.add_all([
        _tx(card, date(2026, 8, 20), "1000.00", bill_id=bill.id),
        _tx(card, date(2026, 8, 25), "283.20", bill_id=bill.id),
    ])
    payment = _tx(
        checking, date(2026, 9, 14), "-500.00", description="Pagamento fatura",
        paid_bill_id=bill.id,
    )
    session.add(payment)
    await bill_service.refresh_bills(session, [bill.id])
    await session.commit()

    resp = await client.get(f"/api/credit-card-bills/{bill.id}", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    # P1 AC 2: close 5 / due 12, reference month 2026-09.
    assert data["reference_month"] == "2026-09-01"
    assert (data["period_start"], data["period_end"]) == ("2026-08-05", "2026-09-04")
    assert data["close_date"] == "2026-09-05"
    assert data["due_date"] == "2026-09-12"
    assert data["effective_due_date"] == "2026-09-14"
    # P1 AC 5 and BPAY AC 6: 500.00 paid against 1,283.20 on the effective due date.
    assert data["source"] == "auto"
    assert data["computed_total"] == 1283.20
    assert data["declared_total"] is None
    assert data["target_amount"] == 1283.20
    assert data["paid_amount"] == 500.00
    assert data["remaining_amount"] == 783.20
    assert data["overpaid_amount"] == 0.0
    assert data["status"] == "partially_paid"
    assert data["settled_on"] is None
    assert data["payments"] == [{
        "id": str(payment.id), "account_id": str(checking.id), "date": "2026-09-14",
        "description": "Pagamento fatura", "amount": 500.00, "currency": "BRL",
    }]


async def test_bill_of_another_workspace_is_not_found(
    client: AsyncClient, auth_headers, session, test_user, other_workspace
):
    foreign_card = await _card(session, test_user, other_workspace)
    foreign = await _bill(session, foreign_card, SEP)

    resp = await client.get(f"/api/credit-card-bills/{foreign.id}", headers=auth_headers)
    assert resp.status_code == 404

    resp = await client.get(
        "/api/credit-card-bills", headers=auth_headers, params={"account_id": str(foreign_card.id)}
    )
    assert resp.status_code == 200
    assert resp.json() == []


async def test_unknown_bill_is_not_found(client: AsyncClient, auth_headers):
    resp = await client.get(f"/api/credit-card-bills/{uuid.uuid4()}", headers=auth_headers)
    assert resp.status_code == 404


async def test_a_viewer_can_read_bills(
    client: AsyncClient, viewer_auth_headers, session, test_user, test_workspace
):
    card = await _card(session, test_user, test_workspace)
    bill = await _bill(session, card, SEP)

    listed = await client.get("/api/credit-card-bills", headers=viewer_auth_headers)
    assert listed.status_code == 200
    assert [b["id"] for b in listed.json()] == [str(bill.id)]
    detail = await client.get(f"/api/credit-card-bills/{bill.id}", headers=viewer_auth_headers)
    assert detail.status_code == 200
    # Edge case: a closed bill with no rows and no declared total reads `paid`.
    assert detail.json()["status"] == "paid"


async def test_account_bills_route_returns_the_new_fields(
    client: AsyncClient, auth_headers, session, test_user, test_workspace
):
    card = await _card(session, test_user, test_workspace)
    bill = await _bill(session, card, SEP)
    session.add(_tx(card, date(2026, 8, 20), "1283.20", bill_id=bill.id))
    await bill_service.refresh_bills(session, [bill.id])
    await session.commit()

    resp = await client.get(f"/api/accounts/{card.id}/bills", headers=auth_headers)
    assert resp.status_code == 200
    [data] = resp.json()
    # Fields the existing frontend reads keep their meaning.
    assert data["due_date"] == "2026-09-12"
    assert data["total_amount"] == 0.0
    assert data["external_id"] is None
    assert data["currency"] == "BRL"
    assert data["minimum_payment"] is None
    # New fields.
    assert data["effective_due_date"] == "2026-09-14"
    assert data["computed_total"] == 1283.20
    assert data["remaining_amount"] == 1283.20
    assert data["status"] == "closed"
    assert data["payments"] == []


# --- T15: manual bill endpoints ----------------------------------------------

MANUAL = {"reference_month": "2026-09-01", "close_date": "2026-09-05", "due_date": "2026-09-12"}


async def test_create_manual_bill_returns_201_and_links_rows(
    client: AsyncClient, auth_headers, session, test_user, test_workspace
):
    card = await _card(session, test_user, test_workspace)
    card.statement_close_day = card.payment_due_day = None
    row = _tx(card, date(2026, 8, 20), "300.00")
    session.add(row)
    await session.commit()

    resp = await client.post(
        "/api/credit-card-bills", headers=auth_headers,
        json={**MANUAL, "account_id": str(card.id), "declared_total": "310.00"},
    )
    assert resp.status_code == 201, resp.text
    data = resp.json()
    assert data["source"] == "manual"
    assert (data["period_start"], data["period_end"]) == ("2026-08-05", "2026-09-04")
    assert data["effective_due_date"] == "2026-09-14"
    assert data["computed_total"] == 300.00
    assert data["declared_total"] == 310.00
    assert data["target_amount"] == 310.00
    await session.refresh(row)
    assert str(row.bill_id) == data["id"]


async def test_create_bill_for_an_existing_reference_month_is_409(
    client: AsyncClient, auth_headers, session, test_user, test_workspace
):
    card = await _card(session, test_user, test_workspace)
    await _bill(session, card, SEP)

    resp = await client.post(
        "/api/credit-card-bills", headers=auth_headers, json={**MANUAL, "account_id": str(card.id)}
    )
    assert resp.status_code == 409
    listed = await client.get(
        "/api/credit-card-bills", headers=auth_headers, params={"account_id": str(card.id)}
    )
    assert len(listed.json()) == 1


async def test_create_bill_with_a_negative_declared_total_is_422(
    client: AsyncClient, auth_headers, session, test_user, test_workspace
):
    card = await _card(session, test_user, test_workspace)
    resp = await client.post(
        "/api/credit-card-bills", headers=auth_headers,
        json={**MANUAL, "account_id": str(card.id), "declared_total": "-1.00"},
    )
    assert resp.status_code == 422


async def test_create_bill_on_another_workspace_card_is_404(
    client: AsyncClient, auth_headers, session, test_user, other_workspace
):
    foreign_card = await _card(session, test_user, other_workspace)
    resp = await client.post(
        "/api/credit-card-bills", headers=auth_headers,
        json={**MANUAL, "account_id": str(foreign_card.id)},
    )
    assert resp.status_code == 404


async def test_patch_declared_total_recomputes_amounts(
    client: AsyncClient, auth_headers, session, test_user, test_workspace
):
    card = await _card(session, test_user, test_workspace)
    bill = await _bill(session, card, SEP)
    session.add(_tx(card, date(2026, 8, 20), "1283.20", bill_id=bill.id))
    await bill_service.refresh_bills(session, [bill.id])
    await session.commit()

    resp = await client.patch(
        f"/api/credit-card-bills/{bill.id}", headers=auth_headers, json={"declared_total": "1300.00"}
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["declared_total"] == 1300.00
    assert data["target_amount"] == 1300.00
    assert data["remaining_amount"] == 1300.00
    assert data["status"] == "closed"


async def test_patch_negative_declared_total_is_422(
    client: AsyncClient, auth_headers, session, test_user, test_workspace
):
    card = await _card(session, test_user, test_workspace)
    bill = await _bill(session, card, SEP)
    resp = await client.patch(
        f"/api/credit-card-bills/{bill.id}", headers=auth_headers, json={"declared_total": "-3.00"}
    )
    assert resp.status_code == 422


async def test_patch_provider_bill_dates_is_422_and_delete_is_422(
    client: AsyncClient, auth_headers, session, test_user, test_workspace
):
    card = await _card(session, test_user, test_workspace)
    provider = CreditCardBill(
        user_id=card.user_id, workspace_id=card.workspace_id, account_id=card.id,
        external_id="pluggy-1", due_date=date(2026, 9, 12), total_amount=Decimal("900.00"),
        currency="BRL",
    )
    session.add(provider)
    await session.commit()

    resp = await client.patch(
        f"/api/credit-card-bills/{provider.id}", headers=auth_headers,
        json={"due_date": "2026-09-15"},
    )
    assert resp.status_code == 422
    resp = await client.delete(f"/api/credit-card-bills/{provider.id}", headers=auth_headers)
    assert resp.status_code == 422
    detail = await client.get(f"/api/credit-card-bills/{provider.id}", headers=auth_headers)
    assert detail.json()["due_date"] == "2026-09-12"


async def test_delete_bill_is_204_and_keeps_its_transactions(
    client: AsyncClient, auth_headers, session, test_user, test_workspace
):
    card = await _card(session, test_user, test_workspace)
    bill = await _bill(session, card, SEP)
    row = _tx(card, date(2026, 8, 20), "10.00", bill_id=bill.id)
    session.add(row)
    await session.commit()

    resp = await client.delete(f"/api/credit-card-bills/{bill.id}", headers=auth_headers)
    assert resp.status_code == 204
    assert (await client.get(f"/api/credit-card-bills/{bill.id}", headers=auth_headers)).status_code == 404
    await session.refresh(row)
    assert row.bill_id is None


async def test_write_routes_on_another_workspace_bill_are_404(
    client: AsyncClient, auth_headers, session, test_user, other_workspace
):
    foreign = await _bill(session, await _card(session, test_user, other_workspace), SEP)

    patch = await client.patch(
        f"/api/credit-card-bills/{foreign.id}", headers=auth_headers, json={"declared_total": "1"}
    )
    delete = await client.delete(f"/api/credit-card-bills/{foreign.id}", headers=auth_headers)
    assert (patch.status_code, delete.status_code) == (404, 404)


async def test_a_viewer_cannot_create_edit_or_delete_bills(
    client: AsyncClient, viewer_auth_headers, session, test_user, test_workspace
):
    card = await _card(session, test_user, test_workspace)
    bill = await _bill(session, card, OCT)

    create = await client.post(
        "/api/credit-card-bills", headers=viewer_auth_headers,
        json={**MANUAL, "account_id": str(card.id)},
    )
    patch = await client.patch(
        f"/api/credit-card-bills/{bill.id}", headers=viewer_auth_headers,
        json={"declared_total": "1.00"},
    )
    delete = await client.delete(f"/api/credit-card-bills/{bill.id}", headers=viewer_auth_headers)
    assert (create.status_code, patch.status_code, delete.status_code) == (403, 403, 403)
