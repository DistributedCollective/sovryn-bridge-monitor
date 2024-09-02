"""vouts to btc transactions

Revision ID: 529b5d405cda
Revises: 0c2171b47894
Create Date: 2024-06-04 12:05:20.543880

"""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "529b5d405cda"
down_revision = "0c2171b47894"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "btc_wallet_transaction", sa.Column("vout", sa.Integer(), nullable=False)
    )
    op.add_column(
        "pending_btc_wallet_transaction",
        sa.Column("vout", sa.Integer(), nullable=False),
    )

    op.drop_constraint("pk_btc_wallet_transaction", "btc_wallet_transaction")
    op.drop_constraint(
        "pk_pending_btc_wallet_transaction", "pending_btc_wallet_transaction"
    )

    op.create_primary_key(
        "wallet_vout_pk", "btc_wallet_transaction", ["wallet_id", "tx_hash", "vout"]
    )
    op.create_primary_key(
        "pending_vout_pk",
        "pending_btc_wallet_transaction",
        ["wallet_id", "tx_hash", "vout"],
    )


def downgrade():
    op.drop_column("pending_btc_wallet_transaction", "vout")
    op.drop_column("btc_wallet_transaction", "vout")

    op.drop_constraint("wallet_vout_pk", "btc_wallet_transaction")
    op.drop_constraint("pending_vout_pk", "pending_btc_wallet_transaction")

    op.create_primary_key(
        "pk_btc_wallet_transaction", "btc_wallet_transaction", ["wallet_id", "tx_hash"]
    )
    op.create_primary_key(
        "pk_pending_btc_wallet_transaction",
        "pending_btc_wallet_transaction",
        ["wallet_id", "tx_hash"],
    )
