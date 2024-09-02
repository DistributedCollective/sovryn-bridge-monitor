"""event_block_timestamp

Revision ID: ee8ba2921a34
Revises: fb39261e0d00
Create Date: 2021-09-27 12:50:59.270668

"""

import functools
import logging
import os
import time

import sqlalchemy as sa
from alembic import op
from sqlalchemy.ext.automap import automap_base
from sqlalchemy.orm import Session

from bridge_monitor.business_logic.utils import get_web3

revision = "ee8ba2921a34"
down_revision = "fb39261e0d00"
branch_labels = None
depends_on = None

logger = logging.getLogger(__name__)


@functools.lru_cache()
def get_web3_cached(chain_name):
    return get_web3(chain_name)


@functools.lru_cache()
def get_block_timestamp(chain_name, block_hash) -> int:
    web3 = get_web3_cached(chain_name)
    attempts = 5
    while True:
        attempts -= 1
        try:
            block = web3.eth.get_block(block_hash)
            break
        except Exception:  # noqa
            if attempts <= 0:
                raise
            logger.exception("error")
            time.sleep(1)
    return block.timestamp


Base = automap_base()


def upgrade():
    op.add_column(
        "transfer", sa.Column("event_block_timestamp", sa.Integer(), nullable=True)
    )
    op.add_column(
        "transfer", sa.Column("executed_block_timestamp", sa.Integer(), nullable=True)
    )

    # Reflect the ORM model like it's in the database right now in the migration
    bind = op.get_bind()
    Base.prepare(autoload_with=bind)
    Transfer = Base.classes.transfer

    dbsession = Session(bind=bind)
    with dbsession:
        transfers = dbsession.query(Transfer).all()
        if transfers:
            logger.info(
                "There are existing transfers -- setting timestamps for existing transfers"
            )
            if not os.getenv("INFURA_API_KEY"):
                raise Exception(
                    "INFURA_API_KEY must be set for the data migration to be run"
                )

            def set_transfer_timestamps(args):
                i, transfer = args
                logger.info(
                    "%s / %s: %.2f %%", i, len(transfers), i / len(transfers) * 100
                )
                if not transfer.event_block_timestamp:
                    transfer.event_block_timestamp = get_block_timestamp(
                        transfer.from_chain, transfer.event_block_hash
                    )
                if (
                    transfer.executed_block_hash
                    and not transfer.executed_block_timestamp
                ):
                    transfer.executed_block_timestamp = get_block_timestamp(
                        transfer.to_chain, transfer.executed_block_hash
                    )
                return transfer

            # with ThreadPoolExecutor(max_workers=4) as executor:
            #    transfer_futures = executor.map(set_transfer_timestamps, enumerate(transfers))
            # transfers = list(transfer_futures)
            for i, transfer in enumerate(transfers, start=1):
                set_transfer_timestamps((i, transfer))

            dbsession.add_all(transfers)
            dbsession.commit()
        else:
            logger.info("No existing transfers -- the data migration needs not be run")

    op.alter_column("transfer", "event_block_timestamp", nullable=False)


def downgrade():
    op.drop_column("transfer", "event_block_timestamp")
    op.drop_column("transfer", "executed_block_timestamp")
