"""bidi fastbtc replenisher transaction

Revision ID: a5fefd86fde0
Revises: f2ff024000b6
Create Date: 2023-10-31 22:10:38.694966

"""

import datetime
import decimal
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from sqlalchemy import types

# revision identifiers, used by Alembic.
revision = "a5fefd86fde0"
down_revision = "f2ff024000b6"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "bidi_fastbtc_replenisher_transaction",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("config_chain", sa.Text(), nullable=False),
        sa.Column("transaction_chain", sa.Text(), nullable=False),
        sa.Column("transaction_id", sa.Text(), nullable=True),
        sa.Column("block_number", sa.Integer(), nullable=True),
        sa.Column("block_timestamp", sa.Integer(), nullable=True),
        sa.Column("fee_satoshi", Uint256(), nullable=False),
        sa.Column("amount_satoshi", Uint256(), nullable=False),
        sa.Column("seen_on", TZDateTime(), nullable=False),
        sa.Column("updated_on", TZDateTime(), nullable=False),
        sa.Column(
            "raw_data",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default="{}",
            nullable=False,
        ),
        sa.PrimaryKeyConstraint(
            "id", name=op.f("pk_bidi_fastbtc_replenisher_transaction")
        ),
    )


def downgrade():
    op.drop_table("bidi_fastbtc_replenisher_transaction")


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
