import argparse
import sys

from pyramid.paster import bootstrap, setup_logging
from pyramid.request import Request

from ..business_logic.bridge_transfer_updater import update_transfers_from_all_bridges


def parse_args(argv):
    parser = argparse.ArgumentParser()
    parser.add_argument(
        'config_uri',
        help='Configuration file, e.g., development.ini',
    )
    return parser.parse_args(argv[1:])


def main(argv=sys.argv):
    args = parse_args(argv)
    setup_logging(args.config_uri)
    env = bootstrap(args.config_uri)
    request: Request = env['request']
    session_factory = request.registry['dbsession_factory']

    update_transfers_from_all_bridges(
        transaction_manager=request.tm,
        session_factory=session_factory,
    )


if __name__ == '__main__':
    main()
