import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import DateTime, ForeignKey, Index, JSON, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class ImportMapping(Base):
    """A saved CSV column mapping, owned by one user (not by a workspace)."""

    __tablename__ = "import_mappings"
    __table_args__ = (
        UniqueConstraint("user_id", "name_key", name="uq_import_mappings_user_name_key"),
        Index("ix_import_mappings_user_headers_key", "user_id", "headers_key"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(100))
    #: `name.strip().lower()`, so names are unique per user ignoring case.
    name_key: Mapped[str] = mapped_column(String(100))
    account_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("accounts.id", ondelete="SET NULL"), nullable=True
    )
    #: Trimmed CSV headers, sorted, so the layout is order-insensitive.
    headers: Mapped[list] = mapped_column(JSON, default=list)
    #: sha256 of the sorted trimmed headers; the lookup key for `match`.
    headers_key: Mapped[str] = mapped_column(String(64))
    #: Securo field -> CSV column, exactly what `parse_csv` takes.
    column_mapping: Mapped[dict] = mapped_column(JSON, default=dict)
    #: date_format, flip_amount, inflow_column, outflow_column.
    options: Mapped[dict] = mapped_column(JSON, default=dict)
    last_used_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow
    )
