"""value from wei to decimal

Revision ID: 166909696ec7
Revises: 5a319af140ea
Create Date: 2024-05-20 10:51:39.199589

"""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "166909696ec7"
down_revision = "5a319af140ea"
branch_labels = None
depends_on = None


def upgrade():
    op.alter_column("rsk_tx_trace", "block_n", new_column_name="block_number")
    op.alter_column("rsk_tx_info_old", "block_n", new_column_name="block_number")
    op.alter_column("rsk_address", "id", new_column_name="address_id")
    op.drop_constraint(
        "fk_rsk_tx_bookkeeper_address_id_rsk_address",
        "rsk_tx_bookkeeper",
        type_="foreignkey",
    )
    op.create_foreign_key(
        op.f("fk_rsk_tx_bookkeeper_address_id_rsk_address"),
        "rsk_tx_bookkeeper",
        "rsk_address",
        ["address_id"],
        ["address_id"],
    )
    op.drop_constraint(
        "fk_rsk_tx_info_address_id_rsk_address", "rsk_tx_info_old", type_="foreignkey"
    )
    op.drop_constraint("fk_block_info", "rsk_tx_info_old", type_="foreignkey")
    op.create_foreign_key(
        op.f("fk_rsk_tx_info_old_block_number_block_info"),
        "rsk_tx_info_old",
        "block_info",
        ["block_number", "chain_id"],
        ["block_number", "block_chain_id"],
    )
    op.create_foreign_key(
        op.f("fk_rsk_tx_info_old_address_id_rsk_address"),
        "rsk_tx_info_old",
        "rsk_address",
        ["address_id"],
        ["address_id"],
    )
    op.drop_constraint(
        "fk_rsk_tx_trace_block_n_block_info", "rsk_tx_trace", type_="foreignkey"
    )
    op.create_foreign_key(
        op.f("fk_rsk_tx_trace_block_number_block_info"),
        "rsk_tx_trace",
        "block_info",
        ["block_number", "chain_id"],
        ["block_number", "block_chain_id"],
    )
    op.alter_column(
        "rsk_tx_trace",
        "value",
        type_=sa.NUMERIC(precision=42, scale=18),
        postgresql_using="value::numeric(42, 18)/1e18",
    )


def downgrade():
    op.drop_constraint(
        op.f("fk_rsk_tx_trace_block_number_block_info"),
        "rsk_tx_trace",
        type_="foreignkey",
    )
    op.create_foreign_key(
        "fk_rsk_tx_trace_block_n_block_info",
        "rsk_tx_trace",
        "block_info",
        ["block_n", "chain_id"],
        ["block_number", "block_chain_id"],
    )
    op.drop_constraint(
        op.f("fk_rsk_tx_info_old_address_id_rsk_address"),
        "rsk_tx_info_old",
        type_="foreignkey",
    )
    op.drop_constraint(
        op.f("fk_rsk_tx_info_old_block_number_block_info"),
        "rsk_tx_info_old",
        type_="foreignkey",
    )
    op.create_foreign_key(
        "fk_block_info",
        "rsk_tx_info_old",
        "block_info",
        ["block_n", "chain_id"],
        ["block_number", "block_chain_id"],
    )
    op.create_foreign_key(
        "fk_rsk_tx_info_address_id_rsk_address",
        "rsk_tx_info_old",
        "rsk_address",
        ["address_id"],
        ["id"],
    )
    op.drop_constraint(
        op.f("fk_rsk_tx_bookkeeper_address_id_rsk_address"),
        "rsk_tx_bookkeeper",
        type_="foreignkey",
    )
    op.create_foreign_key(
        "fk_rsk_tx_bookkeeper_address_id_rsk_address",
        "rsk_tx_bookkeeper",
        "rsk_address",
        ["address_id"],
        ["id"],
    )
    op.alter_column(
        "rsk_tx_trace",
        "value",
        type_=sa.NUMERIC(precision=32),
        postgresql_using="value::numeric*1e18",
    )
    op.alter_column("rsk_address", "address_id", new_column_name="id")
    op.alter_column("rsk_tx_trace", "block_number", new_column_name="block_n")
    op.alter_column("rsk_tx_info_old", "block_number", new_column_name="block_n")
