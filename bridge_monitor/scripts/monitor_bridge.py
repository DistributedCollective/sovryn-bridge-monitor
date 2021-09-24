import logging
import argparse
import sys
import time

from pyramid.paster import bootstrap, setup_logging
from pyramid.request import Request

from ..business_logic.bridge_transfer_updater import update_transfers_from_all_bridges


logger = logging.getLogger(__name__)


def parse_args(argv):
    parser = argparse.ArgumentParser()
    parser.add_argument(
        'config_uri',
        help='Configuration file, e.g., development.ini',
    )
    parser.add_argument(
        '--max-blocks',
        type=int,
        required=False,
        default=None,
        help='Max blocks to process at time. 0 = no maximum',
    )
    parser.add_argument(
        '--sleep',
        type=int,
        required=False,
        default=120,
        help='Sleep seconds between iterations',
    )
    parser.add_argument(
        '--one-off',
        action='store_true',
        default=False,
        help='One-off operation, don\'t enter infinite loop',
    )
    return parser.parse_args(argv[1:])


def main(argv=sys.argv):
    args = parse_args(argv)
    setup_logging(args.config_uri)
    env = bootstrap(args.config_uri)
    request: Request = env['request']
    session_factory = request.registry['dbsession_factory']

    # TODO: limit 1 session at time
    while True:
        try:
            update_transfers_from_all_bridges(
                transaction_manager=request.tm,
                session_factory=session_factory,
                max_blocks=args.max_blocks,
            )
        except KeyboardInterrupt:
            logger.info("Quitting!")
            return
        except Exception as e:
            logger.exception("Got exception monitoring bridge")
        if args.one_off:
            return
        time.sleep(args.sleep)


if __name__ == '__main__':
    main()
