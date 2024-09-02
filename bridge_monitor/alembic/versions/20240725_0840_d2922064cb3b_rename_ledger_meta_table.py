"""rename ledger meta table

Revision ID: d2922064cb3b
Revises: 9a170f8e08a9
Create Date: 2024-07-25 08:40:48.981253

"""

from alembic import op

# revision identifiers, used by Alembic.
revision = "d2922064cb3b"
down_revision = "9a170f8e08a9"
branch_labels = None
depends_on = None


def upgrade():
    op.rename_table("ledger_meta", "ledger_update_meta")


def downgrade():
    op.rename_table("ledger_update_meta", "ledger_meta")
