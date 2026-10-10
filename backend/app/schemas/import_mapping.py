import datetime
import uuid
from typing import Annotated, Optional

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

MappingName = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]


class ImportMappingOptions(BaseModel):
    """The `parse_csv` knobs saved next to the column map."""

    date_format: Optional[str] = None
    flip_amount: bool = False
    inflow_column: Optional[str] = None
    outflow_column: Optional[str] = None


class ImportMappingCreate(BaseModel):
    name: MappingName
    account_id: Optional[uuid.UUID] = None
    headers: list[str] = Field(min_length=1)
    column_mapping: dict[str, str] = Field(default_factory=dict)
    options: ImportMappingOptions = Field(default_factory=ImportMappingOptions)


class ImportMappingUpdate(BaseModel):
    name: Optional[MappingName] = None
    account_id: Optional[uuid.UUID] = None
    headers: Optional[list[str]] = Field(default=None, min_length=1)
    column_mapping: Optional[dict[str, str]] = None
    options: Optional[ImportMappingOptions] = None


class ImportMappingRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    account_id: Optional[uuid.UUID] = None
    headers: list[str]
    column_mapping: dict[str, str]
    options: ImportMappingOptions
    last_used_at: Optional[datetime.datetime] = None
    created_at: datetime.datetime
    updated_at: datetime.datetime


class ImportMappingMatchRequest(BaseModel):
    headers: list[str]


class ImportMappingMatchResponse(BaseModel):
    matches: list[ImportMappingRead]
