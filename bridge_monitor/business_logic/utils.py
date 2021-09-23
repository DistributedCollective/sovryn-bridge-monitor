"""Various web3"""
import functools
import json
import logging
import os
import sys
from datetime import datetime, timezone
from time import sleep
from typing import Any, Dict, List, Optional, Union

from eth_account.signers.local import LocalAccount
from eth_typing import AnyAddress
from eth_utils import to_checksum_address
from web3 import Web3
from web3.contract import Contract, ContractEvent
from web3.middleware import construct_sign_and_send_raw_middleware

THIS_DIR = os.path.dirname(__file__)
ABI_DIR = os.path.join(THIS_DIR, 'abi')
logger = logging.getLogger(__name__)

INFURA_API_KEY = os.environ.get('INFURA_API_KEY', 'INFURA_API_KEY_NOT_SET')
RPC_URLS = {
    'rsk_mainnet': 'https://mainnet.sovryn.app/rpc',
    'rsk_mainnet_iov': 'https://public-node.rsk.co',
    'bsc_mainnet': 'https://bsc-dataseed.binance.org/',
    'rsk_testnet': 'https://testnet2.sovryn.app/rpc',
    'bsc_testnet': 'https://data-seed-prebsc-1-s1.binance.org:8545/',
    'eth_mainnet': f'https://mainnet.infura.io/v3/{INFURA_API_KEY}',
    'eth_testnet_ropsten': f'https://ropsten.infura.io/v3/{INFURA_API_KEY}',
}


def get_web3(chain_name: str, *, account: Optional[LocalAccount] = None) -> Web3:
    try:
        rpc_url = RPC_URLS[chain_name]
    except KeyError:
        valid_chains = ', '.join(repr(k) for k in RPC_URLS.keys())
        raise LookupError(f'Invalid chain name: {chain_name!r}. Valid options: {valid_chains}')
    if 'INFURA_API_KEY_NOT_SET' in rpc_url:
        raise RuntimeError('please provide the enviroment var INFURA_API_KEY')
    web3 = Web3(Web3.HTTPProvider(rpc_url))
    if account:
        set_web3_account(
            web3=web3,
            account=account,
        )
    return web3


def set_web3_account(*, web3: Web3, account: LocalAccount) -> Web3:
    web3.middleware_onion.add(construct_sign_and_send_raw_middleware(account))
    web3.eth.default_account = account.address
    return web3


def enable_logging():
    root = logging.getLogger()
    root.setLevel(logging.NOTSET)
    formatter = logging.Formatter('%(asctime)s - %(name)s [%(levelname)s] %(message)s')

    error_handler = logging.StreamHandler(sys.stderr)
    error_handler.setLevel(logging.WARNING)
    error_handler.setFormatter(formatter)
    root.addHandler(error_handler)

    info_handler = logging.StreamHandler(sys.stdout)
    info_handler.setLevel(logging.INFO)
    info_handler.setFormatter(formatter)
    root.addHandler(info_handler)


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def load_abi(name: str) -> List[Dict[str, Any]]:
    abi_path = os.path.join(ABI_DIR, f'{name}.json')
    assert os.path.abspath(abi_path).startswith(os.path.abspath(ABI_DIR))
    with open(abi_path) as f:
        return json.load(f)


def to_address(a: Union[bytes, str]) -> AnyAddress:
    # Web3.py expects checksummed addresses, but has no support for EIP-1191,
    # so RSK-checksummed addresses are broken
    # Should instead fix web3, but meanwhile this wrapper will help us
    return to_checksum_address(a)


ERC20_ABI = load_abi('IERC20')


@functools.lru_cache()
def get_erc20_contract(*, token_address: Union[str, AnyAddress], web3: Web3) -> Contract:
    return web3.eth.contract(
        address=to_address(token_address),
        abi=ERC20_ABI,
    )


def get_events(
    *,
    event: ContractEvent,
    from_block: int,
    to_block: int,
    batch_size: int = 100
):
    """Load events in batches"""
    if to_block < from_block:
        raise ValueError(f'to_block {to_block} is smaller than from_block {from_block}')

    logger.info('fetching events from %s to %s with batch size %s', from_block, to_block, batch_size)
    ret = []
    batch_from_block = from_block
    while batch_from_block <= to_block:
        batch_to_block = min(batch_from_block + batch_size, to_block)
        logger.info('fetching batch from %s to %s (up to %s)', batch_from_block, batch_to_block, to_block)

        events = get_event_batch_with_retries(
            event=event,
            from_block=batch_from_block,
            to_block=batch_to_block,
        )
        if len(events) > 0:
            logger.info(f'found %s events in batch', len(events))
        ret.extend(events)
        batch_from_block = batch_to_block + 1
    logger.info(f'found %s events in total', len(ret))
    return ret


def get_event_batch_with_retries(event, from_block, to_block, *, retries=3):
    while True:
        try:
            return event.getLogs(
                fromBlock=from_block,
                toBlock=to_block,
            )
        except ValueError as e:
            if retries <= 0:
                raise e
            logger.warning('error in get_all_entries: %s, retrying (%s)', e, retries)
            retries -= 1


def exponential_sleep(attempt, max_sleep_time=256.0):
    sleep_time = min(2 ** attempt, max_sleep_time)
    sleep(sleep_time)


def retryable(*, max_attempts: int = 10):
    def decorator(func):
        @functools.wraps(func)
        def wrapped(*args, **kwargs):
            attempt = 0
            while True:
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    if attempt >= max_attempts:
                        logger.warning('max attempts (%s) exchusted for error: %s', max_attempts, e)
                        raise
                    logger.warning(
                        'Retryable error (attempt: %s/%s): %s',
                        attempt + 1,
                        max_attempts,
                        e,
                    )
                    exponential_sleep(attempt)
                    attempt += 1
        return wrapped
    return decorator


@functools.lru_cache()
def is_contract(*, web3: Web3, address: str) -> bool:
    code = web3.eth.get_code(to_address(address))
    return code != b'\x00'
