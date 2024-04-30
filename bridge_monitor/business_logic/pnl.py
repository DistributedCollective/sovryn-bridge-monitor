import logging
from datetime import datetime, timezone
from decimal import Decimal
from functools import lru_cache

from sqlalchemy import func
from sqlalchemy.orm.session import Session
from transaction import TransactionManager
from web3 import Web3

from .utils import get_web3
from . import blockstream
from ..models import get_tm_session
from ..models.bidirectional_fastbtc import (BidirectionalFastBTCTransfer, SATOSHI_IN_BTC,
                                            TransferStatus as BidiFastBTCTransferStatus)
from ..models.fastbtc_in import (
    FastBTCInTransfer,
    FastBTCInTransferStatus,
)
from ..models.replenisher import BidirectionalFastBTCReplenisherTransaction
from ..models.pnl import PnLTransaction, ProfitCalculation

logger = logging.getLogger(__name__)


class PnLService:
    _transaction_manager: TransactionManager
    _session_factory: Session

    def __init__(
        self,
        session_factory,
        transaction_manager,
    ):
        self._session_factory = session_factory
        self._transaction_manager = transaction_manager

    def update_pnl(self):
        self.update_pnl_for_bidi_fastbtc_transfers()
        self.update_pnl_for_fastbtc_in_transfers()
        self.update_pnl_for_bidi_fastbtc_replenisher_transactions()

    def update_pnl_for_bidi_fastbtc_transfers(self):
        logger.info('Retrieving bidi-fastbtc transfer batches with unprocessed PnL calculations')
        with self._transaction_manager:
            dbsession = self._get_dbsession()

            mined_transfer_batches = dbsession.query(
                BidirectionalFastBTCTransfer.chain,
                BidirectionalFastBTCTransfer.marked_as_sending_transaction_hash,
                func.array_agg(BidirectionalFastBTCTransfer.marked_as_mined_transaction_hash).label('mined_tx_hashes'),
                func.array_agg(BidirectionalFastBTCTransfer.bitcoin_tx_id).label('bitcoin_tx_ids'),
                func.array_agg(BidirectionalFastBTCTransfer.id).label('ids'),
            ).filter(
                BidirectionalFastBTCTransfer.profit_calculation_id.is_(None),
                BidirectionalFastBTCTransfer.status == BidiFastBTCTransferStatus.MINED,
            ).group_by(
                BidirectionalFastBTCTransfer.chain,
                BidirectionalFastBTCTransfer.marked_as_sending_transaction_hash,
            ).all()
            num_transfers = sum(len(b['ids']) for b in mined_transfer_batches)
            logger.info(
                "Got %d mined transfer batches, %d transfers in total",
                len(mined_transfer_batches),
                num_transfers,
            )
        for i, batch in enumerate(mined_transfer_batches, start=1):
            logger.info("Updating PnL for bidi-fastbtc batch %d/%d", i, len(mined_transfer_batches))
            try:
                with self._transaction_manager:
                    self._update_pnl_for_mined_bidi_transfer_batch(batch)
            except Exception:
                logger.exception("Error while processing batch %d/%d", i, len(mined_transfer_batches))
                logger.error("Failed to process batch %s, skipping", batch)

    def _update_pnl_for_mined_bidi_transfer_batch(self, batch):
        transfer_ids = batch['ids']
        chain = batch['chain']
        sending_tx_hash = batch['marked_as_sending_transaction_hash']
        mined_tx_hashes = batch['mined_tx_hashes']
        if not len(set(mined_tx_hashes)) == 1:
            raise Exception(f"Expected exactly one mined tx hash, got {mined_tx_hashes}")
        mined_tx_hash = mined_tx_hashes[0]
        bitcoin_tx_ids = batch['bitcoin_tx_ids']
        if not len(set(bitcoin_tx_ids)) == 1:
            raise Exception(f"Expected exactly one bitcoin tx id, got {bitcoin_tx_ids}")
        bitcoin_tx_id = bitcoin_tx_ids[0]

        dbsession = self._get_dbsession()
        transfers = dbsession.query(BidirectionalFastBTCTransfer).filter(
            BidirectionalFastBTCTransfer.id.in_(transfer_ids),
        ).order_by(
            BidirectionalFastBTCTransfer.id
        ).all()
        if not len(transfers) == len(transfer_ids):
            raise Exception(f"Expected {len(transfer_ids)} transfers, got {len(transfers)}")
        if not all(t.chain == chain for t in transfers):
            raise Exception(f"Expected all transfers to be on chain {chain}")
        if not all(t.marked_as_sending_transaction_hash == sending_tx_hash for t in transfers):
            # Sanity check, should never happen
            raise Exception(f"Expected all transfers to have sending tx hash {sending_tx_hash}")
        if not all(t.marked_as_mined_transaction_hash == mined_tx_hash for t in transfers):
            # Sanity check, should never happen
            raise Exception(f"Expected all transfers to have mined tx hash {mined_tx_hash}")
        if not all(t.bitcoin_tx_id == bitcoin_tx_id for t in transfers):
            # Sanity check, should never happen
            raise Exception(f"Expected all transfers to have bitcoin tx id {bitcoin_tx_id}")

        sending_tx = self._create_evm_pnl_transaction(chain, sending_tx_hash, comment="mark_transfers_as_sending")
        mined_tx = self._create_evm_pnl_transaction(chain, mined_tx_hash, comment="mark_transfers_as_mined")
        bitcoin_tx = self._create_bitcoin_pnl_transaction(chain, bitcoin_tx_id, comment="bitcoin_tx")

        chain_transactions = [
            sending_tx,
            bitcoin_tx,
            mined_tx,
        ]

        profit_calculation = ProfitCalculation(
            service="bidi_fastbtc",
            config_chain=chain,
            timestamp=sending_tx.timestamp,
            volume_btc=sum(t.formatted_amount for t in transfers),
            gross_profit_btc=sum(t.formatted_fee for t in transfers),
            cost_btc=sum(t.cost_btc for t in chain_transactions),
            transactions=chain_transactions,
        )
        logger.info("%s", profit_calculation)
        dbsession.add(profit_calculation)

        for transfer in transfers:
            transfer.profit_calculation = profit_calculation

        dbsession.flush()

    def update_pnl_for_fastbtc_in_transfers(self):
        logger.info('Retrieving fastbtc-in transfers with unprocessed PnL calculations')
        with self._transaction_manager:
            dbsession = self._get_dbsession()
            ids = self._get_unprocessed_object_ids(
                dbsession,
                FastBTCInTransfer,
                FastBTCInTransfer.status == FastBTCInTransferStatus.EXECUTED,
            )
            logger.info(
                "Got %d fastbtc-in transfers with unprocessed PnL calculations",
                len(ids)
            )

        for i, transfer_id in enumerate(ids, start=1):
            logger.info("Updating PnL for fastbtc-in transfer %d/%d", i, len(ids))
            try:
                with self._transaction_manager:
                    self._update_pnl_for_fastbtc_in_transfer(transfer_id)
            except Exception:
                logger.exception("Error while processing transfer %d/%d", i, len(ids))
                logger.error("Failed to process transfer %s, skipping", transfer_id)

    def _update_pnl_for_fastbtc_in_transfer(self, transfer_id):
        dbsession = self._get_dbsession()
        transfer = dbsession.query(FastBTCInTransfer).get(transfer_id)
        if transfer.profit_calculation_id is not None:
            logger.warning("Transfer %s already has a PnL calculation, skipping", transfer_id)
            return
        if transfer.status != FastBTCInTransferStatus.EXECUTED:
            raise Exception(f"Transfer {transfer_id} is not executed")

        chain = transfer.chain
        timestamp = transfer.executed_on
        if not timestamp:
            raise Exception(f"Transfer {transfer_id} has no executed_on timestamp")

        submission_tx = self._create_evm_pnl_transaction(
            chain=chain,
            transaction_hash=transfer.submission_transaction_hash,
            comment="submission",
        )
        execution_tx = self._create_evm_pnl_transaction(
            chain=chain,
            transaction_hash=transfer.executed_transaction_hash,
            comment="execution",
        )
        all_tx_hashes = {submission_tx.transaction_id, execution_tx.transaction_id}

        confirmation_txs = []
        for confirmation in transfer.confirmations:
            tx_hash = confirmation['tx_hash']
            if tx_hash in all_tx_hashes:
                # This confirmation is part of submission/execution tx
                continue
            confirmation_tx = self._create_evm_pnl_transaction(
                chain=chain,
                transaction_hash=tx_hash,
                comment="confirmation",
            )
            confirmation_txs.append(confirmation_tx)
            all_tx_hashes.add(tx_hash)

        revocation_txs = []
        for revocation in transfer.revocations:
            tx_hash = revocation['tx_hash']
            if tx_hash in all_tx_hashes:
                continue
            revocation_tx = self._create_evm_pnl_transaction(
                chain=chain,
                transaction_hash=tx_hash,
                comment="revocation",
            )
            confirmation_txs.append(revocation_tx)
            all_tx_hashes.add(tx_hash)
            confirmation_tx_hash = revocation['revoked_confirmation_tx_hash']
            if confirmation_tx_hash in all_tx_hashes:
                # for some reason, this was already in confirmations...
                continue
            confirmation_tx = self._create_evm_pnl_transaction(
                chain=chain,
                transaction_hash=confirmation_tx_hash,
                comment="revoked_confirmation",
            )
            confirmation_txs.append(confirmation_tx)
            all_tx_hashes.add(confirmation_tx_hash)

        transactions = [
            submission_tx,
            *confirmation_txs,
            *revocation_txs,
        ]
        if execution_tx.transaction_id not in set(t.transaction_id for t in transactions):
            # It might have been submitted and executed in the same tx
            transactions.append(execution_tx)

        profit_calculation = ProfitCalculation(
            service="fastbtc_in",
            config_chain=transfer.chain,
            timestamp=timestamp,
            volume_btc=transfer.formatted_net_amount + transfer.formatted_fee,
            gross_profit_btc=transfer.formatted_fee,
            cost_btc=sum(t.cost_btc for t in transactions),
            transactions=transactions,
        )
        logger.info("%s", profit_calculation)
        dbsession.add(profit_calculation)
        transfer.profit_calculation = profit_calculation
        dbsession.flush()

    def update_pnl_for_bidi_fastbtc_replenisher_transactions(self):
        logger.info("Retrieving bidi-fastbtc replenisher transactions with unprocessed PnL calculations")
        with self._transaction_manager:
            dbsession = self._get_dbsession()
            ids = self._get_unprocessed_object_ids(
                dbsession,
                BidirectionalFastBTCReplenisherTransaction,
            )
            logger.info(
                "Got %d bidi-fastbtc replenisher transactions with unprocessed PnL calculations",
                len(ids)
            )
            # just do it in the same tx... it doesn't take much time since we don't require any api calls
            for i, replenisher_tx_id in enumerate(ids, start=1):
                logger.info(
                    "Updating PnL for bidi-fastbtc replenisher transaction %d/%d",
                    replenisher_tx_id,
                    len(ids)
                )
                replenisher_tx = dbsession.query(BidirectionalFastBTCReplenisherTransaction).get(replenisher_tx_id)
                profit_calculation = ProfitCalculation(
                    service="fastbtc_replenisher",
                    config_chain=replenisher_tx.config_chain,
                    timestamp=replenisher_tx.confirmed_on,
                    volume_btc=Decimal('0'),  # replenishment amount doesn't count towards volume
                    gross_profit_btc=Decimal('0'),  # replenishment fee doesn't count towards profit
                    cost_btc=replenisher_tx.fee_btc,
                    transactions=[
                        PnLTransaction(
                            transaction_chain=replenisher_tx.transaction_chain,
                            transaction_id=replenisher_tx.transaction_id,
                            timestamp=replenisher_tx.confirmed_on,
                            block_number=replenisher_tx.block_number,
                            cost_btc=replenisher_tx.fee_btc,
                            comment="bidi_fastc_replenisher",
                        )
                    ]
                )
                logger.info("%s", profit_calculation)
                dbsession.add(profit_calculation)
                replenisher_tx.profit_calculation = profit_calculation
                dbsession.flush()

    def _get_unprocessed_object_ids(self, dbsession, model, *extra_filter_args):
        objs = dbsession.query(
            model.id
        ).filter(
            model.profit_calculation_id.is_(None),
            *extra_filter_args,
        ).order_by(
            model.id
        ).all()
        logger.info("%s: %d unprocessed objects", model.__name__, len(objs))
        return [o.id for o in objs]

    def _create_evm_pnl_transaction(self, chain: str, transaction_hash: str, *, comment=""):
        web3 = self._get_web3(chain)
        transaction = web3.eth.get_transaction(transaction_hash)
        receipt = web3.eth.get_transaction_receipt(transaction_hash)
        timestamp = self._get_evm_block_timestamp(web3, receipt['blockNumber'])
        gas_used = receipt['gasUsed']
        gas_price_wei = transaction['gasPrice']
        gas_cost_wei = gas_used * gas_price_wei
        gas_cost_btc = Decimal(web3.fromWei(gas_cost_wei, 'ether'))
        return PnLTransaction(
            transaction_chain=chain,
            transaction_id=transaction_hash,
            timestamp=timestamp,
            block_number=receipt['blockNumber'],
            cost_btc=gas_cost_btc,
            comment=comment,
        )

    def _create_bitcoin_pnl_transaction(self, config_chain: str, transaction_id: str, *, comment=""):
        testnet = config_chain.endswith('testnet')  # hehehe, ugly hack
        bitcoin_tx = blockstream.get_transaction(transaction_id, testnet=testnet)
        if not bitcoin_tx['status']['confirmed']:
            raise Exception(f"Bitcoin tx {transaction_id} is not confirmed")
        block_number = bitcoin_tx['status']['block_height']
        timestamp = self._parse_timestamp(bitcoin_tx['status']['block_time'])
        fee_satoshi = bitcoin_tx['fee']
        cost_btc = Decimal(fee_satoshi) / SATOSHI_IN_BTC
        return PnLTransaction(
            transaction_chain='bitcoin_mainnet' if not testnet else 'bitcoin_testnet',
            transaction_id=transaction_id,
            timestamp=timestamp,
            block_number=block_number,
            cost_btc=cost_btc,
            comment=comment,
        )

    @lru_cache(maxsize=128)
    def _get_evm_block_timestamp(self, web3: Web3, block_identifier) -> datetime:
        assert block_identifier not in ['latest', 'pending']
        assert isinstance(block_identifier, int) or (isinstance(block_identifier, str) and block_identifier.startswith('0x'))
        block = web3.eth.get_block(block_identifier)
        return self._parse_timestamp(block['timestamp'])

    def _parse_timestamp(self, timestamp: int) -> datetime:
        return datetime.utcfromtimestamp(timestamp).replace(tzinfo=timezone.utc)

    @lru_cache()
    def _get_web3(self, chain_name) -> Web3:
        return get_web3(chain_name)

    def _get_dbsession(self) -> Session:
        return get_tm_session(
            self._session_factory,
            self._transaction_manager,
        )


def cli_main():
    import argparse
    from pyramid.paster import bootstrap
    from pyramid.paster import setup_logging
    from pyramid.request import Request
    parser = argparse.ArgumentParser()
    parser.add_argument('config_uri')
    args = parser.parse_args()

    setup_logging(args.config_uri)

    env = bootstrap(args.config_uri)
    request: Request = env['request']
    session_factory = request.registry['dbsession_factory']
    transaction_manager = request.tm

    pnl_service = PnLService(
        session_factory=session_factory,
        transaction_manager=transaction_manager,
    )
    pnl_service.update_pnl()


if __name__ == '__main__':
    cli_main()
