import logging
from typing import Optional

import transaction

from bridge_monitor.business_logic.key_value_store import KeyValueStore
from bridge_monitor.models import get_tm_session
from .constants import (
    FASTBTC_IN_CONFIGS,
    FASTBTC_IN_MANAGEDWALLET_ABI,
    FASTBTC_IN_MULTISIG_ABI,
)
from .utils import get_all_contract_events, get_web3
from ..models.fastbtc_in import FastBTCInTransfer
from ..models.types import now_in_utc


logger = logging.getLogger(__name__)


def update_fastbtc_in_transfers(
    config_name: str,
    *,
    session_factory,
    transaction_manager=transaction.manager,
    max_blocks: Optional[int] = None,
    min_block_confirmations: int = 5,
):
    config = FASTBTC_IN_CONFIGS[config_name]
    logger.info("Updating FastBTC-in state with config %s", config)

    chain_name = config["chain"]
    web3 = get_web3(chain_name)
    multisig = web3.eth.contract(
        abi=FASTBTC_IN_MULTISIG_ABI, address=config["multisig_address"]
    )
    managed_wallet = web3.eth.contract(
        abi=FASTBTC_IN_MANAGEDWALLET_ABI, address=config["managedwallet_address"]
    )

    with transaction_manager:
        dbsession = get_tm_session(
            session_factory,
            transaction_manager,
        )
        key_value_store = KeyValueStore(dbsession=dbsession)
        last_processed_block_key = f"fastbtc-in:last-processed-block:{chain_name}"
        last_processed_block = key_value_store.get_or_create_value(
            last_processed_block_key,
            config["start_block"] - 1,
        )

    from_block = last_processed_block + 1
    to_block = web3.eth.get_block_number() - min_block_confirmations

    max_blocks_from_now = config.get("max_blocks_from_now")
    if max_blocks_from_now and to_block - max_blocks_from_now > from_block:
        logger.info(
            "Limiting FastBTC-in start block to %s blocks from now (%s instead of %s)",
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
            "FastBTC-in start block %s is larger than bridge end block %s -- skipping",
            from_block,
            to_block,
        )
        return

    multisig_events = get_all_contract_events(
        web3=web3,
        contract=multisig,
        from_block=from_block,
        to_block=to_block,
    )

    logger.info("Found %s fastbtc-in events", len(multisig_events))

    # Retrieve all data from blockchain before starting the DB transaction
    logger.info("Retrieving all related blocks and multisig transactions")
    blocks_by_block_hash = dict()
    multisig_transactions_by_tx_id = dict()

    for i, event in enumerate(multisig_events, start=1):
        if i % 10 == 0 or i == len(multisig_events):
            logger.info("%s/%s", i, len(multisig_events))
        if event.blockHash not in blocks_by_block_hash:
            blocks_by_block_hash[event.blockHash] = web3.eth.get_block(event.blockHash)
        transaction_id = event.args.get("transactionId")
        if (
            transaction_id is not None
            and transaction_id not in multisig_transactions_by_tx_id
        ):
            multisig_transactions_by_tx_id[transaction_id] = (
                multisig.functions.transactions(transaction_id).call()
            )

    with transaction_manager:
        dbsession = get_tm_session(
            session_factory,
            transaction_manager,
        )
        for event in multisig_events:
            block = blocks_by_block_hash[event.blockHash]
            timestamp = block["timestamp"]
            if event.event not in (
                "Submission",
                "Confirmation",
                "Revocation",
                "Execution",
                "ExecutionFailure",
            ):
                # Not interested in other events, like OwnerAddition
                # Also all of these have the transactionId arg
                continue

            transaction_id = event.args["transactionId"]
            multisig_tx = multisig_transactions_by_tx_id[transaction_id]
            destination, value, data, executed = multisig_tx
            if destination != managed_wallet.address:
                logger.info(
                    "Ignoring fastbtc-in event %s tx %s with destination %s (not ManagedWallet)",
                    event.event,
                    transaction_id,
                    destination,
                )
                continue

            managed_wallet_func, managed_wallet_args = (
                managed_wallet.decode_function_input(data)
            )

            # Note: receiver is not parsed properly for `transferToBridge` transfers to aggregator,
            # but who cares, it's not used anyway
            if managed_wallet_func.function_identifier not in [
                "transferToUser",
                "withdrawAdmin",
                "transferToBridge",
            ]:
                logger.info(
                    "Ignoring fastbtc-in event %s tx %s with function %s",
                    event.event,
                    transaction_id,
                    managed_wallet_func.function_identifier,
                )
                continue

            bitcoin_tx_hash = managed_wallet_args.get("btcTxHash")
            if bitcoin_tx_hash:
                bitcoin_tx_hash = bitcoin_tx_hash.hex()
            transfer = FastBTCInTransfer.get_or_create(
                dbsession=dbsession,
                chain=chain_name,
                multisig_tx_id=transaction_id,
                rsk_receiver_address=managed_wallet_args.get("receiver"),
                transfer_function=managed_wallet_func.function_identifier,
                # amount is available in all functions, the rest only in transferToUser
                net_amount_wei=managed_wallet_args.get("amount"),
                fee_wei=managed_wallet_args.get("fee"),
                bitcoin_tx_hash=bitcoin_tx_hash,
                bitcoin_tx_vout=managed_wallet_args.get("btcTxVout"),
            )

            if event.event == "Submission":
                logger.info("Submission(%s) at block %s", event.args, block["number"])
                transfer.mark_submitted(
                    block_number=block["number"],
                    timestamp=timestamp,
                    block_hash=event.blockHash,
                    tx_hash=event.transactionHash,
                    log_index=event.logIndex,
                )
            elif event.event == "Confirmation":
                logger.info("Confirmation(%s) at block %s", event.args, block["number"])
                transfer.add_confirmation(
                    sender=event.args["sender"],
                    tx_hash=event.transactionHash,
                )
            elif event.event == "Revocation":
                logger.info("Revocation(%s) at block %s", event.args, block["number"])
                transfer.revoke_confirmation(
                    sender=event.args["sender"],
                    tx_hash=event.transactionHash,
                )
            elif event.event == "Execution":
                logger.info("Execution(%s) at block %s", event.args, block["number"])
                transfer.mark_executed(
                    block_number=block["number"],
                    timestamp=timestamp,
                    block_hash=event.blockHash,
                    tx_hash=event.transactionHash,
                    log_index=event.logIndex,
                )
            elif event.event == "ExecutionFailure":
                logger.info(
                    "ExecutionFailure(%s) at block %s", event.args, block["number"]
                )
                transfer.mark_execution_failure(
                    tx_hash=event.transactionHash,
                )
            else:
                raise Exception(f"Unexpected event {event.event}")

            # Flush for old times' sake
            dbsession.flush()

        # Update processed block number and updated timestamp
        logger.info("Updating last processed block to %s", to_block)
        key_value_store = KeyValueStore(dbsession=dbsession)
        key_value_store.set_value(last_processed_block_key, to_block)
        key_value_store.set_value(
            f"fastbtc-in:last-updated:{chain_name}",
            now.isoformat(),
        )

    logger.info("Updated bidirectional FastBTC transfers")
