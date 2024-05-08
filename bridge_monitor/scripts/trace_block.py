import configparser
from collections import defaultdict
from typing import Sequence, List
from pprint import pprint
import time
import logging

import web3
from sqlalchemy import create_engine
from sqlalchemy.engine import Engine, Row
from sqlalchemy.orm import Session
from sqlalchemy.sql.expression import select, or_, and_
from pyramid.paster import setup_logging
from ..models.rsk_transaction_info import RskAddressBookkeeper, RskAddress, RskTransactionInfo


logger = logging.getLogger(__name__)

TIME_PER_ITERATION_SEC: int | float = 0.5

class Bookkeeper:
    def __init__(self, passed_web3: web3.Web3, engine: Engine):
        self.web3 = passed_web3
        self.db_engine = engine

    def add_address(self, address: str, name: str, initial_block: int, start: int = 1, end: int | None = None):
        dbsession = Session(self.db_engine)
        with dbsession.begin():
            address_db_entry = dbsession.query(RskAddress).filter(RskAddress.address == address).first()
            if address_db_entry is None:
                logger.info("Address %s not found in db, creating entry", address)
                address_db_entry = RskAddress(address=address, name=name)
            else:
                logger.info("Address %s alread exists in db with name %s", address, address_db_entry.name)
            dbsession.add(address_db_entry)
            bookkeeper_db_entry = dbsession.query(RskAddressBookkeeper)\
                .filter(RskAddressBookkeeper.address == address_db_entry).first()
            if bookkeeper_db_entry is not None:
                logger.info("Address %s bookkeeper already exists", address)
                return
            dbsession.add(RskAddressBookkeeper(address=address_db_entry, start=start, end=end,
                                               lowest_scanned=initial_block, next_to_scan_high=initial_block))

    def remove_address_bookkeeper(self, address: str, cascade: bool = False):
        logger.info("Removing address %s bookkeeper", address)
        dbsession = Session(self.db_engine)
        with dbsession.begin():
            address = dbsession.query(RskAddress).filter(RskAddress.address == address).first()
            if address is None:
                logger.info("Address %s not found in db, nothing to remove")
                return
            bookkeeper_db_entry = dbsession.query(RskAddressBookkeeper)\
                .filter(RskAddressBookkeeper.address == address).first()
            if bookkeeper_db_entry is None:
                logger.info("Address %s bookkeeper not found in db, nothing to remove", address.address)
                return
            dbsession.delete(bookkeeper_db_entry)
            if cascade:
                logger.info("Cascade delete enabled, removing address %s from rsk_address", address)
                dbsession.delete(address)
    def scan_block(self, dbsession: Session, block_n: int, included_rows: Sequence[Row]):
        logger.info("Scanning block %d", block_n)

        addr_set = set(bk[0].address.address for bk in included_rows)
        if len(addr_set) < 4:
            logger.info("Scanning for addresses %r", addr_set)
        else:
            logger.info("Scanning for %d addresses", len(addr_set))

        result = address_transactions_in_block(self.web3, addr_set, block_n)
        if not result:
            logger.info("No matching transactions found in block %d", block_n)
        else:
            logger.info("Found %d matching transactions", sum(len(v) for v in result.values()))

        for addr, set_of_transactions in result.items():
            address_db_entry = dbsession.query(RskAddress).filter(RskAddress.address == addr).one()
            for tx_hash in set_of_transactions:
                dbsession.add(RskTransactionInfo(
                    address=address_db_entry,
                    tx_hash=tx_hash,
                    block_n=block_n
                ))

        for row in included_rows:
            row = row[0]
            if row.next_to_scan_high == block_n:
                row.next_to_scan_high = block_n + 1
            elif row.lowest_scanned == block_n + 1:
                row.lowest_scanned = block_n

    def scan(self):
        dbsession = Session(self.db_engine)
        current_block = self.web3.eth.block_number
        with dbsession.begin():
            low_scan_rows = dbsession.execute(select(RskAddressBookkeeper)\
            .where(RskAddressBookkeeper.start < RskAddressBookkeeper.lowest_scanned)\
            .order_by(RskAddressBookkeeper.lowest_scanned.desc()).fetch(1, with_ties=True)).all()

            high_scan_rows = dbsession.execute(select(RskAddressBookkeeper)\
            .where(and_(RskAddressBookkeeper.next_to_scan_high <= current_block,
            or_(RskAddressBookkeeper.end == None, RskAddressBookkeeper.end > RskAddressBookkeeper.next_to_scan_high)))\
            .order_by(RskAddressBookkeeper.next_to_scan_high.asc()).fetch(1, with_ties=True)).all()

            if not low_scan_rows and not high_scan_rows:
                logger.info("Nothing to scan")
                return
            if low_scan_rows:
                try:
                    self.scan_block(dbsession, low_scan_rows[0][0].lowest_scanned - 1, low_scan_rows)
                except:
                    logger.exception("Error scanning low rows")
            if high_scan_rows:
                try:
                    self.scan_block(dbsession, high_scan_rows[0][0].next_to_scan_high, high_scan_rows)
                except:
                    logger.exception("Error scanning high rows")

def address_transactions_in_block(w3: web3.Web3, addr_set: set[str], block_n: int) -> defaultdict[str, set[str]]:

    result = w3.tracing.trace_block(block_n)
    transaction_dict = defaultdict(set)
    for trace in result:
        if (from_addr := trace.action.get("from")) and from_addr.lower() in addr_set:
            transaction_dict[from_addr.lower()].add(trace.transactionHash.hex())
        elif (to_addr := trace.action.get("to")) and to_addr.lower() in addr_set:
            transaction_dict[to_addr.lower()].add(trace.transactionHash.hex())
    return transaction_dict

def main():
    setup_logging("development_local.ini")
    logger.info("Starting block tracing")
    config = configparser.ConfigParser()
    config.read("development_local.ini")
    db_url = config['app:main']['sqlalchemy.url']
    engine = create_engine(db_url)
    w3 = web3.Web3(web3.HTTPProvider("http://localhost:4444"))
    bookkeeper = Bookkeeper(w3, engine)
    bookkeeper.add_address("0x1a8e78b41bc5ab9ebb6996136622b9b41a601b5c", "bidi-fastbtc", w3.eth.block_number)
    bookkeeper.add_address("0xe43cafbdd6674df708ce9dff8762af356c2b454d", "fastbtc-in", w3.eth.block_number)
    while True:
        start_time = time.time()
        bookkeeper.scan()
        time_to_sleep = TIME_PER_ITERATION_SEC - (time.time() - start_time)
        if time_to_sleep > 0:
            time.sleep(time_to_sleep)
        else:
            logger.warning("Iteration took longer than %f seconds", TIME_PER_ITERATION_SEC)

if __name__ == "__main__":
    main()
