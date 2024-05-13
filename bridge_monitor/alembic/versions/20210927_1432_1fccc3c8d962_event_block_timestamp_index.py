"""event_block_timestamp_index

Revision ID: 1fccc3c8d962
Revises: ee8ba2921a34
Create Date: 2021-09-27 14:32:53.354673

"""

from alembic import op


# revision identifiers, used by Alembic.
revision = "1fccc3c8d962"
down_revision = "ee8ba2921a34"
branch_labels = None
depends_on = None


def upgrade():
    op.create_index(
        op.f("ix_transfer_event_block_timestamp"),
        "transfer",
        ["event_block_timestamp"],
        unique=False,
    )


def downgrade():
    op.drop_index(op.f("ix_transfer_event_block_timestamp"), table_name="transfer")
