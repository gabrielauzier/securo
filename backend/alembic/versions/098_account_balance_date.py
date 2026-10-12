"""account balance date

The date chosen as "balance date" in the account dialog was only the date of
the synthetic `opening_balance` transaction, so it was lost when the balance
went to 0 and could not be kept on its own. It now lives on the account.

- `accounts.balance_date` is nullable. NULL means no floor: every countable
  transaction is summed.
- Manual accounts are backfilled with the latest `opening_balance`
  transaction date, which is the date the balance floor already uses, so
  displayed balances do not change.
- Bank-connected accounts and manual accounts with no opening transaction
  stay NULL.

Revision ID: 098
Revises: 097
"""
from alembic import op
import sqlalchemy as sa

revision = "098"
down_revision = "097"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("accounts", sa.Column("balance_date", sa.Date(), nullable=True))
    op.execute(
        """
        UPDATE accounts SET balance_date = (
            SELECT max(t.date) FROM transactions t
            WHERE t.account_id = accounts.id AND t.source = 'opening_balance'
        ) WHERE connection_id IS NULL
        """
    )


def downgrade() -> None:
    op.drop_column("accounts", "balance_date")
