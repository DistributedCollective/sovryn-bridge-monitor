"""ignored_flag

Revision ID: 4bf7b1eba272
Revises: 1fccc3c8d962
Create Date: 2021-09-27 15:10:44.508248

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '4bf7b1eba272'
down_revision = '1fccc3c8d962'
branch_labels = None
depends_on = None

def upgrade():
    op.add_column('transfer', sa.Column('ignored', sa.Boolean(), nullable=False, server_default='false'))

def downgrade():
    op.drop_column('transfer', 'ignored')
