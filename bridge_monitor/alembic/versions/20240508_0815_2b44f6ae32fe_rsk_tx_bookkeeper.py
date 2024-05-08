"""rsk_tx_bookkeeper

Revision ID: 2b44f6ae32fe
Revises: 3bb7baafa019
Create Date: 2024-05-08 08:15:19.787853

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '2b44f6ae32fe'
down_revision = '3bb7baafa019'
branch_labels = None
depends_on = None

def upgrade():
    op.create_table('rsk_address',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('address', sa.Text(), nullable=False),
    sa.Column('name', sa.Text(), nullable=True),
    sa.CheckConstraint('LOWER(address) = address', name=op.f('ck_rsk_address_lowercase_address')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_rsk_address')),
    sa.UniqueConstraint('address', name=op.f('uq_rsk_address_address'))
    )
    op.create_table('rsk_tx_bookkeeper',
    sa.Column('address_id', sa.Integer(), nullable=False),
    sa.Column('start', sa.Integer(), nullable=False),
    sa.Column('end', sa.Integer(), nullable=True),
    sa.Column('lowest_scanned', sa.Integer(), nullable=False),
    sa.Column('next_to_scan_high', sa.Integer(), nullable=False),
    sa.ForeignKeyConstraint(['address_id'], ['rsk_address.id'], name=op.f('fk_rsk_tx_bookkeeper_address_id_rsk_address')),
    sa.PrimaryKeyConstraint('address_id', name=op.f('pk_rsk_tx_bookkeeper'))
    )
    op.create_table('rsk_tx_info',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('address_id', sa.Integer(), nullable=False),
    sa.Column('tx_hash', sa.Text(), nullable=False),
    sa.Column('block_n', sa.Integer(), nullable=False),
    sa.ForeignKeyConstraint(['address_id'], ['rsk_address.id'], name=op.f('fk_rsk_tx_info_address_id_rsk_address')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_rsk_tx_info')),
    sa.UniqueConstraint('address_id', 'tx_hash', name='unique_tx')
    )

def downgrade():
    op.drop_table('rsk_tx_info')
    op.drop_table('rsk_tx_bookkeeper')
    op.drop_table('rsk_address')
