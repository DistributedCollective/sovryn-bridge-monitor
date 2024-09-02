"""fastbtc_in_alerttype

Revision ID: a8677868193a
Revises: ddc43b246af0
Create Date: 2023-06-19 15:55:57.357824

"""

from alembic import op


# revision identifiers, used by Alembic.
revision = "a8677868193a"
down_revision = "ddc43b246af0"
branch_labels = None
depends_on = None


def upgrade():
    conn = op.get_bind()
    current_values = (
        conn.execute("SELECT unnest(enum_range(null::alerttype));").scalars().all()
    )
    if "fastbtc_in_late_transfers" not in current_values:
        op.execute(
            """ALTER TYPE alerttype ADD VALUE 'fastbtc_in_late_transfers' after 'bidi_fastbtc_late_transfers'"""
        )


def downgrade():
    pass
