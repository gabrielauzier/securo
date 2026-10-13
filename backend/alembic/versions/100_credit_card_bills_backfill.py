"""backfill credit card bills for existing card transactions

Every credit card with both `statement_close_day` and `payment_due_day`
gets an `auto` bill for each reference month its transactions fall in, and
every unlinked non-opening transaction of the card is linked to its bill.
Rows already linked (provider bills) stay where they are; a period already
covered by a bill, provider or not, reuses it. A row with a manual
`effective_bill_date` override links only to an existing bill with that due
date. Afterwards the stored aggregates (`computed_total`, `paid_amount`,
`settled_on`) of every bill are computed.

Running it again finds every row linked and creates nothing. Historical
bill payments are not matched here (spec decision Q7).

The period and holiday math is a frozen copy so later changes to the app
code cannot change what this migration does.

Revision ID: 100
Revises: 099
"""
import calendar
import uuid
from datetime import date, timedelta
from decimal import Decimal

from alembic import op
import sqlalchemy as sa

revision = "100"
down_revision = "099"
branch_labels = None
depends_on = None

_ZERO = Decimal("0.00")
_CENT = Decimal("0.01")


# --- Frozen period and holiday math ---------------------------------------


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


def _bill_period(tx_date: date, close_day: int, due_day: int) -> dict:
    """The bill a purchase belongs to: the close is the first close day
    strictly after the purchase, the nominal due the first due day strictly
    after the close."""
    close = _clamp(tx_date.year, tx_date.month, close_day)
    if close <= tx_date:
        close = _clamp(*_shift(tx_date, 1), close_day)
    due = _clamp(close.year, close.month, due_day)
    if due <= close:
        due = _clamp(*_shift(close, 1), due_day)
    return {
        "reference_month": due.replace(day=1),
        "period_start": _clamp(*_shift(close, -1), close_day),
        "period_end": close - timedelta(days=1),
        "close_date": close,
        "nominal_due_date": due,
        "effective_due_date": _next_business_day(due),
    }


# --- Backfill ---------------------------------------------------------------

_BILL_COLUMNS = {
    "id": sa.Uuid(),
    "account_id": sa.Uuid(),
    "source": sa.String(),
    "reference_month": sa.Date(),
    "period_start": sa.Date(),
    "period_end": sa.Date(),
    "close_date": sa.Date(),
    "due_date": sa.Date(),
    "effective_due_date": sa.Date(),
    "declared_total": sa.Numeric(15, 2),
}


def _bills(conn, account_id: uuid.UUID) -> list[dict]:
    rows = conn.execute(
        sa.text(
            "SELECT id, account_id, source, reference_month, period_start, period_end, "
            "close_date, due_date, effective_due_date, declared_total "
            "FROM credit_card_bills WHERE account_id = :account_id"
        )
        .bindparams(sa.bindparam("account_id", type_=sa.Uuid()))
        .columns(**_BILL_COLUMNS),
        {"account_id": account_id},
    ).mappings().all()
    return [dict(row) for row in rows]


def _target_bill(account: dict, cycle: tuple[int, int], tx: dict, bills: list[dict], new_bills: list[dict]):
    override = tx["effective_bill_date"]
    if override is not None:
        return next((b for b in bills if override in (b["effective_due_date"], b["due_date"])), None)
    containing = sorted(
        (b for b in bills if b["period_start"] <= tx["date"] <= b["period_end"]),
        key=lambda b: b["source"] != "provider",
    )
    if containing:
        return containing[0]
    period = _bill_period(tx["date"], *cycle)
    same_month = sorted(
        (b for b in bills if b["reference_month"] == period["reference_month"]),
        key=lambda b: b["source"] != "provider",
    )
    if same_month:
        return same_month[0]
    bill = {
        "id": uuid.uuid4(),
        "user_id": account["user_id"],
        "workspace_id": account["workspace_id"],
        "account_id": account["id"],
        "source": "auto",
        "reference_month": period["reference_month"],
        "period_start": period["period_start"],
        "period_end": period["period_end"],
        "close_date": period["close_date"],
        "due_date": period["nominal_due_date"],
        "effective_due_date": period["effective_due_date"],
        "declared_total": None,
        "currency": account["currency"] or "BRL",
    }
    bills.append(bill)
    new_bills.append(bill)
    return bill


def _link_card(conn, account: dict) -> tuple[list[dict], list[dict]]:
    """New bills of the card and the (row, bill) links to write."""
    cycle = (account["statement_close_day"], account["payment_due_day"])
    bills = _bills(conn, account["id"])
    rows = conn.execute(
        sa.text(
            "SELECT id, date, effective_bill_date FROM transactions "
            "WHERE account_id = :account_id AND bill_id IS NULL "
            "AND source <> 'opening_balance' ORDER BY date"
        )
        .bindparams(sa.bindparam("account_id", type_=sa.Uuid()))
        .columns(id=sa.Uuid(), date=sa.Date(), effective_bill_date=sa.Date()),
        {"account_id": account["id"]},
    ).mappings().all()
    new_bills: list[dict] = []
    links: list[dict] = []
    for tx in rows:
        bill = _target_bill(account, cycle, tx, bills, new_bills)
        if bill is not None:
            links.append({"tx_id": tx["id"], "bill_id": bill["id"]})
    return new_bills, links


def _insert_bills(conn, bills: list[dict]) -> None:
    if not bills:
        return
    conn.execute(
        sa.text(
            "INSERT INTO credit_card_bills (id, user_id, workspace_id, account_id, external_id, "
            "source, reference_month, period_start, period_end, close_date, due_date, "
            "effective_due_date, declared_total, computed_total, paid_amount, settled_on, "
            "total_amount, currency, created_at, updated_at) VALUES (:id, :user_id, "
            ":workspace_id, :account_id, NULL, :source, :reference_month, :period_start, "
            ":period_end, :close_date, :due_date, :effective_due_date, NULL, 0, 0, NULL, 0, "
            ":currency, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
        ).bindparams(
            sa.bindparam("id", type_=sa.Uuid()),
            sa.bindparam("user_id", type_=sa.Uuid()),
            sa.bindparam("workspace_id", type_=sa.Uuid()),
            sa.bindparam("account_id", type_=sa.Uuid()),
            *(
                sa.bindparam(name, type_=sa.Date())
                for name in (
                    "reference_month",
                    "period_start",
                    "period_end",
                    "close_date",
                    "due_date",
                    "effective_due_date",
                )
            ),
        ),
        [{k: v for k, v in bill.items() if k != "declared_total"} for bill in bills],
    )


def _write_links(conn, links: list[dict]) -> None:
    if not links:
        return
    conn.execute(
        sa.text("UPDATE transactions SET bill_id = :bill_id WHERE id = :tx_id").bindparams(
            sa.bindparam("bill_id", type_=sa.Uuid()), sa.bindparam("tx_id", type_=sa.Uuid())
        ),
        links,
    )


def _refresh_all_bills(conn) -> None:
    """Frozen copy of the `refresh_bills` aggregate rules, for every bill."""
    computed = {
        row["bill_id"]: Decimal(str(row["total"] or 0)).quantize(_CENT)
        for row in conn.execute(
            sa.text(
                """
                SELECT t.bill_id AS bill_id,
                       SUM(CASE WHEN t.type = 'debit' THEN ABS(t.amount)
                                ELSE -ABS(t.amount) END) AS total
                FROM transactions t
                LEFT JOIN categories c ON c.id = t.category_id
                WHERE t.bill_id IS NOT NULL
                  AND t.source <> 'opening_balance'
                  AND t.is_ignored = false
                  AND (c.id IS NULL OR (c.is_bill_payment = false AND c.is_ignored = false))
                  AND (t.transfer_pair_id IS NULL OR t.transfer_pair_id NOT IN (
                        SELECT p.transfer_pair_id FROM transactions p
                        WHERE p.paid_bill_id IS NOT NULL AND p.transfer_pair_id IS NOT NULL))
                GROUP BY t.bill_id
                """
            ).columns(bill_id=sa.Uuid(), total=sa.Numeric(15, 2))
        ).mappings()
    }
    payments: dict[uuid.UUID, list[tuple[date, Decimal]]] = {}
    for row in conn.execute(
        sa.text(
            "SELECT paid_bill_id, date, ABS(amount) AS amount FROM transactions "
            "WHERE paid_bill_id IS NOT NULL ORDER BY date, created_at"
        ).columns(paid_bill_id=sa.Uuid(), date=sa.Date(), amount=sa.Numeric(15, 2))
    ).mappings():
        payments.setdefault(row["paid_bill_id"], []).append((row["date"], Decimal(str(row["amount"]))))

    updates = []
    for bill in conn.execute(
        sa.text("SELECT id, close_date, declared_total FROM credit_card_bills").columns(
            id=sa.Uuid(), close_date=sa.Date(), declared_total=sa.Numeric(15, 2)
        )
    ).mappings():
        total = computed.get(bill["id"], _ZERO)
        target = Decimal(str(bill["declared_total"])) if bill["declared_total"] is not None else total
        paid = _ZERO
        settled_on = bill["close_date"] if target <= 0 else None
        for paid_on, amount in payments.get(bill["id"], []):
            paid += amount
            if settled_on is None and paid >= target:
                settled_on = paid_on
        updates.append(
            {"id": bill["id"], "computed_total": total, "paid_amount": paid, "settled_on": settled_on}
        )
    if updates:
        conn.execute(
            sa.text(
                "UPDATE credit_card_bills SET computed_total = :computed_total, "
                "paid_amount = :paid_amount, settled_on = :settled_on WHERE id = :id"
            ).bindparams(
                sa.bindparam("id", type_=sa.Uuid()),
                sa.bindparam("computed_total", type_=sa.Numeric(15, 2)),
                sa.bindparam("paid_amount", type_=sa.Numeric(15, 2)),
                sa.bindparam("settled_on", type_=sa.Date()),
            ),
            updates,
        )


def upgrade() -> None:
    conn = op.get_bind()
    cards = conn.execute(
        sa.text(
            "SELECT id, user_id, workspace_id, currency, statement_close_day, payment_due_day "
            "FROM accounts WHERE type = 'credit_card' "
            "AND statement_close_day IS NOT NULL AND payment_due_day IS NOT NULL "
            "AND statement_close_day > 0 AND payment_due_day > 0"
        ).columns(id=sa.Uuid(), user_id=sa.Uuid(), workspace_id=sa.Uuid())
    ).mappings().all()
    for account in cards:
        new_bills, links = _link_card(conn, dict(account))
        _insert_bills(conn, new_bills)
        _write_links(conn, links)
    _refresh_all_bills(conn)


def downgrade() -> None:
    # Nothing to undo: auto bills are dropped by the downgrade of 099, which
    # unlinks their transactions through ON DELETE SET NULL.
    pass
