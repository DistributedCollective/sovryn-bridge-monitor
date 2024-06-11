"""full unmapped trace

Revision ID: 5a319af140ea
Revises: ed6887c6f238
Create Date: 2024-05-19 08:11:13.147777

"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "5a319af140ea"
down_revision = "ed6887c6f238"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "rsk_tx_trace",
        sa.Column("unmapped", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    )
    op.add_column("rsk_tx_trace", sa.Column("error", sa.Text(), nullable=True))
    op.drop_column("rsk_tx_trace", "action")


def downgrade():
    op.add_column(
        "rsk_tx_trace",
        sa.Column(
            "action",
            postgresql.JSONB(astext_type=sa.Text()),
            autoincrement=False,
            nullable=False,
        ),
    )
    op.drop_column("rsk_tx_trace", "error")
    op.drop_column("rsk_tx_trace", "unmapped")
