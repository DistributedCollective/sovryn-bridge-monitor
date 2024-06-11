"""bidirectional_fastbtc

Revision ID: 910ef6cf8776
Revises: ebcdf96488bf
Create Date: 2022-01-27 19:05:23.000947

"""

import datetime
import decimal

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
from sqlalchemy import types

revision = "910ef6cf8776"
down_revision = "ebcdf96488bf"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "bidi_fastbtc_transfer",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("chain", sa.Text(), nullable=False),
        sa.Column("transfer_id", sa.Text(), nullable=False),
        sa.Column("rsk_address", sa.Text(), nullable=False),
        sa.Column("bitcoin_address", sa.Text(), nullable=False),
        sa.Column("total_amount_satoshi", Uint256(), nullable=False),
        sa.Column("net_amount_satoshi", Uint256(), nullable=False),
        sa.Column("fee_satoshi", Uint256(), nullable=False),
        sa.Column(
            "status",
            sa.Enum(
                "NOT_APPLICABLE",
                "NEW",
                "SENDING",
                "MINED",
                "REFUNDED",
                "RECLAIMED",
                "INVALID",
                name="bidi_fastbtc_transferstatus",
            ),
            nullable=False,
        ),
        sa.Column("bitcoin_tx_id", sa.Text(), nullable=True),
        sa.Column("ignored", sa.Boolean(), nullable=False),
        sa.Column("event_block_number", sa.Integer(), nullable=False),
        sa.Column("event_block_hash", sa.Text(), nullable=False),
        sa.Column("event_block_timestamp", sa.Integer(), nullable=False),
        sa.Column("event_transaction_hash", sa.Text(), nullable=False),
        sa.Column("event_log_index", sa.Integer(), nullable=False),
        sa.Column("transfer_batch_size", sa.Integer(), nullable=True),
        sa.Column("marked_as_sending_transaction_hash", sa.Text(), nullable=True),
        sa.Column("marked_as_sending_block_hash", sa.Text(), nullable=True),
        sa.Column("marked_as_sending_block_number", sa.Integer(), nullable=True),
        sa.Column("marked_as_sending_block_timestamp", sa.Integer(), nullable=True),
        sa.Column("marked_as_sending_log_index", sa.Integer(), nullable=True),
        sa.Column("marked_as_mined_transaction_hash", sa.Text(), nullable=True),
        sa.Column("marked_as_mined_block_hash", sa.Text(), nullable=True),
        sa.Column("marked_as_mined_block_number", sa.Integer(), nullable=True),
        sa.Column("marked_as_mined_block_timestamp", sa.Integer(), nullable=True),
        sa.Column("marked_as_mined_log_index", sa.Integer(), nullable=True),
        sa.Column("refunded_or_reclaimed_transaction_hash", sa.Text(), nullable=True),
        sa.Column("refunded_or_reclaimed_block_hash", sa.Text(), nullable=True),
        sa.Column("refunded_or_reclaimed_block_number", sa.Integer(), nullable=True),
        sa.Column("refunded_or_reclaimed_block_timestamp", sa.Integer(), nullable=True),
        sa.Column("refunded_or_reclaimed_log_index", sa.Integer(), nullable=True),
        sa.Column("seen_on", TZDateTime(), nullable=False),
        sa.Column("updated_on", TZDateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_bidi_fastbtc_transfer")),
    )
    op.create_index(
        op.f("ix_bidi_fastbtc_transfer_event_block_timestamp"),
        "bidi_fastbtc_transfer",
        ["event_block_timestamp"],
        unique=False,
    )
    op.create_index(
        "ix_chain_transfer_id",
        "bidi_fastbtc_transfer",
        ["chain", "transfer_id"],
        unique=False,
    )


def downgrade():
    op.drop_index("ix_chain_transfer_id", table_name="bidi_fastbtc_transfer")
    op.drop_index(
        op.f("ix_bidi_fastbtc_transfer_event_block_timestamp"),
        table_name="bidi_fastbtc_transfer",
    )
    op.drop_table("bidi_fastbtc_transfer")
    op.execute("DROP TYPE bidi_fastbtc_transferstatus")


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
