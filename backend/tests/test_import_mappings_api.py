"""Saved CSV import mappings over HTTP (spec IMP-01 ACs 3, 4, 8 and the
HTTP 409 / 422 edge cases)."""
import uuid

import bcrypt as _bcrypt
import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.account import Account
from app.models.user import User
from app.services.workspace_service import create_personal_workspace_for_user

pytestmark = pytest.mark.asyncio

URL = "/api/import-mappings"
NUBANK_HEADERS = ["Data", "Valor", "Identificador", "Descrição"]
NUBANK_MAPPING = {
    "date": "Data",
    "amount": "Valor",
    "external_id": "Identificador",
    "description": "Descrição",
}


def _body(name="Nubank", **extra) -> dict:
    return {
        "name": name,
        "headers": NUBANK_HEADERS,
        "column_mapping": NUBANK_MAPPING,
        "options": {"date_format": "DD/MM/YYYY", "flip_amount": False},
        **extra,
    }


@pytest_asyncio.fixture
async def other_auth_headers(session: AsyncSession, client: AsyncClient, test_user: User) -> dict:
    user = User(
        id=uuid.uuid4(),
        email="other-mapping-api@example.com",
        hashed_password=_bcrypt.hashpw(b"otherpass123", _bcrypt.gensalt()).decode(),
        is_active=True,
        is_superuser=False,
        is_verified=True,
    )
    session.add(user)
    await session.flush()
    await create_personal_workspace_for_user(session, user)
    await session.commit()
    resp = await client.post(
        "/api/auth/login",
        data={"username": user.email, "password": "otherpass123"},
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    assert resp.status_code == 200
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}


async def test_create_returns_201_and_the_saved_fields(
    client: AsyncClient, auth_headers: dict, test_account: Account
):
    r = await client.post(URL, json=_body(account_id=str(test_account.id)), headers=auth_headers)

    assert r.status_code == 201
    body = r.json()
    assert body["name"] == "Nubank"
    assert body["account_id"] == str(test_account.id)
    assert body["column_mapping"] == NUBANK_MAPPING
    assert sorted(body["headers"]) == sorted(NUBANK_HEADERS)
    assert body["options"]["date_format"] == "DD/MM/YYYY"
    assert body["last_used_at"] is None
    listed = await client.get(URL, headers=auth_headers)
    assert [m["id"] for m in listed.json()] == [body["id"]]


async def test_duplicate_name_in_another_case_is_409(client: AsyncClient, auth_headers: dict):
    await client.post(URL, json=_body("Nubank"), headers=auth_headers)

    r = await client.post(URL, json=_body("NUBANK"), headers=auth_headers)

    assert r.status_code == 409
    assert r.json()["detail"] == "A mapping with this name already exists"


@pytest.mark.parametrize("name", ["", "   ", "x" * 101])
async def test_blank_or_overlong_name_is_422(client: AsyncClient, auth_headers: dict, name: str):
    r = await client.post(URL, json=_body(name), headers=auth_headers)

    assert r.status_code == 422
    assert (await client.get(URL, headers=auth_headers)).json() == []


async def test_match_returns_the_mapping_for_the_same_header_set(
    client: AsyncClient, auth_headers: dict
):
    saved = (await client.post(URL, json=_body(), headers=auth_headers)).json()

    hit = await client.post(
        f"{URL}/match",
        json={"headers": ["Descrição", "Valor", "Data", "Identificador"]},
        headers=auth_headers,
    )
    miss = await client.post(f"{URL}/match", json={"headers": ["Foo", "Bar"]}, headers=auth_headers)

    assert hit.status_code == 200
    assert [m["id"] for m in hit.json()["matches"]] == [saved["id"]]
    assert miss.status_code == 200
    assert miss.json() == {"matches": []}


async def test_patch_headers_rematches_by_the_new_headers(
    client: AsyncClient, auth_headers: dict
):
    saved = (await client.post(URL, json=_body(), headers=auth_headers)).json()

    patched = await client.patch(
        f"{URL}/{saved['id']}", json={"headers": ["Foo", "Bar"]}, headers=auth_headers
    )
    old = await client.post(f"{URL}/match", json={"headers": NUBANK_HEADERS}, headers=auth_headers)
    new = await client.post(f"{URL}/match", json={"headers": ["Bar", "Foo"]}, headers=auth_headers)

    assert patched.status_code == 200
    assert sorted(patched.json()["headers"]) == ["Bar", "Foo"]
    assert old.json() == {"matches": []}
    assert [m["id"] for m in new.json()["matches"]] == [saved["id"]]


async def test_patch_renames_and_a_taken_name_is_409(client: AsyncClient, auth_headers: dict):
    first = (await client.post(URL, json=_body("First"), headers=auth_headers)).json()
    await client.post(
        URL, json={**_body("Second"), "headers": ["a", "b"]}, headers=auth_headers
    )

    renamed = await client.patch(f"{URL}/{first['id']}", json={"name": "Renamed"}, headers=auth_headers)
    taken = await client.patch(f"{URL}/{first['id']}", json={"name": "second"}, headers=auth_headers)

    assert renamed.status_code == 200
    assert renamed.json()["name"] == "Renamed"
    assert taken.status_code == 409


async def test_delete_returns_204_and_removes_the_mapping(client: AsyncClient, auth_headers: dict):
    saved = (await client.post(URL, json=_body(), headers=auth_headers)).json()

    r = await client.delete(f"{URL}/{saved['id']}", headers=auth_headers)

    assert r.status_code == 204
    assert (await client.get(URL, headers=auth_headers)).json() == []


async def test_touch_sets_last_used_at(client: AsyncClient, auth_headers: dict):
    saved = (await client.post(URL, json=_body(), headers=auth_headers)).json()

    r = await client.post(f"{URL}/{saved['id']}/touch", headers=auth_headers)

    assert r.status_code == 200
    assert r.json()["last_used_at"] is not None


async def test_another_users_mapping_is_404_and_invisible(
    client: AsyncClient, auth_headers: dict, other_auth_headers: dict
):
    saved = (await client.post(URL, json=_body(), headers=auth_headers)).json()

    patch = await client.patch(f"{URL}/{saved['id']}", json={"name": "X"}, headers=other_auth_headers)
    delete = await client.delete(f"{URL}/{saved['id']}", headers=other_auth_headers)
    touch = await client.post(f"{URL}/{saved['id']}/touch", headers=other_auth_headers)
    listed = await client.get(URL, headers=other_auth_headers)
    match = await client.post(
        f"{URL}/match", json={"headers": NUBANK_HEADERS}, headers=other_auth_headers
    )

    assert (patch.status_code, delete.status_code, touch.status_code) == (404, 404, 404)
    assert listed.json() == []
    assert match.json() == {"matches": []}
    assert len((await client.get(URL, headers=auth_headers)).json()) == 1


async def test_unauthenticated_requests_are_401(client: AsyncClient):
    some_id = uuid.uuid4()

    responses = [
        await client.get(URL),
        await client.post(URL, json=_body()),
        await client.post(f"{URL}/match", json={"headers": ["a"]}),
        await client.patch(f"{URL}/{some_id}", json={"name": "x"}),
        await client.delete(f"{URL}/{some_id}"),
        await client.post(f"{URL}/{some_id}/touch"),
    ]

    assert [r.status_code for r in responses] == [401] * 6
