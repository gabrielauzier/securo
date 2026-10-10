"""Bulk "mark as transfer": pair a selection, report what could not be paired,
and link only confirmed pairs that are still valid (spec BTR-01)."""
import uuid
from datetime import date
from decimal import Decimal

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.account import Account
from app.models.transaction import Transaction
from app.models.workspace import Workspace, WorkspaceMember

pytestmark = pytest.mark.asyncio

TODAY = date.today()


@pytest_asyncio.fixture
async def acc(session: AsyncSession, test_user, test_workspace) -> dict[str, uuid.UUID]:
    out: dict[str, uuid.UUID] = {}
    for name in ("A", "B", "C"):
        account = Account(
            id=uuid.uuid4(), user_id=test_user.id, workspace_id=test_workspace.id,
            name=f"Acc {name}", type="checking", balance=Decimal("0"), currency="BRL",
        )
        session.add(account)
        out[name] = account.id
    await session.commit()
    return out


async def _tx(
    session: AsyncSession, test_user, workspace_id, account_id, kind: str, amount: str,
    *, pair: uuid.UUID | None = None, when: date = TODAY,
) -> str:
    tx_id = uuid.uuid4()
    session.add(
        Transaction(
            id=tx_id, user_id=test_user.id, workspace_id=workspace_id,
            account_id=account_id, description=f"{kind} {amount}",
            amount=Decimal(amount), currency="BRL", date=when, type=kind,
            source="manual", transfer_pair_id=pair,
        )
    )
    await session.commit()
    return str(tx_id)


async def _pair_id(session: AsyncSession, tx_id: str):
    session.expire_all()
    return (
        await session.execute(
            select(Transaction.transfer_pair_id).where(Transaction.id == uuid.UUID(tx_id))
        )
    ).scalar_one()


PREVIEW = "/api/transactions/bulk-transfer/preview"
CONFIRM = "/api/transactions/bulk-transfer"


async def test_preview_pairs_a_debit_and_a_credit_and_reports_the_stray(
    client: AsyncClient, auth_headers, session, test_user, test_workspace, acc
):
    debit = await _tx(session, test_user, test_workspace.id, acc["A"], "debit", "120.00")
    credit = await _tx(session, test_user, test_workspace.id, acc["B"], "credit", "120.00")
    stray = await _tx(session, test_user, test_workspace.id, acc["A"], "debit", "999.00")

    response = await client.post(
        PREVIEW, json={"transaction_ids": [debit, credit, stray]}, headers=auth_headers
    )

    assert response.status_code == 200
    body = response.json()
    assert [(p["a"]["id"], p["b"]["id"]) for p in body["pairs"]] == [(debit, credit)]
    assert body["pairs"][0]["strategy"]
    assert body["unmatched"] == [stray]
    assert body["ambiguous"] == []
    assert body["already_linked"] == []
    assert await _pair_id(session, debit) is None


async def test_preview_does_not_pair_a_row_with_two_valid_counterparts(
    client: AsyncClient, auth_headers, session, test_user, test_workspace, acc
):
    d1 = await _tx(session, test_user, test_workspace.id, acc["A"], "debit", "90.00")
    d2 = await _tx(session, test_user, test_workspace.id, acc["B"], "debit", "90.00")
    credit = await _tx(session, test_user, test_workspace.id, acc["C"], "credit", "90.00")

    response = await client.post(
        PREVIEW, json={"transaction_ids": [d1, d2, credit]}, headers=auth_headers
    )

    body = response.json()
    assert body["pairs"] == []
    assert set(body["ambiguous"]) == {d1, d2, credit}
    assert await _pair_id(session, credit) is None


async def test_preview_lists_already_linked_rows_and_leaves_them_untouched(
    client: AsyncClient, auth_headers, session, test_user, test_workspace, acc
):
    pair = uuid.uuid4()
    debit = await _tx(session, test_user, test_workspace.id, acc["A"], "debit", "60.00", pair=pair)
    credit = await _tx(session, test_user, test_workspace.id, acc["B"], "credit", "60.00", pair=pair)

    response = await client.post(
        PREVIEW, json={"transaction_ids": [debit, credit]}, headers=auth_headers
    )

    body = response.json()
    assert set(body["already_linked"]) == {debit, credit}
    assert body["pairs"] == []
    assert await _pair_id(session, debit) == pair


async def test_preview_never_reveals_another_workspaces_transactions(
    client: AsyncClient, auth_headers, session, test_user, test_workspace, acc
):
    other = Workspace(
        id=uuid.uuid4(), name="Other", kind="personal",
        created_by_user_id=test_user.id, default_currency="BRL",
    )
    session.add(other)
    await session.flush()
    session.add(WorkspaceMember(id=uuid.uuid4(), workspace_id=other.id, user_id=test_user.id, role="owner"))
    other_id = other.id
    await session.commit()
    foreign_account = Account(
        id=uuid.uuid4(), user_id=test_user.id, workspace_id=other_id,
        name="Foreign", type="checking", balance=Decimal("0"), currency="BRL",
    )
    session.add(foreign_account)
    await session.commit()
    mine = await _tx(session, test_user, test_workspace.id, acc["A"], "debit", "30.00")
    foreign = await _tx(session, test_user, other_id, foreign_account.id, "credit", "30.00")

    response = await client.post(
        PREVIEW, json={"transaction_ids": [mine, foreign]}, headers=auth_headers
    )

    body = response.json()
    assert body["pairs"] == []
    assert body["unmatched"] == [mine]
    assert foreign not in str(body)


async def test_preview_rejects_more_than_100_ids_with_422(
    client: AsyncClient, auth_headers
):
    ids = [str(uuid.uuid4()) for _ in range(101)]

    response = await client.post(PREVIEW, json={"transaction_ids": ids}, headers=auth_headers)

    assert response.status_code == 422


async def test_confirm_rejects_more_than_50_pairs_with_422(client: AsyncClient, auth_headers):
    pairs = [{"a": str(uuid.uuid4()), "b": str(uuid.uuid4())} for _ in range(51)]

    response = await client.post(CONFIRM, json={"pairs": pairs}, headers=auth_headers)

    assert response.status_code == 422


async def test_preview_accepts_exactly_100_ids(client: AsyncClient, auth_headers):
    ids = [str(uuid.uuid4()) for _ in range(100)]

    response = await client.post(PREVIEW, json={"transaction_ids": ids}, headers=auth_headers)

    assert response.status_code == 200
    assert response.json()["pairs"] == []


async def test_confirm_links_the_posted_pairs_and_returns_the_count(
    client: AsyncClient, auth_headers, session, test_user, test_workspace, acc
):
    debit = await _tx(session, test_user, test_workspace.id, acc["A"], "debit", "150.00")
    credit = await _tx(session, test_user, test_workspace.id, acc["B"], "credit", "150.00")

    response = await client.post(
        CONFIRM, json={"pairs": [{"a": debit, "b": credit}]}, headers=auth_headers
    )

    assert response.status_code == 200
    assert response.json() == {"linked": 1, "skipped": []}
    shared = await _pair_id(session, debit)
    assert shared is not None
    assert await _pair_id(session, credit) == shared


async def test_confirm_skips_a_pair_that_went_stale_since_the_preview(
    client: AsyncClient, auth_headers, session, test_user, test_workspace, acc
):
    debit = await _tx(session, test_user, test_workspace.id, acc["A"], "debit", "70.00")
    credit = await _tx(session, test_user, test_workspace.id, acc["B"], "credit", "70.00")
    first = await client.post(
        CONFIRM, json={"pairs": [{"a": debit, "b": credit}]}, headers=auth_headers
    )
    assert first.json()["linked"] == 1

    again = await client.post(
        CONFIRM, json={"pairs": [{"a": debit, "b": credit}]}, headers=auth_headers
    )

    body = again.json()
    assert body["linked"] == 0
    assert [(s["a"], s["b"]) for s in body["skipped"]] == [(debit, credit)]


async def test_read_only_member_cannot_confirm_or_preview(
    client: AsyncClient, auth_headers, viewer_auth_headers, session, test_user, test_workspace, acc
):
    debit = await _tx(session, test_user, test_workspace.id, acc["A"], "debit", "35.00")
    credit = await _tx(session, test_user, test_workspace.id, acc["B"], "credit", "35.00")

    confirm = await client.post(
        CONFIRM, json={"pairs": [{"a": debit, "b": credit}]}, headers=viewer_auth_headers
    )
    preview = await client.post(
        PREVIEW, json={"transaction_ids": [debit, credit]}, headers=viewer_auth_headers
    )

    assert confirm.status_code == 403
    assert preview.status_code == 403
    assert await _pair_id(session, debit) is None
