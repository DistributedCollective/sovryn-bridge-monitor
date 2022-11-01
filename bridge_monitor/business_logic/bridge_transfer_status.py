"""
Low-level operations for fetching bridge transfers (no DB updates)
"""
import functools
import logging
from dataclasses import dataclass
from typing import List, Optional

from eth_utils import to_hex
from web3.logs import DISCARD

from .constants import BRIDGE_ABI, BridgeConfig, FEDERATION_ABI
from .utils import call_concurrently, get_events, get_web3, to_address

logger = logging.getLogger(__name__)


@dataclass
class TransferDTO:
    from_chain: str
    to_chain: str
    transaction_id: str
    transaction_id_old: str
    was_processed: bool
    num_votes: int
    receiver_address: str
    depositor_address: str
    token_address: str
    token_symbol: str
    token_decimals: int
    amount_wei: int
    user_data: str
    event_block_number: int
    event_block_hash: str
    event_block_timestamp: int
    event_transaction_hash: str
    event_log_index: int
    executed_transaction_hash: Optional[str]
    executed_block_hash: Optional[str]
    executed_block_number: Optional[int]
    executed_block_timestamp: Optional[int]
    executed_log_index: Optional[int]
    has_error_token_receiver_events: bool
    error_data: str
    #vote_transaction_args: Tuple
    #cross_event: AttributeDict


def fetch_state(
    main_bridge_config: BridgeConfig,
    side_bridge_config: BridgeConfig,
    *,
    bridge_start_block: Optional[int] = None,
    federation_start_block: Optional[int] = None,
    max_blocks: Optional[int] = None,
    min_block_confirmations: int = 5,
) -> List[TransferDTO]:
    bridge_address = main_bridge_config['bridge_address']
    if not bridge_start_block:
        bridge_start_block = main_bridge_config['bridge_start_block']
    if not federation_start_block:
        federation_start_block = side_bridge_config['bridge_start_block']
    side_bridge_address = side_bridge_config['bridge_address']
    federation_address = side_bridge_config['federation_address']
    main_chain = main_bridge_config['chain']
    side_chain = side_bridge_config['chain']

    main_web3 = get_web3(main_chain)
    bridge_contract = main_web3.eth.contract(
        address=to_address(bridge_address),
        abi=BRIDGE_ABI,
    )
    # Note: we need to get the Cross events right -- other parts are less important (and updates will be handled
    # for them). So we only care for confirmations for the bridge.
    bridge_end_block = main_web3.eth.get_block_number() - min_block_confirmations
    if max_blocks:
        bridge_end_block = min(bridge_start_block + max_blocks, bridge_end_block)

    if bridge_start_block > bridge_end_block:
        logger.info("Bridge start block %s is larger than bridge end block %s -- skipping",
                    bridge_start_block,
                    bridge_end_block)
        return []

    side_web3 = get_web3(side_chain)
    federation_contract = side_web3.eth.contract(
        address=to_address(federation_address),
        abi=FEDERATION_ABI,
    )
    federation_end_block = side_web3.eth.get_block_number()
    if max_blocks:
        federation_end_block = min(federation_start_block + max_blocks, federation_end_block)

    side_bridge_contract = side_web3.eth.contract(
        address=to_address(side_bridge_address),
        abi=BRIDGE_ABI,
    )

    logger.info(f'main: {main_chain}, side: {side_chain}, from: {bridge_start_block}, to: {bridge_end_block}')

    logger.info('getting Cross and Executed events')
    cross_events, executed_events = call_concurrently(
        lambda: get_events(
            event=bridge_contract.events.Cross,
            from_block=bridge_start_block,
            to_block=bridge_end_block,
            batch_size=get_event_batch_size(main_chain),
        ),
        lambda: get_events(
            event=federation_contract.events.Executed,
            from_block=federation_start_block,
            to_block=federation_end_block,
            batch_size=get_event_batch_size(side_chain),
        ),
    )

    logger.info(f'found {len(cross_events)} Cross events')
    logger.info(f'found {len(executed_events)} Executed events')
    executed_event_by_transaction_id = {
        to_hex(e.args.transactionId): e
        for e in executed_events
    }

    # Cache block retrieval -- might speed things up a tiny bit
    @functools.lru_cache(maxsize=128)
    def _get_block(web3, block_hash):
        return web3.eth.get_block(block_hash)

    logger.info('processing transfers')
    transfers = []
    for index, event in enumerate(cross_events):
        args = event.args
        tx_id_args_old = (
            args['_tokenAddress'],
            args['_to'],
            args['_amount'],
            args['_symbol'],
            event.blockHash,
            event.transactionHash,
            event.logIndex,
            args['_decimals'],
            args['_granularity'],
        )
        tx_id_args = tx_id_args_old + (
            args['_userData'],
        )

        logger.info("Progress: %.2f %%", index / len(cross_events) * 100)
        #logger.debug('event %s: %s', index, event)

        def get_tx_id_u():
            return federation_contract.functions.getTransactionIdU(*tx_id_args).call()
            try:
                return federation_contract.functions.getTransactionIdU(*tx_id_args).call()
            except Exception as e:
                logger.error('Error calling getTransactionIdU for main %s side %s, falling back', main_chain, side_chain)
                if 'transaction reverted' in str(e) or 'execution reverted' in str(e):
                    return federation_contract.functions.getTransactionId(*tx_id_args_old).call()
                raise

        event_receipt, event_block, transaction_id, transaction_id_old = call_concurrently(
            lambda: main_web3.eth.get_transaction_receipt(event.transactionHash),
            lambda: _get_block(main_web3, event.blockHash),
            get_tx_id_u,
            federation_contract.functions.getTransactionId(*tx_id_args_old),
            retry=True
        )

        transaction_id = to_hex(transaction_id)
        #logger.debug('transaction_id: %s', transaction_id)
        transaction_id_old = to_hex(transaction_id_old)
        #logger.debug('transaction_id_old: %s', transaction_id_old)
        #logger.debug('event block: %s', event_block)
        #logger.debug('event receipt: %s', event_receipt)

        executed_event = executed_event_by_transaction_id.get(transaction_id)
        #logger.debug('related Executed event: %s', executed_event)
        executed_transaction_hash = executed_event.transactionHash.hex() if executed_event else None

        num_votes, was_processed, executed_transaction_receipt, executed_block = call_concurrently(
            federation_contract.functions.getTransactionCount(transaction_id),
            federation_contract.functions.transactionWasProcessed(transaction_id),
            lambda: (
                side_web3.eth.get_transaction_receipt(executed_transaction_hash)
                if executed_transaction_hash
                else None
            ),
            lambda: (
                _get_block(side_web3, executed_event.blockHash)
                if executed_event
                else None
            ),
            retry=True
        )

        #logger.debug('num_votes: %s', num_votes)
        #logger.debug('was_processed: %s', was_processed)

        error_token_receiver_events = tuple()
        if executed_transaction_receipt:
            error_token_receiver_events = side_bridge_contract.events.ErrorTokenReceiver().processReceipt(
                executed_transaction_receipt,
                errors=DISCARD,  # TODO: is this right?
            )

        transfer = TransferDTO(
            from_chain=main_chain,
            to_chain=side_chain,
            transaction_id=transaction_id,
            transaction_id_old=transaction_id_old,
            num_votes=num_votes,
            was_processed=was_processed,
            token_symbol=args['_symbol'],
            receiver_address=args['_to'],
            depositor_address=event_receipt['from'],
            token_address=args['_tokenAddress'],
            token_decimals=args['_decimals'],
            amount_wei=args['_amount'],
            user_data=to_hex(args['_userData']),
            event_block_number=event.blockNumber,
            event_block_hash=event.blockHash.hex(),
            event_block_timestamp=event_block.timestamp,
            event_transaction_hash=event.transactionHash.hex(),
            event_log_index=event.logIndex,
            executed_transaction_hash=executed_transaction_hash,
            executed_block_hash=executed_event.blockHash.hex() if executed_event else None,
            executed_block_number=executed_event.blockNumber if executed_event else None,
            executed_block_timestamp=executed_block.timestamp if executed_block else None,
            executed_log_index=executed_event.logIndex if executed_event else None,
            has_error_token_receiver_events=bool(error_token_receiver_events),
            error_data=to_hex(error_token_receiver_events[0].args._errorData) if error_token_receiver_events else '0x',
            #vote_transaction_args=vote_transaction_args,
            #cross_event=event,
        )
        logger.debug('transfer %s: %s', index, transfer)
        transfers.append(transfer)
    return transfers


def get_event_batch_size(chain_name: str) -> Optional[int]:
    #if chain_name.startswith('rsk_'):
    #    return 500
    return 250
