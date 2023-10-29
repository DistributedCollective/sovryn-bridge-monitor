"""pnl

Revision ID: 73a34359a345
Revises: a8677868193a
Create Date: 2023-10-29 23:05:24.471308

"""
import datetime
from alembic import op
import sqlalchemy as sa
from sqlalchemy import types


# revision identifiers, used by Alembic.
revision = '73a34359a345'
down_revision = 'a8677868193a'
branch_labels = None
depends_on = None

def upgrade():
    op.create_table('pnl_calculation',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('service', sa.Text(), nullable=False),
    sa.Column('config_chain', sa.Text(), nullable=False),
    sa.Column('timestamp', TZDateTime(), nullable=False),
    sa.Column('volume_btc', sa.Numeric(), nullable=False),
    sa.Column('gross_profit_btc', sa.Numeric(), nullable=False),
    sa.Column('cost_btc', sa.Numeric(), nullable=False),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_pnl_calculation'))
    )
    op.create_table('pnl_transaction',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('profit_calculation_id', sa.Integer(), nullable=False),
    sa.Column('cost_btc', sa.Numeric(), nullable=False),
    sa.Column('transaction_chain', sa.Text(), nullable=False),
    sa.Column('transaction_id', sa.Text(), nullable=False),
    sa.Column('timestamp', TZDateTime(), nullable=False),
    sa.Column('block_number', sa.Integer(), nullable=True),
    sa.Column('comment', sa.Text(), nullable=False, default="", server_default=""),
    sa.ForeignKeyConstraint(['profit_calculation_id'], ['pnl_calculation.id'], name=op.f('fk_pnl_transaction_profit_calculation_id_pnl_calculation')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_pnl_transaction'))
    )
    op.add_column('bidi_fastbtc_transfer', sa.Column('profit_calculation_id', sa.Integer(), nullable=True))
    op.create_foreign_key(op.f('fk_bidi_fastbtc_transfer_profit_calculation_id_pnl_calculation'), 'bidi_fastbtc_transfer', 'pnl_calculation', ['profit_calculation_id'], ['id'])

def downgrade():
    op.drop_constraint(op.f('fk_bidi_fastbtc_transfer_profit_calculation_id_pnl_calculation'), 'bidi_fastbtc_transfer', type_='foreignkey')
    op.drop_column('bidi_fastbtc_transfer', 'profit_calculation_id')
    op.drop_table('pnl_transaction')
    op.drop_table('pnl_calculation')


class TZDateTime(types.TypeDecorator):
    """
    A DateTime type which can only store tz-aware DateTimes.
    """
    # https://stackoverflow.com/a/62538441/5696586
    impl = types.DateTime(timezone=True)

    def process_bind_param(self, value, dialect):
        if isinstance(value, datetime.datetime) and value.tzinfo is None:
            raise ValueError(f'{value!r} must be TZ-aware')
        return value

    def __repr__(self):
        return 'TZDateTime()'
