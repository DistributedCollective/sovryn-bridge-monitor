from configparser import ConfigParser
import logging
import multiprocessing
from time import sleep
from functools import partial

from sqlalchemy.engine import Engine
from sqlalchemy import engine_from_config
from sqlalchemy.orm import Session

from .business_logic.utils import update_chain_info_rsk, RSK_META_FETCHER_LONG_DELAY, RSK_META_FETCHER_SHORT_DELAY


logger = logging.getLogger(__name__)

def start_rsk_block_meta_fetcher(settings: dict) -> None:
    engine = engine_from_config(settings, prefix='sqlalchemy.')
    p = multiprocessing.Process(target=partial(rsk_block_meta_fetcher, engine, logger))
    p.start()
    logger.info("rsk_block_meta_fetcher started")


def rsk_block_meta_fetcher(engine: Engine, logger):
    prev_delay = 0
    with Session(engine) as session:
        while 1:
            try:
                prev_delay = update_chain_info_rsk(session,
                                                   seconds_per_iteration=prev_delay if prev_delay > 0 else RSK_META_FETCHER_SHORT_DELAY)
            except Exception:
                logger.exception("Error in update_chain_info_rsk")
                break
            sleep(1)



