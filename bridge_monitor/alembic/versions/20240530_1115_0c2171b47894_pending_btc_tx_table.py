"""pending btc tx table

Revision ID: 0c2171b47894
Revises: 166909696ec7
Create Date: 2024-05-30 11:15:43.939178

"""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "0c2171b47894"
down_revision = "166909696ec7"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "pending_btc_wallet_transaction",
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
            name=op.f("fk_pending_btc_wallet_transaction_wallet_id_btc_wallet"),
        ),
        sa.PrimaryKeyConstraint(
            "wallet_id", "tx_hash", name=op.f("pk_pending_btc_wallet_transaction")
        ),
    )


def downgrade():
    op.drop_table("pending_btc_wallet_transaction")
