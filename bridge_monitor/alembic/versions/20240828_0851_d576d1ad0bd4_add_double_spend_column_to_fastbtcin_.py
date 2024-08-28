"""Add double spend column to fastbtcin table

Revision ID: d576d1ad0bd4
Revises: 3f4050b18717
Create Date: 2024-08-28 08:51:42.341892

"""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "d576d1ad0bd4"
down_revision = "3f4050b18717"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "fastbtc_in_transfer",
        sa.Column(
            "is_double_spend", sa.Boolean(), server_default="false", nullable=False
        ),
    )


def downgrade():
    op.drop_column("fastbtc_in_transfer", "is_double_spend")
