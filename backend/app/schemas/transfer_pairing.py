"""Shapes shared by the two ways of pairing transfers on demand: running
the workspace rule (`/connections/transfers/*`) and pairing a selection
(`/transactions/bulk-transfer*`)."""
import uuid
from datetime import date
from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, Field


class TransferLegRead(BaseModel):
    id: uuid.UUID
    date: date
    account_id: uuid.UUID
    account_name: Optional[str] = None
    description: str
    amount: Decimal
    type: str


class ProposedPairRead(BaseModel):
    """`a` is the debit leg and `b` the credit leg."""

    a: TransferLegRead
    b: TransferLegRead
    strategy: Optional[str] = None


class TransferPreviewRead(BaseModel):
    pairs: list[ProposedPairRead]
    ambiguous: list[uuid.UUID] = []
    unmatched: list[uuid.UUID] = []
    already_linked: list[uuid.UUID] = []


class TransferPairRef(BaseModel):
    a: uuid.UUID
    b: uuid.UUID


class TransferApplyRequest(BaseModel):
    pairs: list[TransferPairRef] = Field(max_length=500)


class SkippedPairRead(BaseModel):
    a: uuid.UUID
    b: uuid.UUID
    reason: str


class TransferApplyRead(BaseModel):
    linked: int
    skipped: list[SkippedPairRead]
