"""depositor_address

Revision ID: fb39261e0d00
Revises: b143b64592f2
Create Date: 2021-09-27 10:14:17.259324

"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "fb39261e0d00"
down_revision = "b143b64592f2"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("transfer", sa.Column("depositor_address", sa.Text(), nullable=False))


def downgrade():
    op.drop_column("transfer", "depositor_address")
