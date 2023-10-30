"""fastbtc-in-pnl

Revision ID: f2ff024000b6
Revises: 73a34359a345
Create Date: 2023-10-30 02:38:47.102262

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'f2ff024000b6'
down_revision = '73a34359a345'
branch_labels = None
depends_on = None

def upgrade():
    op.add_column('fastbtc_in_transfer', sa.Column('profit_calculation_id', sa.Integer(), nullable=True))
    op.create_foreign_key(op.f('fk_fastbtc_in_transfer_profit_calculation_id_pnl_calculation'), 'fastbtc_in_transfer', 'pnl_calculation', ['profit_calculation_id'], ['id'])

def downgrade():
    op.drop_constraint(op.f('fk_fastbtc_in_transfer_profit_calculation_id_pnl_calculation'), 'fastbtc_in_transfer', type_='foreignkey')
    op.drop_column('fastbtc_in_transfer', 'profit_calculation_id')
