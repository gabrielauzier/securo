"""ABD-03: migration 098 adds accounts.balance_date and backfills it.

Runs the real upgrade()/downgrade() of the migration against a scratch sqlite
database seeded with the columns the backfill reads.
"""
import importlib.util
from datetime import date
from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic.operations import Operations
from alembic.runtime.migration import MigrationContext

_MIGRATION_PATH = (
    Path(__file__).resolve().parent.parent
    / "alembic"
    / "versions"
    / "098_account_balance_date.py"
)
_SPEC = importlib.util.spec_from_file_location("account_balance_date_migration", _MIGRATION_PATH)
assert _SPEC is not None and _SPEC.loader is not None
migration = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(migration)


@pytest.fixture
def engine():
    eng = sa.create_engine("sqlite://")
    with eng.begin() as conn:
        conn.execute(sa.text("CREATE TABLE accounts (id TEXT PRIMARY KEY, connection_id TEXT)"))
        conn.execute(
            sa.text(
                "CREATE TABLE transactions "
                "(id TEXT PRIMARY KEY, account_id TEXT, source TEXT, date DATE)"
            )
        )
    yield eng
    eng.dispose()


def _seed(conn):
    accounts = [
        ("manual-two", None),
        ("manual-one", None),
        ("manual-none", None),
        ("connected", "conn-1"),
    ]
    for account_id, connection_id in accounts:
        conn.execute(
            sa.text("INSERT INTO accounts (id, connection_id) VALUES (:id, :c)"),
            {"id": account_id, "c": connection_id},
        )
    txs = [
        # latest opening_balance date must win
        ("t1", "manual-two", "opening_balance", date(2024, 1, 10)),
        ("t2", "manual-two", "opening_balance", date(2025, 6, 20)),
        ("t3", "manual-two", "manual", date(2026, 1, 1)),  # later, but not an opening row
        ("t4", "manual-one", "opening_balance", date(2025, 3, 5)),
        ("t5", "manual-none", "manual", date(2025, 7, 7)),
        # connected account carrying an opening row must stay NULL
        ("t6", "connected", "opening_balance", date(2025, 9, 9)),
    ]
    for tx_id, account_id, source, tx_date in txs:
        conn.execute(
            sa.text(
                "INSERT INTO transactions (id, account_id, source, date) "
                "VALUES (:id, :a, :s, :d)"
            ),
            {"id": tx_id, "a": account_id, "s": source, "d": tx_date.isoformat()},
        )


def _run(conn, direction: str) -> None:
    ctx = MigrationContext.configure(conn)
    with Operations.context(ctx):
        getattr(migration, direction)()


def _balance_dates(conn) -> dict:
    rows = conn.execute(sa.text("SELECT id, balance_date FROM accounts")).all()
    return {row[0]: row[1] for row in rows}


def test_upgrade_backfills_manual_accounts_from_the_latest_opening_transaction(engine):
    with engine.begin() as conn:
        _seed(conn)
        _run(conn, "upgrade")
        dates = _balance_dates(conn)

    assert dates["manual-two"] == "2025-06-20"
    assert dates["manual-one"] == "2025-03-05"
    assert dates["manual-none"] is None
    assert dates["connected"] is None


def test_downgrade_drops_the_column_without_error(engine):
    with engine.begin() as conn:
        _seed(conn)
        _run(conn, "upgrade")
        _run(conn, "downgrade")
        columns = [c["name"] for c in sa.inspect(conn).get_columns("accounts")]

    assert "balance_date" not in columns
