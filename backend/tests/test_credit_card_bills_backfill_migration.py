"""BILL-04: migration 100 backfills bills for existing card transactions (P1 AC 14, 15).

Runs the real upgrade() of the migration against a scratch sqlite database
holding the post-099 columns the backfill reads and writes.
"""
import dataclasses
import importlib.util
import uuid
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic.operations import Operations
from alembic.runtime.migration import MigrationContext

from app.services.credit_card_service import bill_period_for

_MIGRATION_PATH = (
    Path(__file__).resolve().parent.parent
    / "alembic"
    / "versions"
    / "100_credit_card_bills_backfill.py"
)
_SPEC = importlib.util.spec_from_file_location("credit_card_bills_backfill", _MIGRATION_PATH)
assert _SPEC is not None and _SPEC.loader is not None
migration = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(migration)

meta = sa.MetaData()
accounts = sa.Table(
    "accounts",
    meta,
    sa.Column("id", sa.Uuid(), primary_key=True),
    sa.Column("user_id", sa.Uuid()),
    sa.Column("workspace_id", sa.Uuid()),
    sa.Column("type", sa.String(20)),
    sa.Column("currency", sa.String(3)),
    sa.Column("statement_close_day", sa.SmallInteger()),
    sa.Column("payment_due_day", sa.SmallInteger()),
)
categories = sa.Table(
    "categories",
    meta,
    sa.Column("id", sa.Uuid(), primary_key=True),
    sa.Column("is_bill_payment", sa.Boolean(), server_default="0"),
    sa.Column("is_ignored", sa.Boolean(), server_default="0"),
)
bills = sa.Table(
    "credit_card_bills",
    meta,
    sa.Column("id", sa.Uuid(), primary_key=True),
    sa.Column("user_id", sa.Uuid()),
    sa.Column("workspace_id", sa.Uuid()),
    sa.Column("account_id", sa.Uuid()),
    sa.Column("external_id", sa.String(255)),
    sa.Column("source", sa.String(10)),
    sa.Column("reference_month", sa.Date()),
    sa.Column("period_start", sa.Date()),
    sa.Column("period_end", sa.Date()),
    sa.Column("close_date", sa.Date()),
    sa.Column("due_date", sa.Date()),
    sa.Column("effective_due_date", sa.Date()),
    sa.Column("declared_total", sa.Numeric(15, 2)),
    sa.Column("computed_total", sa.Numeric(15, 2), server_default="0"),
    sa.Column("paid_amount", sa.Numeric(15, 2), server_default="0"),
    sa.Column("settled_on", sa.Date()),
    sa.Column("total_amount", sa.Numeric(15, 2)),
    sa.Column("currency", sa.String(3)),
    sa.Column("created_at", sa.DateTime()),
    sa.Column("updated_at", sa.DateTime()),
)
transactions = sa.Table(
    "transactions",
    meta,
    sa.Column("id", sa.Uuid(), primary_key=True),
    sa.Column("account_id", sa.Uuid()),
    sa.Column("category_id", sa.Uuid()),
    sa.Column("date", sa.Date()),
    sa.Column("type", sa.String(10)),
    sa.Column("amount", sa.Numeric(15, 2)),
    sa.Column("source", sa.String(20)),
    sa.Column("is_ignored", sa.Boolean(), server_default="0"),
    sa.Column("effective_bill_date", sa.Date()),
    sa.Column("bill_id", sa.Uuid()),
    sa.Column("paid_bill_id", sa.Uuid()),
    sa.Column("transfer_pair_id", sa.Uuid()),
    sa.Column("created_at", sa.DateTime()),
)

USER = uuid.uuid4()
WORKSPACE = uuid.uuid4()
CARD = uuid.uuid4()
SYNCED_CARD = uuid.uuid4()
UNCONFIGURED_CARD = uuid.uuid4()
PROVIDER_BILL = uuid.uuid4()


@pytest.fixture
def engine():
    eng = sa.create_engine("sqlite://")
    meta.create_all(eng)
    yield eng
    eng.dispose()


def _account(conn, account_id, close_day, due_day):
    conn.execute(
        accounts.insert().values(
            id=account_id,
            user_id=USER,
            workspace_id=WORKSPACE,
            type="credit_card",
            currency="BRL",
            statement_close_day=close_day,
            payment_due_day=due_day,
        )
    )


def _tx(conn, account_id, on, amount="100.00", **extra) -> uuid.UUID:
    tx_id = uuid.uuid4()
    conn.execute(
        transactions.insert().values(
            id=tx_id,
            account_id=account_id,
            date=on,
            type=extra.pop("type", "debit"),
            amount=Decimal(amount),
            source=extra.pop("source", "csv"),
            **extra,
        )
    )
    return tx_id


def _seed(conn) -> dict[str, uuid.UUID]:
    # The P1 Independent Test card: close 5, due 12.
    _account(conn, CARD, 5, 12)
    ids = {
        "aug_04": _tx(conn, CARD, date(2026, 8, 4)),
        "aug_05": _tx(conn, CARD, date(2026, 8, 5), amount="50.00"),
        "sep_04": _tx(conn, CARD, date(2026, 9, 4), amount="25.00"),
        "opening": _tx(conn, CARD, date(2026, 8, 1), amount="999.00", source="opening_balance"),
    }
    # A synced card with one provider bill and a row already linked to it.
    _account(conn, SYNCED_CARD, 5, 12)
    conn.execute(
        bills.insert().values(
            id=PROVIDER_BILL,
            user_id=USER,
            workspace_id=WORKSPACE,
            account_id=SYNCED_CARD,
            external_id="pluggy-bill-1",
            source="provider",
            reference_month=date(2026, 9, 1),
            period_start=date(2026, 8, 5),
            period_end=date(2026, 9, 4),
            close_date=date(2026, 9, 5),
            due_date=date(2026, 9, 12),
            effective_due_date=date(2026, 9, 14),
            declared_total=Decimal("300.00"),
            total_amount=Decimal("300.00"),
            currency="BRL",
        )
    )
    ids["synced_linked"] = _tx(conn, SYNCED_CARD, date(2026, 8, 20), amount="300.00", bill_id=PROVIDER_BILL)
    ids["synced_unlinked"] = _tx(conn, SYNCED_CARD, date(2026, 8, 25), amount="40.00")
    ids["synced_next"] = _tx(conn, SYNCED_CARD, date(2026, 9, 10), amount="60.00")
    # A card without a close day gets no bills (P1 AC 13).
    _account(conn, UNCONFIGURED_CARD, None, 12)
    ids["unconfigured"] = _tx(conn, UNCONFIGURED_CARD, date(2026, 8, 10))
    return ids


def _run(conn) -> None:
    ctx = MigrationContext.configure(conn)
    with Operations.context(ctx):
        migration.upgrade()


def _bills_of(conn, account_id) -> dict[date, dict]:
    rows = conn.execute(bills.select().where(bills.c.account_id == account_id)).mappings()
    return {row["reference_month"]: dict(row) for row in rows}


def _links(conn) -> dict[uuid.UUID, uuid.UUID | None]:
    return {row.id: row.bill_id for row in conn.execute(sa.select(transactions.c.id, transactions.c.bill_id))}


def test_backfill_creates_auto_bills_and_links_the_independent_test_rows(engine):
    with engine.begin() as conn:
        ids = _seed(conn)
        _run(conn)
        card_bills = _bills_of(conn, CARD)
        unconfigured_bills = _bills_of(conn, UNCONFIGURED_CARD)
        links = _links(conn)

    # P1 Independent Test: 2026-08 holds 08-04; 2026-09 holds 08-05 and 09-04.
    assert sorted(card_bills) == [date(2026, 8, 1), date(2026, 9, 1)]
    aug, sep = card_bills[date(2026, 8, 1)], card_bills[date(2026, 9, 1)]
    assert links[ids["aug_04"]] == aug["id"]
    assert links[ids["aug_05"]] == sep["id"]
    assert links[ids["sep_04"]] == sep["id"]
    assert links[ids["opening"]] is None
    # P1 AC 2 dates for reference month 2026-09.
    assert sep["source"] == "auto"
    assert (sep["period_start"], sep["period_end"]) == (date(2026, 8, 5), date(2026, 9, 4))
    assert sep["close_date"] == date(2026, 9, 5)
    assert sep["due_date"] == date(2026, 9, 12)
    assert sep["effective_due_date"] == date(2026, 9, 14)
    assert sep["external_id"] is None
    assert sep["workspace_id"] == WORKSPACE
    assert sep["user_id"] == USER
    assert sep["currency"] == "BRL"
    # Aggregates filled; the opening balance row is not part of any bill.
    assert aug["computed_total"] == Decimal("100.00")
    assert sep["computed_total"] == Decimal("75.00")
    assert sep["paid_amount"] == Decimal("0.00")
    assert sep["settled_on"] is None
    # P1 AC 13: a card without a close day gets no bills.
    assert unconfigured_bills == {}
    assert links[ids["unconfigured"]] is None


def test_running_the_backfill_twice_yields_the_same_bills_and_links(engine):
    # P1 AC 14: idempotent.
    with engine.begin() as conn:
        _seed(conn)
        _run(conn)
        first_bills = conn.execute(bills.select().order_by(bills.c.id)).mappings().all()
        first_links = _links(conn)
        _run(conn)
        second_bills = conn.execute(bills.select().order_by(bills.c.id)).mappings().all()
        second_links = _links(conn)

    assert [dict(b) for b in second_bills] == [dict(b) for b in first_bills]
    assert second_links == first_links


def test_provider_bills_and_their_links_are_unchanged(engine):
    # P1 AC 15: the provider bill keeps its dates, totals and rows; an unlinked
    # row inside its period joins it; a row of the next period gets an auto bill.
    with engine.begin() as conn:
        ids = _seed(conn)
        _run(conn)
        synced = _bills_of(conn, SYNCED_CARD)
        links = _links(conn)

    provider = synced[date(2026, 9, 1)]
    assert provider["id"] == PROVIDER_BILL
    assert provider["source"] == "provider"
    assert provider["external_id"] == "pluggy-bill-1"
    assert (provider["period_start"], provider["period_end"]) == (date(2026, 8, 5), date(2026, 9, 4))
    assert provider["due_date"] == date(2026, 9, 12)
    assert provider["declared_total"] == Decimal("300.00")
    assert provider["total_amount"] == Decimal("300.00")
    assert links[ids["synced_linked"]] == PROVIDER_BILL
    assert links[ids["synced_unlinked"]] == PROVIDER_BILL
    assert sorted(synced) == [date(2026, 9, 1), date(2026, 10, 1)]
    assert synced[date(2026, 10, 1)]["source"] == "auto"
    assert links[ids["synced_next"]] == synced[date(2026, 10, 1)]["id"]


@pytest.mark.parametrize(("close_day", "due_day"), [(5, 12), (31, 10)])
def test_frozen_period_math_equals_the_live_bill_period_for(close_day, due_day):
    day = date(2024, 1, 1)
    while day <= date(2028, 12, 31):
        live = dataclasses.asdict(bill_period_for(day, close_day, due_day))
        assert migration._bill_period(day, close_day, due_day) == live, day
        day += timedelta(days=1)
