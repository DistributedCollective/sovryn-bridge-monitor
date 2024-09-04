import logging
import argparse
import os
import sys
import time
from datetime import timedelta

from pyramid.paster import bootstrap, setup_logging
from pyramid.request import Request

from bridge_monitor.business_logic.bidirectional_fastbtc_alerts import (
    handle_bidi_fastbtc_alerts,
)
from bridge_monitor.business_logic.fastbtc_in import update_fastbtc_in_transfers
from bridge_monitor.business_logic.replenisher import scan_replenisher_transactions
from ..business_logic.bridge_transfer_updater import update_transfers_from_all_bridges
from ..business_logic.bridge_alerts import handle_bridge_alerts
from ..business_logic.bidirectional_fastbtc import update_bidi_fastbtc_transfers
from ..business_logic.fastbtc_in_alerts import handle_fastbtc_in_alerts
from ..business_logic.pnl import PnLService


logger = logging.getLogger(__name__)


def parse_args(argv):
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "config_uri",
        help="Configuration file, e.g., development.ini",
    )
    parser.add_argument(
        "--max-blocks",
        type=int,
        required=False,
        default=None,
        help="Max blocks to process at time. 0 = no maximum",
    )
    parser.add_argument(
        "--sleep",
        type=int,
        required=False,
        default=120,
        help="Sleep seconds between iterations",
    )
    parser.add_argument(
        "--one-off",
        action="store_true",
        default=False,
        help="One-off operation, don't enter infinite loop",
    )
    parser.add_argument(
        "--no-updates",
        action="store_true",
        default=False,
        help="Don't update transfers",
    )
    parser.add_argument(
        "--no-alerts",
        action="store_true",
        default=False,
        help="Don't send alerts",
    )
    parser.add_argument(
        "--alert-interval-minutes",
        type=int,
        help="Send new alerts only every N minutes",
    )
    parser.add_argument(
        "--discord-webhook-url",
        type=str,
        required=False,
        help="Discord webhook url for alerts. Can also be specified with env var DISCORD_WEBHOOK_URL",
    )
    parser.add_argument(
        "--bidi-fastbtc-discord-webhook-url",
        type=str,
        required=False,
        help="Discord webhook url for alerts (bidi fastbtc). Can also be specified with env var DISCORD_WEBHOOK_URL_FASTBTC",
    )
    parser.add_argument(
        "--update-last-processed-blocks-first",
        action="store_true",
        default=False,
        help="Update last processed blocks from DB first (developers only)",
    )

    parser.add_argument(
        "--no-fastbtc",
        action="store_true",
        default=False,
        help="Don't monitor bidirectional FastBTC",
    )
    parser.add_argument(
        "--no-fastbtc-in",
        action="store_true",
        default=False,
        help="Don't monitor FastBTC-in",
    )
    parser.add_argument(
        "--no-bridge",
        action="store_true",
        default=False,
        help="Only monitor (bidirectional) FastBTC - no token bridge",
    )
    parser.add_argument(
        "--no-replenisher",
        action="store_true",
        default=False,
        help="Don't update fastbtc replenisher transactions",
    )
    parser.add_argument(
        "--no-pnl",
        action="store_true",
        default=False,
        help="Don't update profit-and-loss calculations",
    )

    return parser.parse_args(argv[1:])


def main(argv=sys.argv):
    args = parse_args(argv)
    setup_logging(args.config_uri)
    env = bootstrap(args.config_uri)
    request: Request = env["request"]
    session_factory = request.registry["dbsession_factory"]

    chain_env = request.registry.get("chain_env", "unset")
    if chain_env == "unset":
        logger.warning("chain_env not set in config, defaulting to mainnet")
        chain_env = "mainnet"

    logger.info("chain_env: %s", chain_env)

    discord_webhook_url = args.discord_webhook_url or os.getenv("DISCORD_WEBHOOK_URL")
    bidi_fastbtc_discord_webhook_url = (
        args.bidi_fastbtc_discord_webhook_url
        or os.getenv("DISCORD_WEBHOOK_URL_FASTBTC")
        or discord_webhook_url
    )

    # TODO: limit 1 session at time
    while True:
        if not args.no_updates:
            if not args.no_bridge:
                try:
                    update_transfers_from_all_bridges(
                        transaction_manager=request.tm,
                        session_factory=session_factory,
                        max_blocks=args.max_blocks,
                        update_last_processed_blocks_first=args.update_last_processed_blocks_first,
                        chain_env=chain_env,
                    )
                except KeyboardInterrupt:
                    logger.info("Quitting!")
                    raise
                except Exception:  # noqa
                    logger.exception("Got exception getting bridge transfers")

            if not args.no_fastbtc:
                try:
                    update_bidi_fastbtc_transfers(
                        config_name=f"rsk_{chain_env}",
                        transaction_manager=request.tm,
                        session_factory=session_factory,
                        max_blocks=args.max_blocks,
                    )
                except KeyboardInterrupt:
                    logger.info("Quitting!")
                    raise
                except Exception:  # noqa
                    logger.exception("Got exception getting bridge transfers")

            if not args.no_fastbtc_in:
                try:
                    update_fastbtc_in_transfers(
                        config_name=f"rsk_{chain_env}",
                        transaction_manager=request.tm,
                        session_factory=session_factory,
                        max_blocks=args.max_blocks,
                    )
                except KeyboardInterrupt:
                    logger.info("Quitting!")
                    raise
                except Exception:  # noqa
                    logger.exception("Got exception getting bridge transfers")

        if not args.no_alerts:
            extra_args = {}
            if args.alert_interval_minutes is not None:
                extra_args["alert_interval"] = timedelta(
                    minutes=args.alert_interval_minutes
                )
            try:
                handle_bridge_alerts(
                    transaction_manager=request.tm,
                    session_factory=session_factory,
                    discord_webhook_url=discord_webhook_url,
                    **extra_args,
                )
            except KeyboardInterrupt:
                logger.info("Quitting!")
                raise
            except Exception:  # noqa
                logger.exception("Got exception sending bridge alerts")

            try:
                handle_bidi_fastbtc_alerts(
                    transaction_manager=request.tm,
                    session_factory=session_factory,
                    discord_webhook_url=bidi_fastbtc_discord_webhook_url,
                    **extra_args,
                )
            except KeyboardInterrupt:
                logger.info("Quitting!")
                raise
            except Exception:  # noqa
                logger.exception("Got exception sending bidi fastbtc alerts")

            try:
                handle_fastbtc_in_alerts(
                    transaction_manager=request.tm,
                    session_factory=session_factory,
                    discord_webhook_url=bidi_fastbtc_discord_webhook_url,
                    **extra_args,
                )
            except KeyboardInterrupt:
                logger.info("Quitting!")
                raise
            except Exception:  # noqa
                logger.exception("Got exception sending fastbtc-in alerts")

        if not args.no_replenisher:
            try:
                scan_replenisher_transactions(
                    chain_env=chain_env,
                    session_factory=session_factory,
                    transaction_manager=request.tm,
                )
            except KeyboardInterrupt:
                logger.info("Quitting!")
                raise
            except Exception:  # noqa
                logger.exception("Got exception scanning replenisher transactions")

        if not args.no_pnl:
            try:
                pnl_service = PnLService(
                    transaction_manager=request.tm,
                    session_factory=session_factory,
                )
                pnl_service.update_pnl()
            except KeyboardInterrupt:
                logger.info("Quitting!")
                raise
            except Exception:
                logger.exception("Got exception updating PnL")

        if args.one_off:
            return

        logger.info("Monitoring round done, sleeping a while.")
        time.sleep(args.sleep)


if __name__ == "__main__":
    main()
