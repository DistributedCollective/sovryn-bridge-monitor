import logging
import argparse
import sys
import time
from datetime import timedelta

from pyramid.paster import bootstrap, setup_logging
from pyramid.request import Request

from ..business_logic.bridge_transfer_updater import update_transfers_from_all_bridges
from ..business_logic.bridge_alerts import handle_bridge_alerts


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
    parser.add_argument(
        '--no-updates',
        action='store_true',
        default=False,
        help="Don't update transfers",
    )
    parser.add_argument(
        '--no-alerts',
        action='store_true',
        default=False,
        help="Don't send alerts",
    )
    parser.add_argument(
        '--alert-interval-minutes',
        type=int,
        help="Send new alerts only every N minutes",
    )
    parser.add_argument(
        '--update-last-processed-blocks-first',
        action='store_true',
        default=False,
        help="Update last processed blocks from DB first (developers only)",
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
        if not args.no_updates:
            try:
                update_transfers_from_all_bridges(
                    transaction_manager=request.tm,
                    session_factory=session_factory,
                    max_blocks=args.max_blocks,
                    update_last_processed_blocks_first=args.update_last_processed_blocks_first,
                )
            except KeyboardInterrupt:
                logger.info("Quitting!")
                raise
            except Exception:  # noqa
                logger.exception("Got exception getting bridge transfers")

        if not args.no_alerts:
            extra_args = {}
            if args.alert_interval_minutes is not None:
                extra_args['alert_interval'] = timedelta(minutes=args.alert_interval_minutes)
            try:
                handle_bridge_alerts(
                    transaction_manager=request.tm,
                    session_factory=session_factory,
                    **extra_args,
                )
            except KeyboardInterrupt:
                logger.info("Quitting!")
                raise
            except Exception:  # noqa
                logger.exception("Got exception sending alerts")

        if args.one_off:
            return

        logger.info("Monitoring round done, sleeping a while.")
        time.sleep(args.sleep)


if __name__ == '__main__':
    main()
