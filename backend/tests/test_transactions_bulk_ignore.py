"""Bulk ignore: explicit state, workspace scoping, changed-row count and the
no-cascade rule for transfer legs (spec IGN-01)."""
import uuid
from datetime import date
from decimal import Decimal
from typing import NamedTuple

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.transaction import Transaction
from app.models.workspace import Workspace, WorkspaceMember
from app.services import transaction_service

pytestmark = pytest.mark.asyncio


class Ids(NamedTuple):
    """Plain ids, captured up front: ORM instances expire on every commit."""

    user: uuid.UUID
    account: uuid.UUID
    workspace: uuid.UUID
    other_workspace: uuid.UUID


@pytest_asyncio.fixture
async def ids(session: AsyncSession, test_user, test_account, test_workspace) -> Ids:
    user_id, account_id, workspace_id = test_user.id, test_account.id, test_workspace.id
    other = Workspace(
        id=uuid.uuid4(), name="Other", kind="personal",
        created_by_user_id=user_id, default_currency="BRL",
    )
    session.add(other)
    await session.flush()
    session.add(
        WorkspaceMember(id=uuid.uuid4(), workspace_id=other.id, user_id=user_id, role="owner")
    )
    other_id = other.id
    await session.commit()
    return Ids(user_id, account_id, workspace_id, other_id)


async def _tx(
    session: AsyncSession,
    ids: Ids,
    *,
    workspace: uuid.UUID | None = None,
    ignored: bool = False,
    transfer_pair_id: uuid.UUID | None = None,
) -> uuid.UUID:
    tx_id = uuid.uuid4()
    session.add(
        Transaction(
            id=tx_id,
            user_id=ids.user,
            workspace_id=workspace or ids.workspace,
            account_id=ids.account,
            description="X",
            amount=Decimal("10.00"),
            date=date(2026, 4, 1),
            type="debit",
            source="manual",
            is_ignored=ignored,
            transfer_pair_id=transfer_pair_id,
        )
    )
    await session.commit()
    return tx_id


async def _flag(session: AsyncSession, tx_id: uuid.UUID) -> bool:
    session.expire_all()
    return (
        await session.execute(select(Transaction.is_ignored).where(Transaction.id == tx_id))
    ).scalar_one()


async def test_ignore_sets_the_flag_and_counts_only_changed_rows(session, ids):
    fresh = await _tx(session, ids)
    already = await _tx(session, ids, ignored=True)

    updated = await transaction_service.bulk_set_ignored(
        session, ids.workspace, [fresh, already], True
    )

    assert updated == 1
    assert await _flag(session, fresh) is True
    assert await _flag(session, already) is True


async def test_unignore_sets_the_flag_to_false(session, ids):
    a = await _tx(session, ids, ignored=True)
    b = await _tx(session, ids, ignored=True)
    c = await _tx(session, ids, ignored=False)

    updated = await transaction_service.bulk_set_ignored(
        session, ids.workspace, [a, b, c], False
    )

    assert updated == 2
    assert [await _flag(session, t) for t in (a, b, c)] == [False, False, False]


async def test_mixed_selection_ends_in_the_requested_state_not_toggled(session, ids):
    on = await _tx(session, ids, ignored=True)
    off = await _tx(session, ids, ignored=False)

    await transaction_service.bulk_set_ignored(session, ids.workspace, [on, off], True)

    assert await _flag(session, on) is True
    assert await _flag(session, off) is True


async def test_other_workspace_rows_are_untouched_and_uncounted(session, ids):
    mine = await _tx(session, ids)
    foreign = await _tx(session, ids, workspace=ids.other_workspace)

    updated = await transaction_service.bulk_set_ignored(
        session, ids.workspace, [mine, foreign], True
    )

    assert updated == 1
    assert await _flag(session, mine) is True
    assert await _flag(session, foreign) is False


async def test_empty_list_returns_zero(session, ids):
    assert await transaction_service.bulk_set_ignored(session, ids.workspace, [], True) == 0


async def test_transfer_pair_leg_is_not_cascaded(session, ids):
    pair_id = uuid.uuid4()
    leg_a = await _tx(session, ids, transfer_pair_id=pair_id)
    leg_b = await _tx(session, ids, transfer_pair_id=pair_id)

    updated = await transaction_service.bulk_set_ignored(session, ids.workspace, [leg_a], True)

    assert updated == 1
    assert await _flag(session, leg_a) is True
    assert await _flag(session, leg_b) is False


# ---------------------------------------------------------------------------
# PATCH /api/transactions/bulk-ignore
# ---------------------------------------------------------------------------

URL = "/api/transactions/bulk-ignore"


async def test_route_returns_the_changed_count(client, auth_headers, session, ids):
    a = await _tx(session, ids)
    b = await _tx(session, ids, ignored=True)

    resp = await client.patch(
        URL, headers=auth_headers, json={"transaction_ids": [str(a), str(b)], "ignored": True}
    )

    assert resp.status_code == 200, resp.text
    assert resp.json() == {"updated": 1}
    assert await _flag(session, a) is True


async def test_route_rejects_more_than_100_ids_and_changes_nothing(
    client, auth_headers, session, ids
):
    tx = await _tx(session, ids)
    payload = [str(tx)] + [str(uuid.uuid4()) for _ in range(100)]

    resp = await client.patch(
        URL, headers=auth_headers, json={"transaction_ids": payload, "ignored": True}
    )

    assert resp.status_code == 422
    assert await _flag(session, tx) is False


async def test_route_accepts_exactly_100_ids(client, auth_headers, ids):
    payload = [str(uuid.uuid4()) for _ in range(100)]

    resp = await client.patch(
        URL, headers=auth_headers, json={"transaction_ids": payload, "ignored": True}
    )

    assert resp.status_code == 200, resp.text
    assert resp.json() == {"updated": 0}


async def test_route_ignores_exactly_100_real_rows(client, auth_headers, session, ids):
    """Success criterion: a bulk operation acts on 100 transactions in one request."""
    tx_ids = [uuid.uuid4() for _ in range(100)]
    session.add_all(
        Transaction(
            id=tx_id, user_id=ids.user, workspace_id=ids.workspace, account_id=ids.account,
            description="X", amount=Decimal("10.00"), date=date(2026, 4, 1),
            type="debit", source="manual",
        )
        for tx_id in tx_ids
    )
    await session.commit()

    resp = await client.patch(
        URL,
        headers=auth_headers,
        json={"transaction_ids": [str(i) for i in tx_ids], "ignored": True},
    )

    assert resp.status_code == 200, resp.text
    assert resp.json() == {"updated": 100}
    session.expire_all()
    flags = (
        await session.execute(select(Transaction.is_ignored).where(Transaction.id.in_(tx_ids)))
    ).scalars().all()
    assert len(flags) == 100
    assert all(flags)


async def test_route_ignores_ids_from_another_workspace(client, auth_headers, session, ids):
    foreign = await _tx(session, ids, workspace=ids.other_workspace)

    resp = await client.patch(
        URL, headers=auth_headers, json={"transaction_ids": [str(foreign)], "ignored": True}
    )

    assert resp.status_code == 200, resp.text
    assert resp.json() == {"updated": 0}
    assert await _flag(session, foreign) is False


async def test_route_rejects_a_read_only_member(client, viewer_auth_headers, session, ids):
    tx = await _tx(session, ids)

    resp = await client.patch(
        URL, headers=viewer_auth_headers, json={"transaction_ids": [str(tx)], "ignored": True}
    )

    assert resp.status_code == 403, resp.text
    assert await _flag(session, tx) is False
