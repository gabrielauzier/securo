import uuid
from datetime import date as _date, datetime, timezone
from decimal import Decimal
from typing import Optional

from sqlalchemy import (
    Date,
    DateTime,
    ForeignKey,
    Index,
    JSON,
    Numeric,
    String,
    UniqueConstraint,
    event,
    select,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class CreditCardBill(Base):
    """A credit-card bill (fatura) — issue #92.

    Models the universal credit-card billing shape: a statement closes on a
    cycle, has a due date and a total to be paid, and is the canonical "which
    transactions belong in which statement" anchor. Surfaced from whichever
    integration the account uses (Pluggy /bills today, others tomorrow); when
    no integration provides bills, the read path falls back to locally-computed
    cycle math (see app.services.credit_card_service).

    Provider-specific extras live in `raw_data` so we can pull more out later
    without forcing a schema-shaped opinion now.

    Every configured card has one bill per reference month: `provider` bills
    come from the integration, `auto` bills from cycle math, `manual` bills
    from the user. `due_date` is the NOMINAL due date; `effective_due_date`
    rolls it to the next business day. `computed_total`, `paid_amount` and
    `settled_on` are stored aggregates written only by
    `bill_service.refresh_bills` (AD-003); status is derived at read time.
    """

    __tablename__ = "credit_card_bills"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("workspaces.id", ondelete="CASCADE"), index=True
    )
    account_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("accounts.id", ondelete="CASCADE"), nullable=False
    )
    # Provider bill id; auto and manual bills have none.
    external_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    source: Mapped[str] = mapped_column(String(10), default="provider", server_default="provider")
    # Day 1 of the nominal due date's month.
    reference_month: Mapped[_date] = mapped_column(Date, nullable=False)
    period_start: Mapped[_date] = mapped_column(Date, nullable=False)
    period_end: Mapped[_date] = mapped_column(Date, nullable=False)
    close_date: Mapped[_date] = mapped_column(Date, nullable=False)
    due_date: Mapped[_date] = mapped_column(Date, nullable=False, index=True)
    effective_due_date: Mapped[_date] = mapped_column(Date, nullable=False)
    # Official total typed by the user (provider total for provider bills).
    declared_total: Mapped[Optional[Decimal]] = mapped_column(Numeric(precision=15, scale=2), nullable=True)
    computed_total: Mapped[Decimal] = mapped_column(
        Numeric(precision=15, scale=2), default=Decimal("0"), server_default="0"
    )
    paid_amount: Mapped[Decimal] = mapped_column(
        Numeric(precision=15, scale=2), default=Decimal("0"), server_default="0"
    )
    # Date the linked payments first reached the target; NULL until then.
    settled_on: Mapped[Optional[_date]] = mapped_column(Date, nullable=True)
    total_amount: Mapped[Decimal] = mapped_column(Numeric(precision=15, scale=2), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), default="BRL")
    minimum_payment: Mapped[Optional[Decimal]] = mapped_column(Numeric(precision=15, scale=2), nullable=True)
    raw_data: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    __table_args__ = (
        UniqueConstraint("account_id", "external_id", name="uq_cc_bills_account_external_id"),
        Index(
            "ux_cc_bills_account_reference_month",
            "account_id",
            "reference_month",
            unique=True,
            postgresql_where=text("source <> 'provider'"),
            sqlite_where=text("source <> 'provider'"),
        ),
    )


@event.listens_for(CreditCardBill, "before_insert")
def _default_provider_bill_period(mapper, connection, target):
    """Fill the period of a bill created with only a due date.

    Provider sync creates bills from the bank's due date; the period comes
    from the card's close day, and the target from the bank's total."""
    if target.source is None:
        target.source = "provider"
    if target.source == "provider" and target.declared_total is None:
        target.declared_total = target.total_amount
    if target.reference_month is not None and target.close_date is not None:
        return
    from app.models.account import Account
    from app.services.credit_card_service import bill_period_for_due_date

    close_day = connection.execute(
        select(Account.statement_close_day).where(Account.id == target.account_id)
    ).scalar()
    period = bill_period_for_due_date(target.due_date, close_day)
    target.reference_month = period.reference_month
    target.period_start = period.period_start
    target.period_end = period.period_end
    target.close_date = period.close_date
    if target.effective_due_date is None:
        target.effective_due_date = period.effective_due_date
