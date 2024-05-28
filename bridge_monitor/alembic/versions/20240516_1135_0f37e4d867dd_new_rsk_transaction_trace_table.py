"""new rsk transaction trace table

Revision ID: 0f37e4d867dd
Revises: 2e050a65e092
Create Date: 2024-05-16 11:35:15.474156

"""

from alembic import op


# revision identifiers, used by Alembic.
revision = "0f37e4d867dd"
down_revision = "2e050a65e092"
branch_labels = None
depends_on = None


def upgrade():
    op.rename_table("rsk_tx_info", "rsk_tx_info_old")


def downgrade():
    op.rename_table("rsk_tx_info_old", "rsk_tx_info")
