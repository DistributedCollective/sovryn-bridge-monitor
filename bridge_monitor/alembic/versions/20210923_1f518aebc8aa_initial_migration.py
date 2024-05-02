"""initial_migration

Revision ID: 1f518aebc8aa
Revises:
Create Date: 2021-09-23 13:37:37.099489

"""
import decimal

import sqlalchemy as sa
from alembic import op
from sqlalchemy import types
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '1f518aebc8aa'
down_revision = None
branch_labels = None
depends_on = None

def upgrade():
    op.create_table('key_value_pair',
    sa.Column('key', sa.Text(), nullable=False),
    sa.Column('value', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    sa.PrimaryKeyConstraint('key', name=op.f('pk_key_value_pair'))
    )
    op.create_table('transfer',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('from_chain', sa.Text(), nullable=False),
    sa.Column('to_chain', sa.Text(), nullable=False),
    sa.Column('transaction_id', sa.Text(), nullable=False),
    sa.Column('transaction_id_old', sa.Text(), nullable=False),
    sa.Column('was_processed', sa.Boolean(), nullable=False),
    sa.Column('num_votes', sa.Integer(), nullable=False),
    sa.Column('receiver_address', sa.Text(), nullable=False),
    sa.Column('token_address', sa.Text(), nullable=False),
    sa.Column('token_symbol', sa.Text(), nullable=False),
    sa.Column('token_decimals', sa.Integer(), nullable=False),
    sa.Column('amount_wei', Uint256(), nullable=False),
    sa.Column('user_data', sa.Text(), nullable=False),
    sa.Column('event_block_number', sa.Integer(), nullable=False),
    sa.Column('event_block_hash', sa.Text(), nullable=False),
    sa.Column('event_transaction_hash', sa.Text(), nullable=False),
    sa.Column('event_log_index', sa.Integer(), nullable=False),
    sa.Column('executed_transaction_hash', sa.Text(), nullable=True),
    sa.Column('executed_block_hash', sa.Text(), nullable=True),
    sa.Column('executed_block_number', sa.Integer(), nullable=True),
    sa.Column('executed_log_index', sa.Integer(), nullable=True),
    sa.Column('has_error_token_receiver_events', sa.Boolean(), nullable=False),
    sa.Column('error_data', sa.Text(), nullable=False),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_transfer'))
    )
    op.create_index(op.f('ix_transfer_transaction_id'), 'transfer', ['transaction_id'], unique=False)


def downgrade():
    op.drop_index(op.f('ix_transfer_transaction_id'), table_name='transfer')
    op.drop_table('transfer')
    op.drop_table('key_value_pair')


class Uint256(types.TypeDecorator):
    MAX_UINT256 = 2 ** 256 - 1
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
            raise f'Value {value} is out of range for UINT256'
        return value
