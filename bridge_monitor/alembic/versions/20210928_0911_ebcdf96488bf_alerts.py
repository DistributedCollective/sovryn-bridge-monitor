"""alerts

Revision ID: ebcdf96488bf
Revises: 4bf7b1eba272
Create Date: 2021-09-28 09:11:45.183917

"""

from alembic import op
import sqlalchemy as sa
import datetime


# revision identifiers, used by Alembic.
from sqlalchemy import types

revision = "ebcdf96488bf"
down_revision = "4bf7b1eba272"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "alert",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column(
            "type", sa.Enum("late_transfers", "other", name="alerttype"), nullable=False
        ),
        sa.Column("created_on", TZDateTime(), nullable=False),
        sa.Column("last_message_sent_on", TZDateTime(), nullable=False),
        sa.Column("resolved", sa.Boolean(), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_alert")),
    )


def downgrade():
    op.drop_table("alert")
    op.execute("DROP TYPE alerttype;")


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
