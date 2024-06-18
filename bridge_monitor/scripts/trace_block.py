import argparse
import configparser
import sys
from decimal import Decimal
from itertools import groupby
from json import dumps
from typing import Sequence, List, Any, Optional
import time
import logging
from datetime import datetime, timezone, timedelta

import requests
import web3
from eth_utils import is_checksum_address, to_checksum_address

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session
from sqlalchemy.sql.expression import select, or_, and_
import sqlalchemy.sql.functions as sql_func
import sqlalchemy
from pyramid.paster import setup_logging

from ..models.rsk_transaction_info import (
    RskAddressBookkeeper,
    RskAddress,
    RskTxTrace,
)
from ..models.chain_info import BlockInfo, BlockChain
from ..business_logic.utils import get_web3

logger = logging.getLogger(__name__)


class Bookkeeper:
    """
    This class is responsible for scanning the RSK blockchain for transactions
    related to addresses specified in the database. Scanned values are placed in the rsk tx trace table.
    It scans up from the highest block number for a given address in the database and down from the lowest block number
    in the database. It also performs sanity checks, if the sanity check fails, it sends a message to a slack channel.
    """

    FIXED_SANITY_CHECK_INTERVAL = 3600

    def __init__(self, passed_web3: web3.Web3, engine: Engine):
        self.web3 = passed_web3
        self.db_engine = engine
        self.should_sanity_check = False
        self.traces_scanned_down = 0
        self.last_sanity_check = 0
        self.last_failed_sanity_check_time = datetime.fromtimestamp(0)

    @property
    def sanity_check_now(self):
        if self.last_sanity_check + self.FIXED_SANITY_CHECK_INTERVAL < time.time():
            self.last_sanity_check = time.time()
            return True

        if self.should_sanity_check:
            self.should_sanity_check = False
            self.traces_scanned_down = 0
            return True

        return False

    def add_address(
        self,
        *,
        address: str,
        name: str,
        initial_block: int,
        start: int = 1,
        end: Optional[int] = None,
    ):
        initial_block = max(initial_block, start)
        dbsession = Session(self.db_engine)
        with dbsession.begin():
            address_db_entry = (
                dbsession.query(RskAddress)
                .filter(RskAddress.address == address)
                .first()
            )
            if address_db_entry is None:
                logger.info("Address %s not found in db, creating entry", address)
                address_db_entry = RskAddress(address=address, name=name)
            else:
                logger.info(
                    "Address %s already exists in db with name %s",
                    address,
                    address_db_entry.name,
                )
            dbsession.add(address_db_entry)
            bookkeeper_db_entry = (
                dbsession.query(RskAddressBookkeeper)
                .filter(RskAddressBookkeeper.address == address_db_entry)
                .first()
            )
            if bookkeeper_db_entry is not None:
                logger.info("Address %s bookkeeper already exists", address)
                return
            dbsession.add(
                RskAddressBookkeeper(
                    address=address_db_entry,
                    start=start,
                    end=end,
                    lowest_scanned=initial_block,
                    next_to_scan_high=initial_block,
                )
            )

    def remove_address_bookkeeper(self, address: str, cascade: bool = False):
        logger.info("Removing address %s bookkeeper", address)
        dbsession = Session(self.db_engine)
        with dbsession.begin():
            address = (
                dbsession.query(RskAddress)
                .filter(RskAddress.address == address)
                .first()
            )
            if address is None:
                logger.info("Address %s not found in db, nothing to remove")
                return
            bookkeeper_db_entry = (
                dbsession.query(RskAddressBookkeeper)
                .filter(RskAddressBookkeeper.address == address)
                .first()
            )
            if bookkeeper_db_entry is None:
                logger.info(
                    "Address %s bookkeeper not found in db, nothing to remove",
                    address.address,
                )
                return
            dbsession.delete(bookkeeper_db_entry)
            if cascade:
                logger.info(
                    "Cascade delete enabled, removing address %s from rsk_address",
                    address,
                )
                dbsession.delete(address)

    def add_result_to_db(
        self,
        *,
        dbsession: Session,
        block_n: int,
        address_bookkeepers: Sequence[RskAddressBookkeeper],
        result: dict[str, list[dict]],
        block_info: BlockInfo,
        scanning_up: bool = True,
    ) -> None:
        try:
            dumps(result)
        except TypeError:
            logger.warning(
                "Traces cannot be serialized for block_n %d, skipping", block_n
            )
            raise ValueError("Traces cannot be serialized")
        if result:
            logger.info(
                "Found %d matching transactions in block %d", len(result), block_n
            )
        for tx_hash, traces in result.items():
            if not scanning_up:
                self.traces_scanned_down += 1
                if self.traces_scanned_down > 100:
                    self.should_sanity_check = True
            else:
                self.should_sanity_check = True
            trace_exists = dbsession.query(
                dbsession.query(RskTxTrace)
                .filter(RskTxTrace.tx_hash == tx_hash)
                .exists()
            ).scalar()
            if trace_exists:
                continue
            for trace_index, trace in enumerate(traces):
                assert trace.pop("blockNumber") == block_info.block_number

                trace = RskTxTrace(
                    tx_hash=trace.pop("transactionHash"),
                    unmapped=trace,
                    from_address=trace["action"].pop("from", ""),
                    to_address=trace["action"].pop("to", ""),
                    trace_index=trace_index,
                    value=trace["action"].pop("value", 0) / Decimal("1e18"),
                    block_info=block_info,
                    block_time=block_info.timestamp,
                    error=trace.pop("error", None),
                )

                dbsession.add(trace)
        if scanning_up:
            for bookkeeper in address_bookkeepers:
                bookkeeper.next_to_scan_high = block_n + 1
        else:
            for bookkeeper in address_bookkeepers:
                bookkeeper.lowest_scanned = block_n

    def scan_up(
        self,
        dbsession: Session,
        chain_id: int,
        safety_limit: int = 12,
    ) -> bool:
        current_block = self.web3.eth.block_number
        high_scan_rows = (
            dbsession.execute(
                select(RskAddressBookkeeper)
                .where(
                    and_(
                        RskAddressBookkeeper.next_to_scan_high + safety_limit
                        <= current_block,
                        or_(
                            RskAddressBookkeeper.end.is_(None),
                            RskAddressBookkeeper.end
                            > RskAddressBookkeeper.next_to_scan_high,
                        ),
                    )
                )
                .order_by(RskAddressBookkeeper.next_to_scan_high.asc())
                .fetch(1, with_ties=True)
            )
            .scalars()
            .all()
        )

        if not high_scan_rows:
            return False

        next_to_scan_high = high_scan_rows[0].next_to_scan_high

        block_info = self.get_or_create_block_info(
            dbsession, next_to_scan_high, chain_id
        )

        try:
            result = self.address_traces_in_block(next_to_scan_high, high_scan_rows)
            self.add_result_to_db(
                dbsession=dbsession,
                block_n=next_to_scan_high,
                address_bookkeepers=high_scan_rows,
                result=result,
                scanning_up=True,
                block_info=block_info,
            )
        except Exception:
            logger.exception("Error in scan_up")
            raise
        dbsession.flush()
        return True

    def scan_down(
        self,
        dbsession: Session,
        chain_id: int,
    ) -> bool:
        low_scan_rows = (
            dbsession.execute(
                select(RskAddressBookkeeper)
                .where(RskAddressBookkeeper.start < RskAddressBookkeeper.lowest_scanned)
                .order_by(RskAddressBookkeeper.lowest_scanned.desc())
                .fetch(1, with_ties=True)
            )
            .scalars()
            .all()
        )

        if not low_scan_rows:
            return False

        try:
            new_block_number = low_scan_rows[0].lowest_scanned - 1
            block_info = (
                dbsession.query(BlockInfo)
                .filter(
                    BlockInfo.block_chain_id == chain_id,
                    BlockInfo.block_number == new_block_number,
                )
                .one()
            )
            result = self.address_traces_in_block(new_block_number, low_scan_rows)
            self.add_result_to_db(
                dbsession=dbsession,
                block_n=new_block_number,
                address_bookkeepers=low_scan_rows,
                result=result,
                scanning_up=False,
                block_info=block_info,
            )
        except Exception:
            logger.exception("Error in scan_down")
            raise
        dbsession.flush()
        return True

    def get_or_create_block_info(
        self,
        dbsession: Session,
        block_n: int,
        chain_id: int,
    ):
        block_info = (
            dbsession.query(BlockInfo)
            .filter(
                and_(
                    BlockInfo.block_chain_id == chain_id,
                    BlockInfo.block_number == block_n,
                )
            )
            .first()
        )
        if block_info is None:
            block = self.web3.eth.get_block(block_n)
            block_info = BlockInfo(
                block_chain_id=chain_id,
                block_number=block_n,
                timestamp=datetime.fromtimestamp(block["timestamp"], tz=timezone.utc),
            )
            dbsession.add(block_info)
        return block_info

    def sanity_check_on_address(
        self,
        dbsession: Session,
        bk: RskAddressBookkeeper,
        config: configparser.ConfigParser,
        sensitivity: int = 100,
    ):
        def on_fail(st):
            logger.warning(
                "sanity check failed for: %s, with message: %s", bk.address.address, st
            )
            if (
                self.last_failed_sanity_check_time + timedelta(minutes=1)
                < datetime.now()
            ):
                return
            post_url = config.get("slack", "sanity_check_hook")
            if not post_url:
                return
            payload = {
                "username": "Trace table sanity check -bot",
                "icon_emoji": ":skull:",
                "blocks": [
                    {
                        "type": "header",
                        "text": {
                            "type": "plain_text",
                            "text": "RSK trace table sanity check failed",
                        },
                    },
                    {
                        "type": "section",
                        "text": {
                            "type": "mrkdwn",
                            "text": f"Address: {bk.address.address}\nMessage: {st}",
                        },
                    },
                ],
            }
            response = requests.post(post_url, json=payload)
            if response.status_code != 200:
                logger.warning(
                    "Failed to send slack message, status code: %d",
                    response.status_code,
                )
            self.last_failed_sanity_check_time = datetime.now()

        current_block = self.web3.eth.block_number

        if bk.start >= bk.lowest_scanned:
            if bk.next_to_scan_high < current_block - sensitivity:
                on_fail(f"fell behind by {current_block - bk.next_to_scan_high} blocks")

        bk_checksum_addr = to_checksum_address(bk.address.address)

        expected_value_delta = self.web3.eth.get_balance(
            bk_checksum_addr, bk.next_to_scan_high - 1
        ) - self.web3.eth.get_balance(bk_checksum_addr, bk.lowest_scanned - 1)

        expected_value_delta = Decimal(expected_value_delta) / Decimal("1e18")

        to_values = dbsession.execute(
            select(sql_func.sum(RskTxTrace.value)).where(
                and_(
                    RskTxTrace.to_address == bk.address.address,
                    RskTxTrace.error.is_(None),
                    RskTxTrace.block_number.between(
                        bk.lowest_scanned, bk.next_to_scan_high - 1
                    ),
                )
            )
        ).scalar()

        from_values = dbsession.execute(
            select(sql_func.sum(RskTxTrace.value)).where(
                and_(
                    RskTxTrace.from_address == bk.address.address,
                    RskTxTrace.error.is_(None),
                    RskTxTrace.block_number.between(
                        bk.lowest_scanned, bk.next_to_scan_high - 1
                    ),
                )
            )
        ).scalar()

        if to_values is None and from_values is None:
            logger.warning("sanity check returns None for both sums")
            return

        value_delta = to_values - from_values
        if expected_value_delta != value_delta:
            on_fail("value delta mismatch")
        logger.info(
            "sanity check complete for address %s, with deviation "
            + str(value_delta - expected_value_delta),
            bk.address.address,
        )

    def address_traces_in_block(
        self,
        block_n: int,
        included_rows: Sequence[RskAddressBookkeeper],
    ) -> dict[str, list[dict]]:
        if not included_rows:
            return {}
        if block_n < 1:
            return {}
        if block_n % 1000 == 0:
            logger.info("Scanning block %d", block_n)

        addr_set = set(bk.address.address for bk in included_rows)
        result = self.web3.tracing.trace_block(block_n)
        result = convert_to_json_serializable(result)
        result = groupby(result, lambda x: x["transactionHash"])

        ret_val = {}
        for tx_hash, tx in result:
            tx = list(tx)
            if any(trace["action"].get("from") in addr_set for trace in tx) or any(
                trace["action"].get("to") in addr_set for trace in tx
            ):
                ret_val[tx_hash] = tx
        return ret_val


def convert_to_json_serializable(obj: Any) -> Any:
    if isinstance(obj, bytes):
        return obj.hex()
    if isinstance(obj, dict) or isinstance(obj, web3.datastructures.AttributeDict):
        return {k: convert_to_json_serializable(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [convert_to_json_serializable(v) for v in obj]
    if isinstance(obj, str) and is_checksum_address(obj):
        return obj.lower()
    return obj


def parse_args(argv: Optional[List[str]] = None):
    parser = argparse.ArgumentParser()
    parser.add_argument("config_uri", help="Path to the config file")
    parser.add_argument(
        "-chain_env", default="local_node", help="Default is local node"
    )
    return parser.parse_args(argv[1:])


def main(argv: List[str]):
    if argv is None:
        argv = sys.argv
    args = parse_args(argv)
    setup_logging(args.config_uri)
    logger.info("Starting block tracing")
    config = configparser.ConfigParser()
    config.read(args.config_uri)
    db_url = config["app:main"]["sqlalchemy.url"]
    engine = create_engine(db_url)
    w3 = get_web3(args.chain_env)
    bookkeeper = Bookkeeper(w3, engine)
    dbsession = Session(engine)
    block_chain_meta = (
        dbsession.query(BlockChain).filter(BlockChain.name == "rsk").scalar()
    )
    if block_chain_meta is None:
        raise LookupError(
            "Block chain meta not found (maybe running import_block_meta_rsk will help)"
        )
    rsk_id = block_chain_meta.id
    try:
        latest_info_block_n = (
            dbsession.query(BlockInfo.block_number)
            .filter(BlockInfo.block_chain_id == rsk_id)
            .order_by(BlockInfo.block_number.desc())
            .limit(1)
            .one()
        ).block_number
    except sqlalchemy.exc.NoResultFound:
        latest_info_block_n = 1

    bookkeeper.add_address(
        address="0x1a8e78b41bc5ab9ebb6996136622b9b41a601b5c",
        name="fastbtc-out",
        initial_block=latest_info_block_n + 1,  # if less than start, will set to start
        start=5500000,
    )
    bookkeeper.add_address(
        address="0xe43cafbdd6674df708ce9dff8762af356c2b454d",
        name="fastbtc-in",
        initial_block=latest_info_block_n + 1,
        start=5074757,
    )

    while True:
        scanned_down = False
        try:
            for i in range(100):
                scanned_down = bookkeeper.scan_down(dbsession, chain_id=rsk_id)
                if not scanned_down:
                    break

            scanned_up = bookkeeper.scan_up(
                dbsession, chain_id=rsk_id, safety_limit=block_chain_meta.safe_limit
            )

            # logger.info("Committing")
            dbsession.commit()

            if not (scanned_down or scanned_up):
                time.sleep(1)

        except Exception:
            logger.exception("Error scanning")
            dbsession.rollback()
            time.sleep(10)

        try:
            if bookkeeper.sanity_check_now:
                all_bookkeepers = (
                    dbsession.execute(select(RskAddressBookkeeper)).scalars().all()
                )
                for bk in all_bookkeepers:
                    bookkeeper.sanity_check_on_address(dbsession, bk, config=config)

        except Exception:
            logger.exception("Error in sanity check")
            # maybe these should also send slack alerts


if __name__ == "__main__":
    main(sys.argv)
