"""add ledger meta table

Revision ID: 9a170f8e08a9
Revises: 529b5d405cda
Create Date: 2024-07-22 13:14:08.412057

"""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "9a170f8e08a9"
down_revision = "529b5d405cda"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "ledger_meta",
        sa.Column("timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.Column("failed", sa.Boolean(), nullable=False),
        sa.Column("error", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("timestamp", name=op.f("pk_ledger_meta")),
    )


def downgrade():
    op.drop_table("ledger_meta")
