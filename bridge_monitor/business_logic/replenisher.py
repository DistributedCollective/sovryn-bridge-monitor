"""
Service that tract the transaction made by the bidirectional FastBTC replenisher, e.g.
automatic funds transfers between FastBTC-in and bidirectional FastBTC
"""

import logging
from typing import Optional

import transaction
from sqlalchemy.orm.session import Session

from . import blockstream
from .key_value_store import KeyValueStore
from ..models import get_tm_session
from ..models.replenisher import BidirectionalFastBTCReplenisherTransaction

logger = logging.getLogger(__name__)


class ReplenisherTransactionScanner:
    def __init__(
        self,
        *,
        config_chain: str,  # rsk_mainnet or rsk_testnet
        bidi_fastbtc_btc_multisig_address: Optional[str],
        session_factory: Session,
        transaction_manager: transaction.TransactionManager = transaction.manager,
    ):
        if config_chain not in ("rsk_mainnet", "rsk_testnet"):
            raise ValueError(
                f"Invalid config_chain {config_chain}, must be rsk_mainnet or rsk_testnet"
            )
        self._config_chain = config_chain
        self._testnet = config_chain == "rsk_testnet"
        self._transaction_chain = (
            "bitcoin_testnet" if self._testnet else "bitcoin_mainnet"
        )
        self._bidi_fastbtc_btc_multisig_address = bidi_fastbtc_btc_multisig_address
        self._session_factory = session_factory
        self._transaction_manager = transaction_manager

    def scan_replenisher_transactions(self):
        """
        Scan for replenisher transactions and update the database accordingly.
        """
        self.scan_bidi_fastbtc_replenisher_transactions()

    def scan_bidi_fastbtc_replenisher_transactions(self):
        if not self._bidi_fastbtc_btc_multisig_address:
            logger.info(
                "No bidirectional FastBTC replenisher address configured, skipping replenisher tx scanning"
            )
            return

        last_processed_txid_key = (
            f"bidi-fastbtc-replenisher:last-processed-txid:{self._config_chain}"
        )
        with self._transaction_manager:
            dbsession = self._get_dbsession()
            key_value_store = KeyValueStore(dbsession=dbsession)
            last_processed_txid = key_value_store.get_value(
                last_processed_txid_key, None
            )

        raw_replenisher_txs = []

        logger.info(
            "Fetching new transactions for %s (until tx id %s)",
            self._bidi_fastbtc_btc_multisig_address,
            last_processed_txid,
        )
        # This iterates newest-first
        tx_iterator = blockstream.get_confirmed_transactions(
            self._bidi_fastbtc_btc_multisig_address,
            testnet=self._testnet,
            after_txid=last_processed_txid,
        )
        new_last_processed_txid = None
        for i, raw_tx in enumerate(tx_iterator, start=1):  # oldest first
            if not new_last_processed_txid:
                new_last_processed_txid = raw_tx["txid"]
            logger.info("Checking tx %d: %s", i + 1, raw_tx["txid"])
            if self._is_bidi_fastbtc_replenisher_transaction(raw_tx):
                logger.info(
                    "Found bidi-fastbtc replenisher transaction %s", raw_tx["txid"]
                )
                raw_replenisher_txs.append(raw_tx)

        logger.info(
            "Processing %d bidi-fastbtc replenisher transactions",
            len(raw_replenisher_txs),
        )
        raw_replenisher_txs.reverse()  # oldest first
        with self._transaction_manager:
            dbsession = self._get_dbsession()
            key_value_store = KeyValueStore(dbsession=dbsession)
            for i, raw_tx in enumerate(raw_replenisher_txs, start=1):
                logger.info(
                    "Processing bidi-fastbtc replenisher transaction %d/%d: %s",
                    i,
                    len(raw_replenisher_txs),
                    raw_tx["txid"],
                )
                replenisher_tx = self._parse_bidi_fastbtc_replenisher_transaction(
                    raw_tx
                )
                dbsession.add(replenisher_tx)
            if new_last_processed_txid:
                logger.info(
                    "Updating last processed txid to %s", new_last_processed_txid
                )
                key_value_store.set_value(
                    last_processed_txid_key, new_last_processed_txid
                )

    def _is_bidi_fastbtc_replenisher_transaction(self, tx):
        """
        Return True if raw tx from blcokstream is a replenisher transaction.

        Replenisher transactions have the following properties:
        - Exactly 2 outputs (no change output)
        - ScriptPubKey for the first output is "OP_RETURN OP_PUSHBYTES_1 00" with value 0
        - The address for the second output is the replenisher's multisig address
        """
        outputs = tx["vout"]
        if len(outputs) != 2:
            return False
        if (
            outputs[1]["scriptpubkey_address"]
            != self._bidi_fastbtc_btc_multisig_address
        ):
            return False
        if outputs[0].get("scriptpubkey_asm", "") != "OP_RETURN OP_PUSHBYTES_1 00":
            # If this is not so, it might be a manual replenishment transaction
            return False
        if outputs[0]["value"] != 0:
            logger.warning(
                "Replenisher transaction %s has OP_RETURN output with value %s instead of 0 "
                "(still treating as a replenisher transaction)",
                tx["txid"],
                outputs[0]["value"],
            )
        return True

    def _parse_bidi_fastbtc_replenisher_transaction(self, tx):
        if not self._is_bidi_fastbtc_replenisher_transaction(tx):
            raise ValueError(f"Transaction {tx} is not a replenisher transaction")
        return BidirectionalFastBTCReplenisherTransaction(
            config_chain=self._config_chain,
            transaction_chain=self._transaction_chain,
            transaction_id=tx["txid"],
            block_number=tx["status"]["block_height"],
            block_timestamp=tx["status"]["block_time"],
            fee_satoshi=tx["fee"],
            amount_satoshi=tx["vout"][1]["value"],
            raw_data={
                "blockstream_transaction": tx,
            },
        )

    def _get_dbsession(self) -> Session:
        return get_tm_session(
            self._session_factory,
            self._transaction_manager,
        )


def scan_replenisher_transactions(
    *,
    chain_env: str,
    session_factory: Session,
    transaction_manager: transaction.TransactionManager = transaction.manager,
):
    if chain_env not in ("mainnet", "testnet"):
        raise ValueError(f"Invalid chain_env {chain_env}, must be mainnet or testnet")
    from .constants import BIDI_FASTBTC_CONFIGS

    config_name = f"rsk_{chain_env}"
    bidi_config = BIDI_FASTBTC_CONFIGS[config_name]
    scanner = ReplenisherTransactionScanner(
        config_chain=config_name,
        bidi_fastbtc_btc_multisig_address=bidi_config.get("btc_multisig_address"),
        session_factory=session_factory,
        transaction_manager=transaction_manager,
    )
    scanner.scan_replenisher_transactions()


def cli_main():
    import argparse
    from pyramid.paster import bootstrap
    from pyramid.paster import setup_logging
    from pyramid.request import Request
    from .constants import BIDI_FASTBTC_CONFIGS

    parser = argparse.ArgumentParser()
    parser.add_argument("config_uri")
    args = parser.parse_args()

    setup_logging(args.config_uri)

    env = bootstrap(args.config_uri)
    request: Request = env["request"]
    session_factory = request.registry["dbsession_factory"]
    transaction_manager = request.tm
    chain_env = request.registry["chain_env"]

    config_chain = f"rsk_{chain_env}"
    bidi_config = BIDI_FASTBTC_CONFIGS[config_chain]

    scanner = ReplenisherTransactionScanner(
        config_chain=config_chain,
        bidi_fastbtc_btc_multisig_address=bidi_config.get("btc_multisig_address"),
        session_factory=session_factory,
        transaction_manager=transaction_manager,
    )
    scanner.scan_replenisher_transactions()


if __name__ == "__main__":
    cli_main()
