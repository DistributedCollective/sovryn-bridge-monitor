import logging
from collections import defaultdict
from typing import Optional

import transaction
from eth_utils import to_hex

from bridge_monitor.business_logic.key_value_store import KeyValueStore
from bridge_monitor.models import get_tm_session
from .constants import BIDI_FASTBTC_ABI, BIDI_FASTBTC_CONFIGS
from .utils import get_events, get_web3, retryable
from ..models.bidirectional_fastbtc import BidirectionalFastBTCTransfer, TransferStatus
from ..models.types import now_in_utc

logger = logging.getLogger(__name__)


def update_bidi_fastbtc_transfers(
    config_name: str,
    *,
    session_factory,
    transaction_manager=transaction.manager,
    max_blocks: Optional[int] = None,
    min_block_confirmations: int = 5,
):
    config = BIDI_FASTBTC_CONFIGS[config_name]
    logger.info("Updating Bi-directional FastBTC state with config %s", config)

    chain_name = config["chain"]
    web3 = get_web3(chain_name)
    fastbtc_bridge = web3.eth.contract(
        abi=BIDI_FASTBTC_ABI, address=config["contract_address"]
    )

    with transaction_manager:
        dbsession = get_tm_session(
            session_factory,
            transaction_manager,
        )
        key_value_store = KeyValueStore(dbsession=dbsession)
        last_processed_block_key = f"bidi-fastbtc:last-processed-block:{chain_name}"
        last_processed_block = key_value_store.get_or_create_value(
            last_processed_block_key,
            config["start_block"] - 1,
        )

    from_block = last_processed_block + 1
    to_block = web3.eth.get_block_number() - min_block_confirmations

    max_blocks_from_now = config.get("max_blocks_from_now")
    if max_blocks_from_now and to_block - max_blocks_from_now > from_block:
        logger.info(
            "Limiting bidi-FastBTC start block to %s blocks from now (%s instead of %s)",
            max_blocks_from_now,
            to_block - max_blocks_from_now,
            from_block,
        )
        from_block = to_block - max_blocks_from_now

    now = now_in_utc()
    if max_blocks:
        to_block = min(from_block + max_blocks, to_block)

    if from_block > to_block:
        logger.info(
            "Bidi FastBTC start block %s is larger than bridge end block %s -- skipping",
            from_block,
            to_block,
        )
        return

    # TODO: optimize by getting all events in a single call, not 3 calls

    logger.info("Fetching events...")
    new_bitcoin_transfer_events = get_events(
        event=fastbtc_bridge.events.NewBitcoinTransfer(),
        from_block=from_block,
        to_block=to_block,
    )
    logger.info("Found %s NewBitcoinTransfer events", len(new_bitcoin_transfer_events))

    bitcoin_transfer_batch_sending_events = get_events(
        event=fastbtc_bridge.events.BitcoinTransferBatchSending(),
        from_block=from_block,
        to_block=to_block,
    )
    logger.info(
        "Found %s BitcoinTransferBatchSending events",
        len(bitcoin_transfer_batch_sending_events),
    )

    bitcoin_transfer_status_updated_events = get_events(
        event=fastbtc_bridge.events.BitcoinTransferStatusUpdated(),
        from_block=from_block,
        to_block=to_block,
    )
    logger.info(
        "Found %s BitcoinTransferStatusUpdated events",
        len(bitcoin_transfer_status_updated_events),
    )

    # Prepare a list of TransferBatchSending events for each transaction
    transfer_batch_sending_events_by_tx_hash = defaultdict(list)
    for event in bitcoin_transfer_batch_sending_events:
        # Add a reference to this event for each event in the transferBatchSize,
        # to make processing easier
        transfer_batch_sending_events_by_tx_hash[event.transactionHash].extend(
            [event] * event.args.transferBatchSize
        )

    @retryable()
    def get_block(block_hash):
        return web3.eth.get_block(block_hash)

    logger.info("Retrieving all blocks with events in them")
    blocks_by_block_hash = dict()
    for event in [
        *new_bitcoin_transfer_events,
        *bitcoin_transfer_status_updated_events,
        *bitcoin_transfer_batch_sending_events,
    ]:
        if event.blockHash not in blocks_by_block_hash:
            blocks_by_block_hash[event.blockHash] = get_block(event.blockHash)

    with transaction_manager:
        dbsession = get_tm_session(
            session_factory,
            transaction_manager,
        )
        # Create new transfers
        for event in new_bitcoin_transfer_events:
            event_block = blocks_by_block_hash[event.blockHash]
            transfer = BidirectionalFastBTCTransfer(
                chain=chain_name,
                transfer_id=to_hex(event.args.transferId),
                rsk_address=event.args.rskAddress,
                bitcoin_address=event.args.btcAddress,
                total_amount_satoshi=event.args.amountSatoshi + event.args.feeSatoshi,
                net_amount_satoshi=event.args.amountSatoshi,
                fee_satoshi=event.args.feeSatoshi,
                status=TransferStatus.NEW,
                bitcoin_tx_id=None,
                event_block_number=event.blockNumber,
                event_block_hash=event.blockHash.hex(),
                event_block_timestamp=event_block.timestamp,
                event_transaction_hash=event.transactionHash.hex(),
                event_log_index=event.logIndex,
            )
            dbsession.add(transfer)
        dbsession.flush()  # so that we can query these events

        # Update transfer statuses and bitcoin hashes
        for event in bitcoin_transfer_status_updated_events:
            transfer_id = to_hex(event.args.transferId)
            event_block = blocks_by_block_hash[event.blockHash]
            try:
                transfer = (
                    dbsession.query(BidirectionalFastBTCTransfer)
                    .filter_by(
                        chain=chain_name,
                        transfer_id=transfer_id,
                    )
                    .one()
                )
            except Exception:
                logger.error(
                    "Could not find transfer with id %s, chain %s",
                    transfer_id,
                    chain_name,
                )
                raise

            status = TransferStatus(event.args.newStatus)
            if status == TransferStatus.SENDING:
                sending_event = transfer_batch_sending_events_by_tx_hash[
                    event.transactionHash
                ].pop(0)
                bitcoin_tx_id = to_hex(sending_event.args.bitcoinTxHash)
                if bitcoin_tx_id.startswith("0x"):
                    bitcoin_tx_id = bitcoin_tx_id[2:]

                transfer.bitcoin_tx_id = bitcoin_tx_id
                transfer.transfer_batch_size = sending_event.args.transferBatchSize
                transfer.marked_as_sending_transaction_hash = (
                    event.transactionHash.hex()
                )
                transfer.marked_as_sending_block_hash = event.blockHash.hex()
                transfer.marked_as_sending_block_number = event.blockNumber
                transfer.marked_as_sending_block_timestamp = event_block.timestamp
                transfer.marked_as_sending_log_index = event.logIndex
            elif status == TransferStatus.MINED:
                transfer.marked_as_mined_transaction_hash = event.transactionHash.hex()
                transfer.marked_as_mined_block_hash = event.blockHash.hex()
                transfer.marked_as_mined_block_number = event.blockNumber
                transfer.marked_as_mined_block_timestamp = event_block.timestamp
                transfer.marked_as_mined_log_index = event.logIndex
            elif status in (TransferStatus.REFUNDED, TransferStatus.RECLAIMED):
                transfer.refunded_or_reclaimed_transaction_hash = (
                    event.transactionHash.hex()
                )
                transfer.refunded_or_reclaimed_block_hash = event.blockHash.hex()
                transfer.refunded_or_reclaimed_block_number = event.blockNumber
                transfer.refunded_or_reclaimed_block_timestamp = event_block.timestamp
                transfer.refunded_or_reclaimed_log_index = event.logIndex
            else:
                logger.error("Invalid status: %s for event: %s", status, event)
                raise ValueError(f"Invalid status: {status} for event: {event}")
            transfer.status = status
            transfer.updated_on = now

        # Update processed block number and updated timestamp
        logger.info("Updating last processed block to %s", to_block)
        key_value_store = KeyValueStore(dbsession=dbsession)
        key_value_store.set_value(last_processed_block_key, to_block)
        key_value_store.set_value(
            f"bidi-fastbtc:last-updated:{chain_name}",
            now.isoformat(),
        )

    logger.info("Updated bidirectional FastBTC transfers")
