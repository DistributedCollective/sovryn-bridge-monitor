"""fastbtc_in_transfer

Revision ID: ddc43b246af0
Revises: b9abe6ad9a84
Create Date: 2023-06-16 13:08:35.313498

"""

import decimal
from datetime import datetime

from alembic import op
import sqlalchemy as sa
from sqlalchemy import types
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "ddc43b246af0"
down_revision = "b9abe6ad9a84"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "fastbtc_in_transfer",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("chain", sa.Text(), nullable=False),
        sa.Column("multisig_tx_id", Uint256(), nullable=False),
        sa.Column("rsk_receiver_address", sa.Text(), nullable=False),
        sa.Column("bitcoin_tx_hash", sa.Text(), nullable=True),
        sa.Column("bitcoin_tx_vout", sa.Integer(), nullable=True),
        sa.Column("transfer_function", sa.Text(), nullable=False),
        sa.Column("net_amount_wei", Uint256(), nullable=False),
        sa.Column("fee_wei", Uint256(), nullable=True),
        sa.Column(
            "status",
            sa.Enum(
                "INITIATED",
                "SUBMITTED",
                "PARTIALLY_CONFIRMED",
                "EXECUTED",
                "INVALID",
                name="fastbtc_in_transferstatus",
            ),
            nullable=False,
        ),
        sa.Column("num_confirmations", sa.Integer(), nullable=False),
        sa.Column("has_execution_failure", sa.Boolean(), nullable=True),
        sa.Column("ignored", sa.Boolean(), nullable=False),
        sa.Column("submission_block_number", sa.Integer(), nullable=True),
        sa.Column("submission_block_hash", sa.Text(), nullable=True),
        sa.Column("submission_block_timestamp", sa.Integer(), nullable=True),
        sa.Column("submission_transaction_hash", sa.Text(), nullable=True),
        sa.Column("submission_log_index", sa.Integer(), nullable=True),
        sa.Column("executed_block_number", sa.Integer(), nullable=True),
        sa.Column("executed_block_hash", sa.Text(), nullable=True),
        sa.Column("executed_block_timestamp", sa.Integer(), nullable=True),
        sa.Column("executed_transaction_hash", sa.Text(), nullable=True),
        sa.Column("executed_log_index", sa.Integer(), nullable=True),
        sa.Column("seen_on", TZDateTime(), nullable=False),
        sa.Column("updated_on", TZDateTime(), nullable=False),
        sa.Column(
            "extra_data",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default="{}",
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_fastbtc_in_transfer")),
    )
    op.create_index(
        "ix_fastbtc_in_chain_tx_id",
        "fastbtc_in_transfer",
        ["chain", "multisig_tx_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_fastbtc_in_transfer_executed_block_timestamp"),
        "fastbtc_in_transfer",
        ["executed_block_timestamp"],
        unique=False,
    )
    op.create_index(
        op.f("ix_fastbtc_in_transfer_submission_block_timestamp"),
        "fastbtc_in_transfer",
        ["submission_block_timestamp"],
        unique=False,
    )


def downgrade():
    op.drop_index(
        op.f("ix_fastbtc_in_transfer_submission_block_timestamp"),
        table_name="fastbtc_in_transfer",
    )
    op.drop_index(
        op.f("ix_fastbtc_in_transfer_executed_block_timestamp"),
        table_name="fastbtc_in_transfer",
    )
    op.drop_index("ix_fastbtc_in_chain_tx_id", table_name="fastbtc_in_transfer")
    op.drop_table("fastbtc_in_transfer")


class Uint256(types.TypeDecorator):
    MAX_UINT256 = 2**256 - 1
    impl = types.NUMERIC
    cache_ok = True

    def process_result_value(self, value, dialect):
        if value is not None:
            return self._coerce_and_validate_uint256(value)
        return None

    def process_bind_param(self, value, dialect):
        if isinstance(value, decimal.Decimal):
            return self._coerce_and_validate_uint256(value)
        return value

    def _coerce_and_validate_uint256(self, value):
        value = int(value)
        if value < 0 or value > self.MAX_UINT256:
            raise f"Value {value} is out of range for UINT256"
        return value


class TZDateTime(types.TypeDecorator):
    """
    A DateTime type which can only store tz-aware DateTimes.
    """

    # https://stackoverflow.com/a/62538441/5696586
    impl = types.DateTime(timezone=True)

    def process_bind_param(self, value, dialect):
        if isinstance(value, datetime.datetime) and value.tzinfo is None:
            raise ValueError(f"{value!r} must be TZ-aware")
        return value

    def __repr__(self):
        return "TZDateTime()"
