"""timestamps

Revision ID: b143b64592f2
Revises: 1f518aebc8aa
Create Date: 2021-09-24 09:29:30.005717

"""
import datetime
from alembic import op
import sqlalchemy as sa
from sqlalchemy import types


# revision identifiers, used by Alembic.
revision = 'b143b64592f2'
down_revision = '1f518aebc8aa'
branch_labels = None
depends_on = None

def upgrade():
    op.add_column('transfer', sa.Column('created_on', TZDateTime(), nullable=False))
    op.add_column('transfer', sa.Column('updated_on', TZDateTime(), nullable=False))

def downgrade():
    op.drop_column('transfer', 'updated_on')
    op.drop_column('transfer', 'created_on')


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
