"""chain_info_tables

Revision ID: c0e4e10a72e6
Revises: c349734b0d55
Create Date: 2024-04-17 10:05:22.670646

"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "c0e4e10a72e6"
down_revision = "c349734b0d55"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "block_chain",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("safe_limit", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_block_chain")),
    )
    op.create_table(
        "block_info",
        sa.Column("block_chain_id", sa.Integer(), nullable=False),
        sa.Column("block_number", sa.Integer(), nullable=False),
        sa.Column("timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["block_chain_id"],
            ["block_chain.id"],
            name=op.f("fk_block_info_block_chain_id_block_chain"),
        ),
        sa.PrimaryKeyConstraint(
            "block_chain_id", "block_number", name=op.f("pk_block_info")
        ),
    )


def downgrade():
    op.drop_table("block_info")
    op.drop_table("block_chain")
