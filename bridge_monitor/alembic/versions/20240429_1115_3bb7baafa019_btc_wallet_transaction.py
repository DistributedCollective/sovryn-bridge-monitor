"""btc_wallet_transaction

Revision ID: 3bb7baafa019
Revises: c0e4e10a72e6
Create Date: 2024-04-29 11:15:56.484357

"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "3bb7baafa019"
down_revision = "c0e4e10a72e6"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "btc_wallet",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_btc_wallet")),
    )
    op.create_table(
        "btc_wallet_transaction",
        sa.Column("wallet_id", sa.Integer(), nullable=False),
        sa.Column("tx_hash", sa.Text(), nullable=False),
        sa.Column("timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.Column("net_change", sa.Numeric(precision=40, scale=32), nullable=False),
        sa.Column("amount_sent", sa.Numeric(precision=40, scale=32), nullable=False),
        sa.Column(
            "amount_received", sa.Numeric(precision=40, scale=32), nullable=False
        ),
        sa.Column("amount_fees", sa.Numeric(precision=40, scale=32), nullable=False),
        sa.Column("tx_type", sa.Text(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("block_height", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(
            ["wallet_id"],
            ["btc_wallet.id"],
            name=op.f("fk_btc_wallet_transaction_wallet_id_btc_wallet"),
        ),
        sa.PrimaryKeyConstraint(
            "wallet_id", "tx_hash", name=op.f("pk_btc_wallet_transaction")
        ),
    )


def downgrade():
    op.drop_table("btc_wallet_transaction")
    op.drop_table("btc_wallet")
