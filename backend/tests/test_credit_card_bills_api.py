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


# --- T20: payment endpoints --------------------------------------------------


async def _reference(session, user, workspace):
    """The reference case: the 1,283.20 September bill, the card's payment
    credit, the 1,283.20 payment from "Nubank" and a 100.00 expense."""
    card = await _card(session, user, workspace)
    checking = await _checking(session, user, workspace)
    bill = await _bill(session, card, SEP)
    october = await _bill(session, card, OCT)
    credit = _tx(card, date(2026, 9, 15), "1283.20", type_="credit", bill_id=october.id)
    payment = _tx(checking, date(2026, 9, 14), "1283.20", description="Pagamento fatura")
    session.add_all([
        _tx(card, date(2026, 8, 20), "1283.20", bill_id=bill.id),
        credit,
        payment,
        _tx(checking, date(2026, 9, 3), "100.00", description="Mercado"),
    ])
    await bill_service.refresh_bills(session, [bill.id, october.id])
    await session.commit()
    return {"card": card, "checking": checking, "bill": bill, "credit": credit, "payment": payment}


async def _september_expenses(client, headers) -> float:
    resp = await client.get(
        "/api/dashboard/summary", headers=headers, params={"month": "2026-09-01"}
    )
    assert resp.status_code == 200
    return resp.json()["monthly_expenses"]


async def test_linking_the_reference_payment_pays_the_bill_and_leaves_the_expenses(
    client: AsyncClient, auth_headers, session, test_user, test_workspace
):
    ref = await _reference(session, test_user, test_workspace)
    assert await _september_expenses(client, auth_headers) == 1383.20

    resp = await client.post(
        f"/api/credit-card-bills/{ref['bill'].id}/payments", headers=auth_headers,
        json={"transaction_id": str(ref["payment"].id)},
    )

    # BPAY Independent Test: expenses exclude 1,283.20 and the bill reports paid.
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["transaction_id"] == str(ref["payment"].id)
    assert data["bill"]["status"] == "paid"
    assert data["bill"]["remaining_amount"] == 0.0
    assert data["bill"]["paid_amount"] == 1283.20
    assert data["paired_credit_id"] == str(ref["credit"].id)
    assert data["needs_counterpart"] is False
    assert await _september_expenses(client, auth_headers) == 100.0


async def test_unlinking_a_payment_returns_the_bill_and_restores_the_expense(
    client: AsyncClient, auth_headers, session, test_user, test_workspace
):
    ref = await _reference(session, test_user, test_workspace)
    await client.post(
        f"/api/credit-card-bills/{ref['bill'].id}/payments", headers=auth_headers,
        json={"transaction_id": str(ref["payment"].id)},
    )

    resp = await client.delete(
        f"/api/credit-card-bills/payments/{ref['payment'].id}", headers=auth_headers
    )

    assert resp.status_code == 200, resp.text
    assert resp.json()["id"] == str(ref["bill"].id)
    assert resp.json()["status"] == "closed"
    assert resp.json()["paid_amount"] == 0.0
    assert await _september_expenses(client, auth_headers) == 1383.20


async def test_unlinking_a_transaction_that_pays_no_bill_is_404(
    client: AsyncClient, auth_headers, session, test_user, test_workspace
):
    ref = await _reference(session, test_user, test_workspace)
    resp = await client.delete(
        f"/api/credit-card-bills/payments/{ref['payment'].id}", headers=auth_headers
    )
    assert resp.status_code == 404


async def test_linking_a_credit_is_422(
    client: AsyncClient, auth_headers, session, test_user, test_workspace
):
    ref = await _reference(session, test_user, test_workspace)
    resp = await client.post(
        f"/api/credit-card-bills/{ref['bill'].id}/payments", headers=auth_headers,
        json={"transaction_id": str(ref["credit"].id)},
    )
    assert resp.status_code == 422


async def test_linking_a_payment_of_another_bill_is_409(
    client: AsyncClient, auth_headers, session, test_user, test_workspace
):
    ref = await _reference(session, test_user, test_workspace)
    october = await _bill(session, ref["card"], OCT)
    first = await client.post(
        f"/api/credit-card-bills/{ref['bill'].id}/payments", headers=auth_headers,
        json={"transaction_id": str(ref["payment"].id)},
    )
    assert first.status_code == 200

    resp = await client.post(
        f"/api/credit-card-bills/{october.id}/payments", headers=auth_headers,
        json={"transaction_id": str(ref["payment"].id)},
    )
    assert resp.status_code == 409


async def test_linking_across_workspaces_is_404(
    client: AsyncClient, auth_headers, session, test_user, test_workspace, other_workspace
):
    ref = await _reference(session, test_user, test_workspace)
    foreign = await _bill(session, await _card(session, test_user, other_workspace), SEP)

    to_foreign_bill = await client.post(
        f"/api/credit-card-bills/{foreign.id}/payments", headers=auth_headers,
        json={"transaction_id": str(ref["payment"].id)},
    )
    unknown_tx = await client.post(
        f"/api/credit-card-bills/{ref['bill'].id}/payments", headers=auth_headers,
        json={"transaction_id": str(uuid.uuid4())},
    )
    assert (to_foreign_bill.status_code, unknown_tx.status_code) == (404, 404)


async def test_a_viewer_cannot_link_or_unlink_payments(
    client: AsyncClient, viewer_auth_headers, session, test_user, test_workspace
):
    ref = await _reference(session, test_user, test_workspace)

    link = await client.post(
        f"/api/credit-card-bills/{ref['bill'].id}/payments", headers=viewer_auth_headers,
        json={"transaction_id": str(ref["payment"].id)},
    )
    unlink = await client.delete(
        f"/api/credit-card-bills/payments/{ref['payment'].id}", headers=viewer_auth_headers
    )
    assert (link.status_code, unlink.status_code) == (403, 403)


# --- T28: matching endpoints and the list indicator -------------------------


async def _matching(session, user, workspace):
    """The 1,283.20 September bill, a 300.00 October bill, the reference payment
    on 2026-09-14 and a 100.00 expense outside every window."""
    card = await _card(session, user, workspace)
    checking = await _checking(session, user, workspace)
    bill = await _bill(session, card, SEP)
    october = await _bill(session, card, OCT)
    payment = _tx(checking, date(2026, 9, 14), "1283.20", description="Pagamento fatura")
    expense = _tx(checking, date(2026, 9, 3), "100.00", description="Mercado")
    session.add_all([
        _tx(card, date(2026, 8, 20), "1283.20", bill_id=bill.id),
        _tx(card, date(2026, 9, 20), "300.00", bill_id=october.id),
        payment,
        expense,
    ])
    await bill_service.refresh_bills(session, [bill.id, october.id])
    await session.commit()
    return {
        "card": card, "checking": checking, "bill": bill, "october": october,
        "payment": payment, "expense": expense,
    }


async def test_payment_candidates_list_candidates_first_then_other_unpaid_bills(
    client: AsyncClient, auth_headers, session, test_user, test_workspace
):
    ref = await _matching(session, test_user, test_workspace)

    resp = await client.get(
        "/api/credit-card-bills/payment-candidates", headers=auth_headers,
        params={"transaction_id": str(ref["payment"].id)},
    )

    # BMATCH AC 8: card, reference month, effective due date, target,
    # remaining and match reason; candidates before the other unpaid bills.
    assert resp.status_code == 200, resp.text
    rows = resp.json()
    assert [(r["bill_id"], r["kind"], r["rank"]) for r in rows] == [
        (str(ref["bill"].id), "exact", 1),
        (str(ref["october"].id), "other", 2),
    ]
    first = rows[0]
    assert first["account_name"] == "Cartão de Crédito Nubank"
    assert first["reference_month"] == "2026-09-01"
    assert first["effective_due_date"] == "2026-09-14"
    assert first["target_amount"] == 1283.20
    assert first["remaining_amount"] == 1283.20
    assert first["reason"] == "exact_amount"
    assert rows[1]["reason"] == "outside_window"


async def test_payment_candidates_of_an_unknown_transaction_are_404(
    client: AsyncClient, auth_headers, session, test_user, other_workspace
):
    foreign = await _checking(session, test_user, other_workspace)
    tx = _tx(foreign, date(2026, 9, 14), "10.00")
    session.add(tx)
    await session.commit()

    resp = await client.get(
        "/api/credit-card-bills/payment-candidates", headers=auth_headers,
        params={"transaction_id": str(tx.id)},
    )
    assert resp.status_code == 404


async def test_match_preview_lists_proposals_and_writes_nothing(
    client: AsyncClient, auth_headers, session, test_user, test_workspace
):
    ref = await _matching(session, test_user, test_workspace)

    resp = await client.get("/api/credit-card-bills/payment-matches/preview", headers=auth_headers)

    # BMATCH AC 10
    assert resp.status_code == 200, resp.text
    rows = resp.json()
    assert [(r["transaction_id"], r["bill_id"], r["kind"]) for r in rows] == [
        (str(ref["payment"].id), str(ref["bill"].id), "exact")
    ]
    assert rows[0]["payment_amount"] == 1283.20
    assert rows[0]["payment_account_name"] == "Nubank"
    assert rows[0]["bill_account_name"] == "Cartão de Crédito Nubank"
    assert rows[0]["remaining_amount"] == 1283.20
    await session.refresh(ref["payment"])
    assert ref["payment"].paid_bill_id is None


async def test_match_apply_links_checked_pairs_and_reports_failures(
    client: AsyncClient, auth_headers, session, test_user, test_workspace
):
    ref = await _matching(session, test_user, test_workspace)
    missing = uuid.uuid4()

    resp = await client.post(
        "/api/credit-card-bills/payment-matches/apply", headers=auth_headers,
        json={"pairs": [
            {"transaction_id": str(ref["payment"].id), "bill_id": str(ref["bill"].id)},
            {"transaction_id": str(ref["expense"].id), "bill_id": str(missing)},
        ]},
    )

    # BMATCH AC 11
    assert resp.status_code == 200, resp.text
    assert resp.json() == {
        "linked": 1,
        "failed": [
            {"transaction_id": str(ref["expense"].id), "bill_id": str(missing),
             "reason": "Bill not found"},
        ],
    }
    await session.refresh(ref["payment"])
    await session.refresh(ref["expense"])
    assert ref["payment"].paid_bill_id == ref["bill"].id
    assert ref["expense"].paid_bill_id is None


async def _list_flags(client, headers, account) -> dict[str, bool]:
    resp = await client.get(
        "/api/transactions", headers=headers, params={"account_id": str(account.id)}
    )
    assert resp.status_code == 200, resp.text
    return {row["id"]: row["bill_payment_suggestion"] for row in resp.json()["items"]}


async def test_transactions_list_flags_pending_suggestions_until_dismissed(
    client: AsyncClient, auth_headers, session, test_user, test_workspace
):
    ref = await _matching(session, test_user, test_workspace)

    # BMATCH AC 14 (API side): the indicator for the payment only.
    assert await _list_flags(client, auth_headers, ref["checking"]) == {
        str(ref["payment"].id): True,
        str(ref["expense"].id): False,
    }

    dismissed = await client.post(
        "/api/credit-card-bills/payment-suggestions/dismiss", headers=auth_headers,
        json={"transaction_id": str(ref["payment"].id), "bill_id": str(ref["bill"].id)},
    )

    # BMATCH AC 9: the dismissed pair is suggested no more.
    assert dismissed.status_code == 204
    assert (await _list_flags(client, auth_headers, ref["checking"]))[str(ref["payment"].id)] is False
    preview = await client.get("/api/credit-card-bills/payment-matches/preview", headers=auth_headers)
    assert preview.json() == []


async def test_dismissing_an_unknown_bill_is_404(
    client: AsyncClient, auth_headers, session, test_user, test_workspace
):
    ref = await _matching(session, test_user, test_workspace)
    resp = await client.post(
        "/api/credit-card-bills/payment-suggestions/dismiss", headers=auth_headers,
        json={"transaction_id": str(ref["payment"].id), "bill_id": str(uuid.uuid4())},
    )
    assert resp.status_code == 404


async def test_suggestion_flags_cost_the_same_queries_for_any_page_size(
    session, test_user, test_workspace
):
    from sqlalchemy import event

    from app.services.bill_match_service import has_suggestion

    ref = await _matching(session, test_user, test_workspace)
    extra = [_tx(ref["checking"], date(2026, 9, 14), "10.00") for _ in range(5)]
    session.add_all(extra)
    await session.commit()

    statements: list[str] = []

    def count(conn, cursor, statement, *args):
        statements.append(statement)

    engine = session.bind.sync_engine
    event.listen(engine, "before_cursor_execute", count)
    try:
        await has_suggestion(session, test_workspace.id, [ref["payment"].id])
        one = len(statements)
        statements.clear()
        await has_suggestion(session, test_workspace.id, [ref["payment"].id] + [t.id for t in extra])
        many = len(statements)
    finally:
        event.remove(engine, "before_cursor_execute", count)

    # T28: one batched lookup per page, no N+1.
    assert one == many


async def test_a_viewer_can_read_matches_but_not_apply_or_dismiss(
    client: AsyncClient, viewer_auth_headers, session, test_user, test_workspace
):
    ref = await _matching(session, test_user, test_workspace)
    pair = {"transaction_id": str(ref["payment"].id), "bill_id": str(ref["bill"].id)}

    candidates = await client.get(
        "/api/credit-card-bills/payment-candidates", headers=viewer_auth_headers,
        params={"transaction_id": str(ref["payment"].id)},
    )
    preview = await client.get(
        "/api/credit-card-bills/payment-matches/preview", headers=viewer_auth_headers
    )
    apply = await client.post(
        "/api/credit-card-bills/payment-matches/apply", headers=viewer_auth_headers,
        json={"pairs": [pair]},
    )
    dismiss = await client.post(
        "/api/credit-card-bills/payment-suggestions/dismiss", headers=viewer_auth_headers,
        json=pair,
    )
    assert (candidates.status_code, preview.status_code) == (200, 200)
    assert (apply.status_code, dismiss.status_code) == (403, 403)
