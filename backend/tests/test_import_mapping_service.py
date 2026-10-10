"""Saved CSV import mappings: naming, header-set matching, recency order and
per-user scoping (spec IMP-01 ACs 2-10)."""
import uuid
from datetime import datetime, timedelta, timezone

import bcrypt as _bcrypt
import pytest
import pytest_asyncio
from pydantic import ValidationError
from sqlalchemy import delete, text, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.account import Account
from app.models.import_mapping import ImportMapping
from app.models.user import User
from app.models.workspace import Workspace
from app.schemas.import_mapping import (
    ImportMappingCreate,
    ImportMappingOptions,
    ImportMappingUpdate,
)
from app.services import import_mapping_service as svc

pytestmark = pytest.mark.asyncio

NUBANK_HEADERS = ["Data", "Valor", "Identificador", "Descrição"]
NUBANK_MAPPING = {
    "date": "Data",
    "amount": "Valor",
    "external_id": "Identificador",
    "description": "Descrição",
}


def _create(name="Nubank", headers=None, **kwargs) -> ImportMappingCreate:
    return ImportMappingCreate(
        name=name,
        headers=headers if headers is not None else NUBANK_HEADERS,
        column_mapping=kwargs.pop("column_mapping", NUBANK_MAPPING),
        **kwargs,
    )


@pytest_asyncio.fixture
async def other_user(session: AsyncSession, test_user: User) -> User:
    user = User(
        id=uuid.uuid4(),
        email="other-mapping@example.com",
        hashed_password=_bcrypt.hashpw(b"otherpass123", _bcrypt.gensalt()).decode(),
        is_active=True,
        is_superuser=False,
        is_verified=True,
    )
    session.add(user)
    await session.commit()
    return user


async def test_nubank_mapping_round_trips_with_all_saved_fields(
    session: AsyncSession, test_user: User, test_account: Account
):
    options = ImportMappingOptions(
        date_format="DD/MM/YYYY", flip_amount=True, inflow_column="In", outflow_column="Out"
    )
    created = await svc.create_mapping(
        session, test_user.id, _create(account_id=test_account.id, options=options)
    )

    listed = await svc.list_mappings(session, test_user.id)

    assert [m.id for m in listed] == [created.id]
    saved = listed[0]
    assert saved.name == "Nubank"
    assert saved.account_id == test_account.id
    assert saved.column_mapping == {
        "date": "Data",
        "amount": "Valor",
        "external_id": "Identificador",
        "description": "Descrição",
    }
    assert sorted(saved.headers) == sorted(NUBANK_HEADERS)
    assert saved.options == {
        "date_format": "DD/MM/YYYY",
        "flip_amount": True,
        "inflow_column": "In",
        "outflow_column": "Out",
    }


async def test_duplicate_name_in_any_case_is_a_conflict(session: AsyncSession, test_user: User):
    await svc.create_mapping(session, test_user.id, _create(name="Nubank"))

    with pytest.raises(svc.DuplicateImportMappingError):
        await svc.create_mapping(session, test_user.id, _create(name="  nUBANK "))

    assert len(await svc.list_mappings(session, test_user.id)) == 1


async def test_same_name_is_allowed_for_another_user(
    session: AsyncSession, test_user: User, other_user: User
):
    await svc.create_mapping(session, test_user.id, _create(name="Nubank"))

    other = await svc.create_mapping(session, other_user.id, _create(name="Nubank"))

    assert other.user_id == other_user.id


@pytest.mark.parametrize("name", ["", "   ", "x" * 101])
async def test_blank_or_overlong_name_is_rejected(name: str):
    with pytest.raises(ValidationError):
        ImportMappingCreate(name=name, headers=NUBANK_HEADERS, column_mapping=NUBANK_MAPPING)


async def test_rename_to_an_existing_name_conflicts_but_own_name_is_fine(
    session: AsyncSession, test_user: User
):
    first = await svc.create_mapping(session, test_user.id, _create(name="Nubank"))
    second = await svc.create_mapping(
        session, test_user.id, _create(name="Inter", headers=["a", "b"], column_mapping={})
    )

    with pytest.raises(svc.DuplicateImportMappingError):
        await svc.update_mapping(
            session, test_user.id, second.id, ImportMappingUpdate(name="NUBANK")
        )
    renamed = await svc.update_mapping(
        session, test_user.id, first.id, ImportMappingUpdate(name="NUBANK")
    )

    assert renamed.name == "NUBANK"


async def test_patching_headers_changes_which_uploads_match(
    session: AsyncSession, test_user: User
):
    saved = await svc.create_mapping(session, test_user.id, _create())

    await svc.update_mapping(
        session, test_user.id, saved.id, ImportMappingUpdate(headers=["Foo", " Bar "])
    )

    assert await svc.match_mappings(session, test_user.id, NUBANK_HEADERS) == []
    found = await svc.match_mappings(session, test_user.id, ["Bar", "Foo"])
    assert [m.id for m in found] == [saved.id]
    assert found[0].headers == ["Bar", "Foo"]


async def test_match_ignores_order_and_padding_but_requires_the_exact_set(
    session: AsyncSession, test_user: User
):
    saved = await svc.create_mapping(session, test_user.id, _create())

    reordered = await svc.match_mappings(
        session, test_user.id, ["Descrição", " Data ", "Identificador", "Valor"]
    )
    subset = await svc.match_mappings(session, test_user.id, ["Data", "Valor", "Identificador"])
    superset = await svc.match_mappings(session, test_user.id, NUBANK_HEADERS + ["Extra"])
    other_case = await svc.match_mappings(
        session, test_user.id, ["data", "valor", "identificador", "descrição"]
    )

    assert [m.id for m in reordered] == [saved.id]
    assert subset == []
    assert superset == []
    assert other_case == []


async def test_no_match_returns_empty_and_no_headers_match_nothing(
    session: AsyncSession, test_user: User
):
    await svc.create_mapping(session, test_user.id, _create())

    assert await svc.match_mappings(session, test_user.id, ["Foo", "Bar"]) == []
    assert await svc.match_mappings(session, test_user.id, []) == []


async def test_several_matches_are_ordered_most_recently_used_first(
    session: AsyncSession, test_user: User
):
    mappings = {}
    for name in ["Old", "Recent", "NeverOlder", "NeverNewer"]:
        mappings[name] = await svc.create_mapping(session, test_user.id, _create(name=name))
    base = datetime(2026, 1, 1, tzinfo=timezone.utc)
    for name, created, used in [
        ("Old", 0, 10),
        ("Recent", 1, 20),
        ("NeverOlder", 2, None),
        ("NeverNewer", 3, None),
    ]:
        await session.execute(
            update(ImportMapping)
            .where(ImportMapping.id == mappings[name].id)
            .values(
                created_at=base + timedelta(days=created),
                last_used_at=None if used is None else base + timedelta(days=used),
            )
        )
    await session.commit()

    matches = await svc.match_mappings(session, test_user.id, NUBANK_HEADERS)

    assert [m.name for m in matches] == ["Recent", "Old", "NeverNewer", "NeverOlder"]


async def test_touch_moves_a_mapping_to_the_front(session: AsyncSession, test_user: User):
    first = await svc.create_mapping(session, test_user.id, _create(name="First"))
    second = await svc.create_mapping(session, test_user.id, _create(name="Second"))
    assert first.last_used_at is None

    touched = await svc.touch_mapping(session, test_user.id, first.id)

    assert touched.last_used_at is not None
    matches = await svc.match_mappings(session, test_user.id, NUBANK_HEADERS)
    assert [m.id for m in matches] == [first.id, second.id]


async def test_another_users_mappings_are_invisible_and_untouchable(
    session: AsyncSession, test_user: User, other_user: User
):
    mine = await svc.create_mapping(session, test_user.id, _create())

    assert await svc.list_mappings(session, other_user.id) == []
    assert await svc.match_mappings(session, other_user.id, NUBANK_HEADERS) == []
    with pytest.raises(svc.ImportMappingNotFoundError):
        await svc.update_mapping(
            session, other_user.id, mine.id, ImportMappingUpdate(name="Stolen")
        )
    with pytest.raises(svc.ImportMappingNotFoundError):
        await svc.touch_mapping(session, other_user.id, mine.id)
    with pytest.raises(svc.ImportMappingNotFoundError):
        await svc.delete_mapping(session, other_user.id, mine.id)

    still_mine = await svc.list_mappings(session, test_user.id)
    assert [(m.id, m.name) for m in still_mine] == [(mine.id, "Nubank")]


async def test_delete_removes_the_mapping(session: AsyncSession, test_user: User):
    mine = await svc.create_mapping(session, test_user.id, _create())

    await svc.delete_mapping(session, test_user.id, mine.id)

    assert await svc.list_mappings(session, test_user.id) == []


async def test_deleted_account_reads_back_as_no_account(
    session: AsyncSession, test_user: User, test_account: Account
):
    mapping = await svc.create_mapping(
        session, test_user.id, _create(account_id=test_account.id)
    )
    mapping_id = mapping.id

    # SQLite skips foreign keys unless asked; enforce them so the ON DELETE
    # SET NULL declared on the column is what clears the reference.
    await session.execute(text("PRAGMA foreign_keys=ON"))
    try:
        await session.execute(delete(Account).where(Account.id == test_account.id))
        await session.commit()
    finally:
        await session.execute(text("PRAGMA foreign_keys=OFF"))
    session.expunge_all()

    listed = await svc.list_mappings(session, test_user.id)
    assert [(m.id, m.account_id) for m in listed] == [(mapping_id, None)]
    matches = await svc.match_mappings(session, test_user.id, NUBANK_HEADERS)
    assert [m.account_id for m in matches] == [None]


async def test_unknown_or_foreign_account_is_rejected_on_create_and_update(
    session: AsyncSession, test_user: User, other_user: User, test_account: Account
):
    saved = await svc.create_mapping(session, test_user.id, _create())

    with pytest.raises(svc.ImportMappingAccountNotFoundError):
        await svc.create_mapping(session, test_user.id, _create(name="X", account_id=uuid.uuid4()))
    with pytest.raises(svc.ImportMappingAccountNotFoundError):
        await svc.create_mapping(session, other_user.id, _create(name="Y", account_id=test_account.id))
    with pytest.raises(svc.ImportMappingAccountNotFoundError):
        await svc.update_mapping(
            session, test_user.id, saved.id, ImportMappingUpdate(account_id=uuid.uuid4())
        )

    ok = await svc.update_mapping(
        session, test_user.id, saved.id, ImportMappingUpdate(account_id=test_account.id)
    )
    assert ok.account_id == test_account.id


async def test_account_of_a_managed_workspace_is_accepted(
    session: AsyncSession, test_user: User, other_user: User
):
    """The destination account may live in a workspace the user manages without being a member."""
    workspace = Workspace(
        id=uuid.uuid4(), name="Managed", kind="personal",
        created_by_user_id=test_user.id, managed_by_user_id=other_user.id,
        default_currency="BRL",
    )
    session.add(workspace)
    await session.flush()
    account = Account(
        id=uuid.uuid4(), user_id=test_user.id, workspace_id=workspace.id,
        name="Managed account", type="checking", balance=0, currency="BRL",
    )
    session.add(account)
    await session.commit()
    account_id = account.id

    saved = await svc.create_mapping(
        session, other_user.id, _create(name="Managed", account_id=account_id)
    )

    assert saved.account_id == account_id
