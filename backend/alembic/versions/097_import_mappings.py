"""saved CSV import mappings

A user can name a CSV column mapping, pick the account it imports into
and have it re-applied whenever a file with the same header set is
uploaded again.

- `import_mappings` belongs to a user (not a workspace); deleting the
  user deletes the mappings.
- `account_id` is cleared, not cascaded, when the account is deleted:
  the mapping still works, it just has no preselected account.
- `(user_id, name_key)` is unique, `name_key` being the lowercased name,
  so names are unique per user ignoring case.
- `(user_id, headers_key)` is indexed for the header-set lookup.

Revision ID: 097
Revises: 096
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "097"
down_revision = "096"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "import_mappings",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("name_key", sa.String(length=100), nullable=False),
        sa.Column("account_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("headers", sa.JSON(), nullable=False),
        sa.Column("headers_key", sa.String(length=64), nullable=False),
        sa.Column("column_mapping", sa.JSON(), nullable=False),
        sa.Column("options", sa.JSON(), nullable=False),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["account_id"], ["accounts.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "name_key", name="uq_import_mappings_user_name_key"),
    )
    op.create_index("ix_import_mappings_user_id", "import_mappings", ["user_id"])
    op.create_index(
        "ix_import_mappings_user_headers_key", "import_mappings", ["user_id", "headers_key"]
    )


def downgrade() -> None:
    op.drop_index("ix_import_mappings_user_headers_key", table_name="import_mappings")
    op.drop_index("ix_import_mappings_user_id", table_name="import_mappings")
    op.drop_table("import_mappings")
