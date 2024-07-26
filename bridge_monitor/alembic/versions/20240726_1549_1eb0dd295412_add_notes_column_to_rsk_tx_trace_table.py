"""add notes column to rsk_tx_trace table

Revision ID: 1eb0dd295412
Revises: d2922064cb3b
Create Date: 2024-07-26 15:49:45.309443

"""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "1eb0dd295412"
down_revision = "d2922064cb3b"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("rsk_tx_trace", sa.Column("notes", sa.Text(), nullable=True))


def downgrade():
    op.drop_column("rsk_tx_trace", "notes")
