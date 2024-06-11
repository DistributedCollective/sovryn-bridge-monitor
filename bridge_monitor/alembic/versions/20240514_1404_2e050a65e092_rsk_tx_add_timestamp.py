"""rsk_tx_add_timestamp

Revision ID: 2e050a65e092
Revises: 04c35b0474d1
Create Date: 2024-05-14 14:04:15.198656

"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "2e050a65e092"
down_revision = "04c35b0474d1"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("rsk_tx_info", sa.Column("chain_id", sa.Integer(), nullable=True))
    op.add_column(
        "rsk_tx_info", sa.Column("blocktime", sa.DateTime(timezone=True), nullable=True)
    )
    op.alter_column("rsk_tx_info", "block_n", existing_type=sa.INTEGER(), nullable=True)
    op.create_foreign_key(
        "fk_block_info",
        "rsk_tx_info",
        "block_info",
        ["block_n", "chain_id"],
        ["block_number", "block_chain_id"],
    )


def downgrade():
    op.drop_constraint("fk_block_info", "rsk_tx_info", type_="foreignkey")
    op.alter_column(
        "rsk_tx_info", "block_n", existing_type=sa.INTEGER(), nullable=False
    )
    op.drop_column("rsk_tx_info", "blocktime")
    op.drop_column("rsk_tx_info", "chain_id")
