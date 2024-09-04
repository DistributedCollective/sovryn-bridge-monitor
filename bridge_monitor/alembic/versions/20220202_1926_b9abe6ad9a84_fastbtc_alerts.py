"""fastbtc_alerts

Revision ID: b9abe6ad9a84
Revises: 910ef6cf8776
Create Date: 2022-02-02 19:26:13.887875

"""

from alembic import op


# revision identifiers, used by Alembic.
revision = "b9abe6ad9a84"
down_revision = "910ef6cf8776"
branch_labels = None
depends_on = None


def upgrade():
    conn = op.get_bind()
    current_values = (
        conn.execute("SELECT unnest(enum_range(null::alerttype));").scalars().all()
    )
    if "bidi_fastbtc_late_transfers" not in current_values:
        op.execute(
            """ALTER TYPE alerttype ADD VALUE 'bidi_fastbtc_late_transfers' after 'late_transfers'"""
        )


def downgrade():
    # Looks like this cannot be downgraded, see https://www.postgresql.org/docs/14/sql-altertype.html
    pass
