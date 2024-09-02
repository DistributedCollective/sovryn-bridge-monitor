"""Add description override table

Revision ID: 3f4050b18717
Revises: 1eb0dd295412
Create Date: 2024-07-31 09:54:37.915102

"""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "3f4050b18717"
down_revision = "1eb0dd295412"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "ledger_description_override",
        sa.Column("tx_hash", sa.Text(), nullable=False),
        sa.Column("description_override", sa.Text(), nullable=False),
        sa.PrimaryKeyConstraint("tx_hash", name=op.f("pk_ledger_description_override")),
    )


def downgrade():
    op.drop_table("ledger_description_override")
