import uuid

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import current_active_user
from app.core.database import get_async_session
from app.models.user import User
from app.schemas.import_mapping import (
    ImportMappingCreate,
    ImportMappingMatchRequest,
    ImportMappingMatchResponse,
    ImportMappingRead,
    ImportMappingUpdate,
)
from app.services import import_mapping_service as service

router = APIRouter(prefix="/api/import-mappings", tags=["import-mappings"])

_NOT_FOUND = HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Import mapping not found")


def _conflict() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail="A mapping with this name already exists",
    )


@router.get("", response_model=list[ImportMappingRead])
async def list_import_mappings(
    user: User = Depends(current_active_user),
    session: AsyncSession = Depends(get_async_session),
):
    return await service.list_mappings(session, user.id)


@router.post("", response_model=ImportMappingRead, status_code=status.HTTP_201_CREATED)
async def create_import_mapping(
    data: ImportMappingCreate,
    user: User = Depends(current_active_user),
    session: AsyncSession = Depends(get_async_session),
):
    try:
        return await service.create_mapping(session, user.id, data)
    except service.DuplicateImportMappingError:
        raise _conflict()


# Static path first so "match" is never read as a mapping id.
@router.post("/match", response_model=ImportMappingMatchResponse)
async def match_import_mappings(
    data: ImportMappingMatchRequest,
    user: User = Depends(current_active_user),
    session: AsyncSession = Depends(get_async_session),
):
    return ImportMappingMatchResponse(
        matches=[
            ImportMappingRead.model_validate(m)
            for m in await service.match_mappings(session, user.id, data.headers)
        ]
    )


@router.patch("/{mapping_id}", response_model=ImportMappingRead)
async def update_import_mapping(
    mapping_id: uuid.UUID,
    data: ImportMappingUpdate,
    user: User = Depends(current_active_user),
    session: AsyncSession = Depends(get_async_session),
):
    try:
        return await service.update_mapping(session, user.id, mapping_id, data)
    except service.ImportMappingNotFoundError:
        raise _NOT_FOUND
    except service.DuplicateImportMappingError:
        raise _conflict()


@router.delete("/{mapping_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_import_mapping(
    mapping_id: uuid.UUID,
    user: User = Depends(current_active_user),
    session: AsyncSession = Depends(get_async_session),
):
    try:
        await service.delete_mapping(session, user.id, mapping_id)
    except service.ImportMappingNotFoundError:
        raise _NOT_FOUND
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/{mapping_id}/touch", response_model=ImportMappingRead)
async def touch_import_mapping(
    mapping_id: uuid.UUID,
    user: User = Depends(current_active_user),
    session: AsyncSession = Depends(get_async_session),
):
    try:
        return await service.touch_mapping(session, user.id, mapping_id)
    except service.ImportMappingNotFoundError:
        raise _NOT_FOUND
