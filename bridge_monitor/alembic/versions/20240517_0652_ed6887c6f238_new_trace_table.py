"""new trace table

Revision ID: ed6887c6f238
Revises: 0f37e4d867dd
Create Date: 2024-05-17 06:52:35.574681

"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "ed6887c6f238"
down_revision = "0f37e4d867dd"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "rsk_tx_trace",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("tx_hash", sa.Text(), nullable=False),
        sa.Column("block_n", sa.Integer(), nullable=True),
        sa.Column("chain_id", sa.Integer(), nullable=True),
        sa.Column("block_time", sa.DateTime(timezone=True), nullable=True),
        sa.Column("to_address", sa.Text(), nullable=False),
        sa.Column("from_address", sa.Text(), nullable=False),
        sa.Column("trace_index", sa.Integer(), nullable=False),
        sa.Column("value", sa.Numeric(precision=32, scale=0), nullable=False),
        sa.Column("action", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.CheckConstraint(
            "LOWER(from_address) = from_address",
            name=op.f("ck_rsk_tx_trace_from_address_lowercase"),
        ),
        sa.CheckConstraint(
            "LOWER(to_address) = to_address",
            name=op.f("ck_rsk_tx_trace_to_address_lowercase"),
        ),
        sa.ForeignKeyConstraint(
            ["block_n", "chain_id"],
            ["block_info.block_number", "block_info.block_chain_id"],
            name=op.f("fk_rsk_tx_trace_block_n_block_info"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_rsk_tx_trace")),
        sa.UniqueConstraint(
            "tx_hash", "trace_index", name=op.f("uq_rsk_tx_trace_tx_hash")
        ),
    )
    op.drop_constraint("unique_tx", "rsk_tx_info_old", type_="unique")
    op.create_unique_constraint(
        op.f("uq_rsk_tx_info_old_address_id"),
        "rsk_tx_info_old",
        ["address_id", "tx_hash"],
    )


def downgrade():
    op.drop_constraint(
        op.f("uq_rsk_tx_info_old_address_id"), "rsk_tx_info_old", type_="unique"
    )
    op.create_unique_constraint(
        "unique_tx", "rsk_tx_info_old", ["address_id", "tx_hash"]
    )
    op.drop_table("rsk_tx_trace")
