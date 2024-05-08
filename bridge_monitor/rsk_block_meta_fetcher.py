from configparser import ConfigParser
import logging
import multiprocessing
from time import sleep
from functools import partial

import sqlalchemy.exc
from sqlalchemy.engine import Engine
from sqlalchemy import engine_from_config
from sqlalchemy.orm import Session

from .business_logic.utils import update_chain_info_rsk, RSK_META_FETCHER_SHORT_DELAY


logger = logging.getLogger(__name__)

def start_rsk_block_meta_fetcher(settings: dict) -> None:
    engine = engine_from_config(settings, prefix='sqlalchemy.')
    p = multiprocessing.Process(target=partial(rsk_block_meta_fetcher, engine, logger))
    p.start()


def rsk_block_meta_fetcher(engine: Engine, logger):
    logger.info("rsk_block_meta_fetcher started")
    prev_delay = 0
    with Session(engine) as session:
        while 1:
            try:
                prev_delay = update_chain_info_rsk(session,
                                                   seconds_per_iteration=prev_delay if prev_delay > 0 else RSK_META_FETCHER_SHORT_DELAY)
            except sqlalchemy.exc.IntegrityError:
                logger.warning("Attempted to push duplicate block info to the database")
                session.rollback()
                break
            except Exception:
                logger.exception("Error in update_chain_info_rsk")
                break
            sleep(1)

        logger.info("rsk_block_meta_fetcher stopped")
