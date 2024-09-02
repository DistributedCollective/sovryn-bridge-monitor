"""bidi fastbtc replenisher pnl

Revision ID: c349734b0d55
Revises: a5fefd86fde0
Create Date: 2023-10-31 23:14:05.010205

"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "c349734b0d55"
down_revision = "a5fefd86fde0"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "bidi_fastbtc_replenisher_transaction",
        sa.Column("profit_calculation_id", sa.Integer(), nullable=True),
    )
    op.create_foreign_key(
        op.f(
            "fk_bidi_fastbtc_replenisher_transaction_profit_calculation_id_pnl_calculation"
        ),
        "bidi_fastbtc_replenisher_transaction",
        "pnl_calculation",
        ["profit_calculation_id"],
        ["id"],
    )


def downgrade():
    op.drop_constraint(
        op.f(
            "fk_bidi_fastbtc_replenisher_transaction_profit_calculation_id_pnl_calculation"
        ),
        "bidi_fastbtc_replenisher_transaction",
        type_="foreignkey",
    )
    op.drop_column("bidi_fastbtc_replenisher_transaction", "profit_calculation_id")
