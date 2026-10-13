"""credit card bills for every card

Bills were stored only when a provider delivered them. Every configured card
now gets one bill per reference month, so the bill table grows the columns
the bill lifecycle needs.

- `credit_card_bills`: `external_id` becomes nullable (auto and manual bills
  have none); new `source`, `reference_month`, `period_start`, `period_end`,
  `close_date`, `effective_due_date`, `declared_total`, `computed_total`,
  `paid_amount`, `settled_on`; partial unique index on
  `(account_id, reference_month)` for non-provider bills.
- Existing bills are provider bills: `source = 'provider'`,
  `declared_total = total_amount`, period from the card's close day around
  the provider due date (close assumed 7 days before due when the card has
  no close day), effective due date rolled to the next business day.
- `transactions.paid_bill_id` and `transactions.bill_payment_pair` mark bill
  payments; `categories.is_bill_payment` flags bill-payment categories;
  `bill_payment_dismissals` records dismissed match suggestions.

The period and holiday math is a frozen copy so later changes to the app
code cannot change what this migration does.

Revision ID: 099
Revises: 098
"""
import calendar
from datetime import date, timedelta

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "099"
down_revision = "098"
branch_labels = None
depends_on = None

_DEFAULT_CLOSE_GAP = 7


def _clamp(year: int, month: int, day: int) -> date:
    return date(year, month, min(day, calendar.monthrange(year, month)[1]))


def _shift(d: date, months: int) -> tuple[int, int]:
    index = d.year * 12 + (d.month - 1) + months
    return index // 12, index % 12 + 1


def _easter(year: int) -> date:
    a = year % 19
    b, c = divmod(year, 100)
    d, e = divmod(b, 4)
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = divmod(c, 4)
    l = (32 + 2 * e + 2 * i - h - k) % 7  # noqa: E741
    m = (a + 11 * h + 22 * l) // 451
    month, day = divmod(h + l - 7 * m + 114, 31)
    return date(year, month, day + 1)


def _holidays(year: int) -> set[date]:
    fixed = [(1, 1), (4, 21), (5, 1), (9, 7), (10, 12), (11, 2), (11, 15), (12, 25)]
    if year >= 2024:
        fixed.append((11, 20))
    easter = _easter(year)
    days = {date(year, m, d) for m, d in fixed}
    days.update(easter + timedelta(days=n) for n in (-48, -47, -2, 60))
    return days


def _next_business_day(d: date) -> date:
    while d.weekday() >= 5 or d in _holidays(d.year):
        d += timedelta(days=1)
    return d


def _provider_period(due: date, close_day):
    if close_day:
        close = _clamp(due.year, due.month, close_day)
        if close >= due:
            close = _clamp(*_shift(due, -1), close_day)
    else:
        close = due - timedelta(days=_DEFAULT_CLOSE_GAP)
    start = _clamp(*_shift(close, -1), close_day or close.day)
    return {
        "reference_month": due.replace(day=1),
        "period_start": start,
        "period_end": close - timedelta(days=1),
        "close_date": close,
        "effective_due_date": _next_business_day(due),
    }


def upgrade() -> None:
    op.alter_column(
        "credit_card_bills", "external_id", existing_type=sa.String(255), nullable=True
    )
    op.add_column(
        "credit_card_bills",
        sa.Column("source", sa.String(10), nullable=False, server_default="provider"),
    )
    for name in ("reference_month", "period_start", "period_end", "close_date", "effective_due_date"):
        op.add_column("credit_card_bills", sa.Column(name, sa.Date(), nullable=True))
    op.add_column(
        "credit_card_bills", sa.Column("declared_total", sa.Numeric(15, 2), nullable=True)
    )
    for name in ("computed_total", "paid_amount"):
        op.add_column(
            "credit_card_bills",
            sa.Column(name, sa.Numeric(15, 2), nullable=False, server_default="0"),
        )
    op.add_column("credit_card_bills", sa.Column("settled_on", sa.Date(), nullable=True))

    conn = op.get_bind()
    rows = conn.execute(
        sa.text(
            """
            SELECT b.id, b.due_date, a.statement_close_day
            FROM credit_card_bills b JOIN accounts a ON a.id = b.account_id
            """
        )
    ).fetchall()
    for bill_id, due, close_day in rows:
        if isinstance(due, str):  # SQLite returns DATE as text
            due = date.fromisoformat(due)
        conn.execute(
            sa.text(
                """
                UPDATE credit_card_bills SET
                    reference_month = :reference_month,
                    period_start = :period_start,
                    period_end = :period_end,
                    close_date = :close_date,
                    effective_due_date = :effective_due_date,
                    declared_total = total_amount
                WHERE id = :id
                """
            ),
            {"id": bill_id, **_provider_period(due, close_day)},
        )

    with op.batch_alter_table("credit_card_bills") as batch:
        for name in ("reference_month", "period_start", "period_end", "close_date", "effective_due_date"):
            batch.alter_column(name, existing_type=sa.Date(), nullable=False)
    op.create_index(
        "ux_cc_bills_account_reference_month",
        "credit_card_bills",
        ["account_id", "reference_month"],
        unique=True,
        postgresql_where=sa.text("source <> 'provider'"),
        sqlite_where=sa.text("source <> 'provider'"),
    )

    with op.batch_alter_table("transactions") as batch:
        batch.add_column(sa.Column("paid_bill_id", postgresql.UUID(as_uuid=True), nullable=True))
        batch.add_column(
            sa.Column("bill_payment_pair", sa.Boolean(), nullable=False, server_default="false")
        )
        batch.create_foreign_key(
            "fk_transactions_paid_bill_id",
            "credit_card_bills",
            ["paid_bill_id"],
            ["id"],
            ondelete="SET NULL",
        )
    op.create_index("ix_transactions_paid_bill_id", "transactions", ["paid_bill_id"])

    op.add_column(
        "categories",
        sa.Column("is_bill_payment", sa.Boolean(), nullable=False, server_default="false"),
    )

    op.create_table(
        "bill_payment_dismissals",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "workspace_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("workspaces.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "transaction_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("transactions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "bill_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("credit_card_bills.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("transaction_id", "bill_id", name="uq_bill_payment_dismissals_tx_bill"),
    )
    op.create_index(
        "ix_bill_payment_dismissals_workspace_id", "bill_payment_dismissals", ["workspace_id"]
    )
    op.create_index("ix_bill_payment_dismissals_bill_id", "bill_payment_dismissals", ["bill_id"])


def downgrade() -> None:
    op.drop_index("ix_bill_payment_dismissals_bill_id", table_name="bill_payment_dismissals")
    op.drop_index("ix_bill_payment_dismissals_workspace_id", table_name="bill_payment_dismissals")
    op.drop_table("bill_payment_dismissals")
    op.drop_column("categories", "is_bill_payment")

    op.drop_index("ix_transactions_paid_bill_id", table_name="transactions")
    with op.batch_alter_table("transactions") as batch:
        batch.drop_constraint("fk_transactions_paid_bill_id", type_="foreignkey")
        batch.drop_column("bill_payment_pair")
        batch.drop_column("paid_bill_id")

    op.drop_index("ux_cc_bills_account_reference_month", table_name="credit_card_bills")
    # Auto and manual bills cannot survive the old schema (no external id,
    # no provider behind them); their transactions unlink via ON DELETE SET NULL.
    op.execute("DELETE FROM credit_card_bills WHERE source <> 'provider'")
    with op.batch_alter_table("credit_card_bills") as batch:
        for name in (
            "settled_on",
            "paid_amount",
            "computed_total",
            "declared_total",
            "effective_due_date",
            "close_date",
            "period_end",
            "period_start",
            "reference_month",
            "source",
        ):
            batch.drop_column(name)
        batch.alter_column("external_id", existing_type=sa.String(255), nullable=False)
