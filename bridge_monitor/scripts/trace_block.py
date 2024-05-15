import argparse
import configparser
import sys
from collections import defaultdict
from itertools import cycle
from json import dumps
from typing import Sequence, List, Any
import time
import logging
from datetime import datetime, timezone
import web3
from eth_utils import is_checksum_address

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session
from sqlalchemy.sql.expression import select, or_, and_
import sqlalchemy
from pyramid.paster import setup_logging
from ..models.rsk_transaction_info import (
    RskAddressBookkeeper,
    RskAddress,
    RskTransactionInfo,
)
from ..models.chain_info import BlockInfo, BlockChain

logger = logging.getLogger(__name__)


class Bookkeeper:
    def __init__(self, passed_web3: web3.Web3, engine: Engine):
        self.web3 = passed_web3
        self.db_engine = engine

    def add_address(
        self,
        *,
        address: str,
        name: str,
        initial_block: int,
        start: int = 1,
        end: int | None = None,
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
                    "Address %s alread exists in db with name %s",
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
        included_rows: Sequence[RskAddressBookkeeper],
        result: dict,
        block_info: BlockInfo,
        scanning_up: bool = True,
    ) -> None:
        if result:
            logger.info(
                "Found %d matching transactions in block %d", len(result), block_n
            )
        for addr_and_tx_hash, traces in result.items():
            addr = addr_and_tx_hash[0]
            tx_hash = addr_and_tx_hash[1]
            address_db_entry = (
                dbsession.query(RskAddress).filter(RskAddress.address == addr).one()
            )
            try:
                dumps(traces)
            except TypeError:
                logger.warning(
                    "Traces cannot be serialized for addr %s, tx_hash %s, skipping",
                    addr,
                    tx_hash,
                )
                continue
            skip_entry = False
            for row in included_rows:
                if row.address == address_db_entry and not (
                    row.start <= block_n and (row.end is None or block_n < row.end)
                ):
                    skip_entry = True
            if skip_entry:
                continue
            tx = RskTransactionInfo(
                address=address_db_entry,
                tx_hash=tx_hash,
                trace_json=traces,
                block_n=block_n,
                blocktime=block_info.timestamp,
            )
            dbsession.add(tx)
        if scanning_up:
            for row in included_rows:
                row.next_to_scan_high = block_n + 1
        else:
            for row in included_rows:
                row.lowest_scanned = block_n

    def scan_up(
        self, dbsession: Session, chain_id: int, safety_limit: int = 12
    ) -> bool:
        current_block = self.web3.eth.block_number

        high_scan_rows = (
            dbsession.execute(
                select(RskAddressBookkeeper)
                .where(
                    and_(
                        RskAddressBookkeeper.next_to_scan_high <= current_block,
                        or_(
                            RskAddressBookkeeper.end.is_(None),
                            RskAddressBookkeeper.end
                            > RskAddressBookkeeper.next_to_scan_high + safety_limit,
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

        block_info = (
            dbsession.query(BlockInfo)
            .filter(
                and_(
                    BlockInfo.block_chain_id == chain_id,
                    BlockInfo.block_number == next_to_scan_high,
                )
            )
            .first()
        )
        if block_info is None:
            block = self.web3.eth.get_block(next_to_scan_high)
            block_info = BlockInfo(
                block_chain_id=chain_id,
                block_number=next_to_scan_high,
                timestamp=datetime.fromtimestamp(block["timestamp"], tz=timezone.utc),
            )
            dbsession.add(block_info)

        try:
            result = self.address_transactions_in_block(
                next_to_scan_high, high_scan_rows
            )
            self.add_result_to_db(
                dbsession=dbsession,
                block_n=next_to_scan_high,
                included_rows=high_scan_rows,
                result=result,
                scanning_up=True,
                block_info=block_info,
            )
        except Exception:
            logger.exception("Error in scan_up")
            dbsession.rollback()
        dbsession.flush()
        return True

    def scan_down(self, dbsession: Session, chain_id: int) -> bool:
        block_info = (
            dbsession.query(BlockInfo)
            .filter(BlockInfo.block_chain_id == chain_id)
            .order_by(BlockInfo.block_number.desc())
            .first()
        )
        if block_info is None:
            raise LookupError("No block info found when scanning down")
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
            result = self.address_transactions_in_block(
                low_scan_rows[0].lowest_scanned - 1, low_scan_rows
            )
            self.add_result_to_db(
                dbsession=dbsession,
                block_n=low_scan_rows[0].lowest_scanned - 1,
                included_rows=low_scan_rows,
                result=result,
                scanning_up=False,
                block_info=block_info,
            )
        except Exception:
            logger.exception("Error in scan_down")
            dbsession.rollback()
        dbsession.flush()
        return True

    def address_transactions_in_block(
        self, block_n: int, included_rows: Sequence[RskAddressBookkeeper]
    ) -> dict[tuple[str, str], list[dict]]:
        if not included_rows:
            return dict()
        if block_n < 1:
            return dict()
        if block_n % 1000 == 0:
            logger.info("Scanning block %d", block_n)

        addr_set = set(bk.address.address for bk in included_rows)
        result = self.web3.tracing.trace_block(block_n)
        result = convert_result_to_json_serializable(result)
        address_traces = defaultdict(list)

        for trace in result:
            trace_transaction_hash = trace["transactionHash"]
            if (from_addr := trace["action"].get("from")) and from_addr in addr_set:
                address_traces[from_addr, trace_transaction_hash].append(trace)
            if (to_addr := trace["action"].get("to")) and to_addr in addr_set:
                address_traces[to_addr, trace_transaction_hash].append(trace)

        return dict(address_traces)


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


def convert_result_to_json_serializable(result: List[dict]) -> list[dict]:
    ret_val = []
    for trace in result:
        ret_val.append(convert_to_json_serializable(trace))
    return ret_val


def parse_args(argv: List[str] | None = None):
    parser = argparse.ArgumentParser()
    parser.add_argument("config_uri", help="Path to the config file")
    return parser.parse_args()


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
    w3 = web3.Web3(web3.HTTPProvider("http://localhost:4444"))
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

    for i in cycle(range(1000)):
        try:
            scanned_down = bookkeeper.scan_down(dbsession, chain_id=rsk_id)
            if not scanned_down:
                scanned_up = bookkeeper.scan_up(
                    dbsession, chain_id=rsk_id, safety_limit=block_chain_meta.safe_limit
                )
                if not scanned_up:
                    dbsession.commit()
                    time.sleep(10)
            elif i % 100 == 99:
                bookkeeper.scan_up(
                    dbsession, chain_id=rsk_id, safety_limit=block_chain_meta.safe_limit
                )
                dbsession.commit()
        except Exception:
            logger.exception("Error scanning")
            time.sleep(10)


if __name__ == "__main__":
    main(sys.argv)

# SELECT COUNT(*) FROM rsk_tx_info WHERE address_id=26 AND JSONB_PATH_EXISTS(trace_json, '$[*].action ? (@.from == "0x1a8e78b41bc5ab9ebb6996136622b9b41a601b5c" && @.value > 0 )');
# SELECT * FROM rsk_tx_info WHERE address_id=29 AND JSONB_PATH_EXISTS(trace_json, '$[*].action ? (@.to == "0xe43cafbdd6674df708ce9dff8762af356c2b454d" &&  !(@.input starts with "0xe01ed1a2" ) )');
