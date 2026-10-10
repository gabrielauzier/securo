# backend/app/services/import_mapping_service.py
import hashlib
import json
import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.import_mapping import ImportMapping
from app.schemas.import_mapping import ImportMappingCreate, ImportMappingUpdate


class DuplicateImportMappingError(Exception):
    """Raised when the user already has a mapping with this name (any case)."""


class ImportMappingNotFoundError(Exception):
    """Raised when the mapping does not exist or belongs to another user."""


def normalize_headers(headers: list[str]) -> list[str]:
    """Trim and sort, so the same layout hashes the same in any column order."""
    return sorted(h.strip() for h in headers)


def headers_key(headers: list[str]) -> str:
    # JSON keeps the boundaries between headers unambiguous (a header may
    # contain any separator character).
    payload = json.dumps(normalize_headers(headers), ensure_ascii=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _name_key(name: str) -> str:
    return name.strip().lower()


async def _get_owned(session: AsyncSession, user_id: uuid.UUID, mapping_id: uuid.UUID) -> ImportMapping:
    mapping = await session.scalar(
        select(ImportMapping).where(
            ImportMapping.id == mapping_id, ImportMapping.user_id == user_id
        )
    )
    if mapping is None:
        raise ImportMappingNotFoundError(str(mapping_id))
    return mapping


async def _ensure_name_free(
    session: AsyncSession, user_id: uuid.UUID, name: str, exclude_id: uuid.UUID | None = None
) -> None:
    query = select(ImportMapping.id).where(
        ImportMapping.user_id == user_id, ImportMapping.name_key == _name_key(name)
    )
    if exclude_id is not None:
        query = query.where(ImportMapping.id != exclude_id)
    if await session.scalar(query) is not None:
        raise DuplicateImportMappingError(f"A mapping named '{name}' already exists")


async def list_mappings(session: AsyncSession, user_id: uuid.UUID) -> list[ImportMapping]:
    result = await session.execute(
        select(ImportMapping)
        .where(ImportMapping.user_id == user_id)
        .order_by(ImportMapping.name_key)
    )
    return list(result.scalars().all())


async def create_mapping(
    session: AsyncSession, user_id: uuid.UUID, data: ImportMappingCreate
) -> ImportMapping:
    await _ensure_name_free(session, user_id, data.name)
    mapping = ImportMapping(
        user_id=user_id,
        name=data.name,
        name_key=_name_key(data.name),
        account_id=data.account_id,
        headers=normalize_headers(data.headers),
        headers_key=headers_key(data.headers),
        column_mapping=data.column_mapping,
        options=data.options.model_dump(),
    )
    session.add(mapping)
    await session.commit()
    await session.refresh(mapping)
    return mapping


async def update_mapping(
    session: AsyncSession, user_id: uuid.UUID, mapping_id: uuid.UUID, data: ImportMappingUpdate
) -> ImportMapping:
    mapping = await _get_owned(session, user_id, mapping_id)
    changes = data.model_dump(exclude_unset=True)
    if changes.get("name") is not None:
        await _ensure_name_free(session, user_id, changes["name"], exclude_id=mapping.id)
        mapping.name = changes["name"]
        mapping.name_key = _name_key(changes["name"])
    if "account_id" in changes:
        mapping.account_id = changes["account_id"]
    if changes.get("headers") is not None:
        mapping.headers = normalize_headers(changes["headers"])
        mapping.headers_key = headers_key(changes["headers"])
    if changes.get("column_mapping") is not None:
        mapping.column_mapping = changes["column_mapping"]
    if changes.get("options") is not None:
        mapping.options = changes["options"]
    await session.commit()
    await session.refresh(mapping)
    return mapping


async def delete_mapping(session: AsyncSession, user_id: uuid.UUID, mapping_id: uuid.UUID) -> None:
    mapping = await _get_owned(session, user_id, mapping_id)
    await session.delete(mapping)
    await session.commit()


async def match_mappings(
    session: AsyncSession, user_id: uuid.UUID, headers: list[str]
) -> list[ImportMapping]:
    """Mappings whose header set equals `headers`, most recently used first."""
    if not headers:
        return []
    result = await session.execute(
        select(ImportMapping)
        .where(
            ImportMapping.user_id == user_id,
            ImportMapping.headers_key == headers_key(headers),
        )
        .order_by(
            ImportMapping.last_used_at.desc().nulls_last(),
            ImportMapping.created_at.desc(),
        )
    )
    return list(result.scalars().all())


async def touch_mapping(
    session: AsyncSession, user_id: uuid.UUID, mapping_id: uuid.UUID
) -> ImportMapping:
    mapping = await _get_owned(session, user_id, mapping_id)
    mapping.last_used_at = datetime.now(timezone.utc)
    await session.commit()
    await session.refresh(mapping)
    return mapping
