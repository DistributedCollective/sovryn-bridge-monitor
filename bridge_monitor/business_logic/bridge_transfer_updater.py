"""
High-level operations for updating bridge transfers in DB
"""
import logging
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict
from datetime import datetime
from typing import List, Optional

import transaction
from sqlalchemy.orm import Session

from .bridge_transfer_status import TransferDTO, fetch_state
from .constants import BRIDGES
from .key_value_store import KeyValueStore
from ..models import Transfer, get_tm_session
from ..models.types import now_in_utc

logger = logging.getLogger(__name__)


def update_transfers_from_all_bridges(
    *,
    session_factory,
    transaction_manager=transaction.manager,
    max_blocks: Optional[int] = None,
):
    # TODO: these are hardcoded :f
    for bridge_name in ['rsk_eth_mainnet', 'rsk_bsc_mainnet']:
        update_transfers(
            bridge_name=bridge_name,
            session_factory=session_factory,
            transaction_manager=transaction_manager,
            max_blocks=max_blocks,
        )


def update_transfers(
    *,
    bridge_name,
    session_factory,
    transaction_manager=transaction.manager,
    max_blocks: Optional[int] = None
):
    bridge_config = BRIDGES[bridge_name]

    with transaction_manager:
        dbsession = get_tm_session(
            session_factory,
            transaction_manager,
        )
        key_value_store = KeyValueStore(dbsession=dbsession)
        rsk_chain_name = bridge_config['rsk']['chain']
        rsk_chain_block_key = f'last-processed-block:{bridge_name}:{rsk_chain_name}'
        other_chain_name = bridge_config['other']['chain']
        other_chain_block_key = f'last-processed-block:{bridge_name}:{other_chain_name}'
        rsk_last_processed_block = key_value_store.get_or_create_value(
            rsk_chain_block_key,
            bridge_config['rsk']['bridge_start_block'] - 1,
        )
        other_last_processed_block = key_value_store.get_or_create_value(
            other_chain_block_key,
            bridge_config['other']['bridge_start_block'] - 1,
        )

    now = now_in_utc()

    with ThreadPoolExecutor() as executor:
        rsk_transfers_future = executor.submit(
            fetch_state,
            main_bridge_config=bridge_config['rsk'],
            side_bridge_config=bridge_config['other'],
            bridge_start_block=rsk_last_processed_block + 1,
            federation_start_block=other_last_processed_block + 1,
            max_blocks=max_blocks,
        )
        other_transfers_future = executor.submit(
            fetch_state,
            main_bridge_config=bridge_config['other'],
            side_bridge_config=bridge_config['rsk'],
            bridge_start_block=other_last_processed_block + 1,
            federation_start_block=rsk_last_processed_block + 1,
            max_blocks=max_blocks,
        )

    rsk_transfers = rsk_transfers_future.result()
    other_transfers = other_transfers_future.result()
    logger.debug("Got %s %s transfers", len(rsk_transfers), rsk_chain_name)
    logger.debug("Got %s %s transfers", len(other_transfers), other_chain_name)

    rsk_last_processed_block = get_last_block_number_with_all_transfers_processed(
        rsk_transfers,
        rsk_last_processed_block
    )
    logger.debug(
        "%s last block: %s, last fully processed: %s",
        rsk_chain_name,
        max(t.event_block_number for t in rsk_transfers) if rsk_transfers else '(none)',
        rsk_last_processed_block
    )
    other_last_processed_block = get_last_block_number_with_all_transfers_processed(
        other_transfers,
        other_last_processed_block
    )
    logger.debug(
        "%s last block: %s, last fully processed: %s",
        other_chain_name,
        max(t.event_block_number for t in other_transfers) if other_transfers else '(none)',
        other_last_processed_block
    )

    with transaction_manager:
        dbsession = get_tm_session(
            session_factory,
            transaction_manager,
        )
        key_value_store = KeyValueStore(dbsession=dbsession)

        update_db_transfers(
            dbsession=dbsession,
            transfer_dtos=rsk_transfers + other_transfers,
            now=now,
        )

        key_value_store.set_value(
            rsk_chain_block_key,
            rsk_last_processed_block
        )
        key_value_store.set_value(
            other_chain_block_key,
            other_last_processed_block
        )
        key_value_store.set_value(
            f'last-updated:{bridge_name}',
            now.isoformat(),
        )

    logger.debug("All done")


def get_last_block_number_with_all_transfers_processed(transfers: List[TransferDTO], default_value: int) -> int:
    transfers_by_block = defaultdict(list)
    for t in transfers:
        transfers_by_block[t.event_block_number].append(t)

    ret = default_value
    for block_number, transfers in sorted(transfers_by_block.items()):
        if any(not t.was_processed for t in transfers):
            break
        ret = block_number
    return ret


def update_db_transfers(*, dbsession: Session, transfer_dtos: List[TransferDTO], now: datetime):
    created, updated = 0, 0
    for transfer_dto in transfer_dtos:
        transfer = dbsession.query(Transfer).filter_by(
            transaction_id=transfer_dto.transaction_id,
            from_chain=transfer_dto.from_chain,
            to_chain=transfer_dto.to_chain,
        ).first()
        if not transfer:
            transfer = Transfer(
                **asdict(transfer_dto),
                created_on=now,
                updated_on=now,
            )
            logger.info("Creating transfer %s", transfer_dto)
            dbsession.add(transfer)
            created += 1
        else:
            compared_fields = [
                'was_processed',
                'num_votes',
                'executed_transaction_hash',
                'executed_block_hash',
                'executed_block_number',
                'executed_log_index',
                'has_error_token_receiver_events',
                'error_data',
            ]
            has_changes = False
            for field in compared_fields:
                dto_value = getattr(transfer_dto, field)
                if dto_value != getattr(transfer, field):
                    has_changes = True
                    setattr(transfer, field, dto_value)
            if has_changes:
                logger.info('Updating transfer %s', transfer.transaction_id)
                transfer.updated_on = now
                updated += 1
        logger.info('Created %s, updated %s transfers', created, updated)
