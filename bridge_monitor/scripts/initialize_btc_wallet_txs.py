import logging
import argparse
import sys
import configparser
from pyramid.paster import setup_logging
from typing import List
from sqlalchemy.orm import Session
from sqlalchemy import create_engine

from ..rpc.rpc import get_wallet_transactions_from_block


logger = logging.getLogger(__name__)


def parse_args(argv):
    parser = argparse.ArgumentParser()
    parser.add_argument(
        'config_uri',
        help='Configuration file, e.g., development.ini',
    )
    parser.add_argument(
        "--wallet",
        help="wallet names to fetch data from",
        action="append"
    )

    return parser.parse_args(argv[1:])


def main(argv: List[str] | None=None):
    if argv is None:
        argv = sys.argv
    args = parse_args(argv)
    setup_logging(args.config_uri)

    config = configparser.ConfigParser()
    config.read(args.config_uri)
    db_url = config['app:main']['sqlalchemy.url']
    engine = create_engine(db_url)
    dbsession = Session(engine)
    logger.info("Initializing btc wallet txs into db")

    for wallet in args.wallet:
        logger.info("Initialisation for wallet %s", wallet)
        with dbsession.begin():
            get_wallet_transactions_from_block(dbsession, 0, wallet)


if __name__ == '__main__':
    main()
