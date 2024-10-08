"""Various web3"""

from concurrent.futures import ThreadPoolExecutor
import functools
import json
import logging
import os
import sys
from datetime import datetime, timezone
from time import sleep
from typing import Any, Callable, Dict, List, Optional, Tuple, Type, Union
from decimal import Decimal

from eth_account.signers.local import LocalAccount
from eth_typing import AnyAddress
from eth_utils import to_checksum_address, is_checksum_address
from web3 import Web3
from web3.contract import Contract
from web3.middleware import construct_sign_and_send_raw_middleware, geth_poa_middleware
from web3.exceptions import MismatchedABI
from web3.types import BlockData
from sqlalchemy.orm import Session
from sqlalchemy.sql import func as sql_func
from sqlalchemy.sql.expression import select

from .retry_middleware import http_retry_request_middleware
from ..models.chain_info import BlockInfo, BlockChain
from ..models.rsk_transaction_info import RskTxTrace, RskAddressBookkeeper

THIS_DIR = os.path.dirname(__file__)
ABI_DIR = os.path.join(THIS_DIR, "abi")
logger = logging.getLogger(__name__)
OLDEST_RSK_BLOCK_NUMBER = 3175735
RSK_META_FETCHER_SHORT_DELAY = 2 * 60
RSK_META_FETCHER_LONG_DELAY = 10 * 60

INFURA_API_KEY = os.getenv("INFURA_API_KEY", "INFURA_API_KEY_NOT_SET")
RPC_URLS = {
    # NOTE: rsk-internal only works on sovryn machines -- use mainnet-dev for local dev
    'rsk_mainnet': os.getenv('RSK_NODE_URL', 'https://rsk-internal.sovryn.app/rpc'),
    #"rsk_mainnet": os.getenv("RSK_NODE_URL", "https://mainnet-dev.sovryn.app/rpc/"),
    "rsk_mainnet_iov": "https://public-node.rsk.co",
    "bsc_mainnet": os.getenv("BSC_NODE_URL", "https://bsc-dataseed1.binance.org/"),
    "rsk_testnet": "https://testnet.sovryn.app/rpc",
    #'bsc_testnet': 'https://bsc.sovryn.app/testnet',
    "bsc_testnet": "https://data-seed-prebsc-1-s1.binance.org:8545/",
    "eth_mainnet": os.getenv(
        "ETH_NODE_URL", f"https://mainnet.infura.io/v3/{INFURA_API_KEY}"
    ),
    "eth_testnet_ropsten": f"https://ropsten.infura.io/v3/{INFURA_API_KEY}",
    "eth_testnet": f"https://sepolia.infura.io/v3/{INFURA_API_KEY}",
    "local_node": "http://localhost:4444",
}


def get_web3(chain_name: str, *, account: Optional[LocalAccount] = None) -> Web3:
    try:
        rpc_url = RPC_URLS[chain_name]
    except KeyError:
        valid_chains = ", ".join(repr(k) for k in RPC_URLS.keys())
        raise LookupError(
            f"Invalid chain name: {chain_name!r}. Valid options: {valid_chains}"
        )
    if "INFURA_API_KEY_NOT_SET" in rpc_url:
        raise RuntimeError("please provide the enviroment var INFURA_API_KEY")
    web3 = Web3(Web3.HTTPProvider(rpc_url))
    if account:
        set_web3_account(
            web3=web3,
            account=account,
        )

    # Fix this
    # web3.exceptions.ExtraDataLengthError:
    # The field extraData is 97 bytes, but should be 32. It is quite likely that  you are connected to a POA chain.
    # Refer to http://web3py.readthedocs.io/en/stable/middleware.html#geth-style-proof-of-authority for more details.
    web3.middleware_onion.inject(geth_poa_middleware, layer=0)

    web3.middleware_onion.add(http_retry_request_middleware)

    return web3


def set_web3_account(*, web3: Web3, account: LocalAccount) -> Web3:
    web3.middleware_onion.add(construct_sign_and_send_raw_middleware(account))
    web3.eth.default_account = account.address
    return web3


def enable_logging():
    root = logging.getLogger()
    root.setLevel(logging.NOTSET)
    formatter = logging.Formatter("%(asctime)s - %(name)s [%(levelname)s] %(message)s")

    error_handler = logging.StreamHandler(sys.stderr)
    error_handler.setLevel(logging.WARNING)
    error_handler.setFormatter(formatter)
    root.addHandler(error_handler)

    info_handler = logging.StreamHandler(sys.stdout)
    info_handler.setLevel(logging.INFO)
    info_handler.setFormatter(formatter)
    root.addHandler(info_handler)


def load_abi(name: str) -> List[Dict[str, Any]]:
    abi_path = os.path.join(ABI_DIR, f"{name}.json")
    assert os.path.abspath(abi_path).startswith(os.path.abspath(ABI_DIR))
    with open(abi_path) as f:
        return json.load(f)


def to_address(a: Union[bytes, str]) -> AnyAddress:
    # Web3.py expects checksummed addresses, but has no support for EIP-1191,
    # so RSK-checksummed addresses are broken
    # Should instead fix web3, but meanwhile this wrapper will help us
    return to_checksum_address(a)


ERC20_ABI = load_abi("IERC20")


@functools.lru_cache()
def get_erc20_contract(
    *, token_address: Union[str, AnyAddress], web3: Web3
) -> Type[Contract]:
    return web3.eth.contract(
        address=to_address(token_address),
        abi=ERC20_ABI,
    )


def get_events(*, event, from_block: int, to_block: int, batch_size: int = None):
    """Load events in batches"""
    if to_block < from_block:
        raise ValueError(f"to_block {to_block} is smaller than from_block {from_block}")

    if batch_size is None:
        batch_size = 100

    logger.info(
        "fetching events from %s to %s with batch size %s",
        from_block,
        to_block,
        batch_size,
    )
    ret = []
    batch_from_block = from_block
    while batch_from_block <= to_block:
        batch_to_block = min(batch_from_block + batch_size, to_block)
        logger.info(
            "fetching batch from %s to %s (up to %s)",
            batch_from_block,
            batch_to_block,
            to_block,
        )

        events = get_event_batch_with_retries(
            event=event,
            from_block=batch_from_block,
            to_block=batch_to_block,
        )
        if len(events) > 0:
            logger.info("found %s events in batch", len(events))
        ret.extend(events)
        batch_from_block = batch_to_block + 1
    logger.info("found %s events in total", len(ret))
    return ret


def get_all_contract_events(
    *,
    contract: Contract,
    from_block: int,
    to_block: int,
    web3: Web3,
    batch_size: int = None,
):
    """Get all events of a single contract"""
    if to_block < from_block:
        raise ValueError(f"to_block {to_block} is smaller than from_block {from_block}")

    if batch_size is None:
        batch_size = 100

    logger.info(
        "fetching events for %s from %s to %s with batch size %s",
        contract.address,
        from_block,
        to_block,
        batch_size,
    )

    ret = []
    batch_from_block = from_block
    while batch_from_block <= to_block:
        batch_to_block = min(batch_from_block + batch_size, to_block)
        logger.info(
            "fetching batch for %s from %s to %s (up to %s)",
            contract.address,
            batch_from_block,
            batch_to_block,
            to_block,
        )

        logs = get_log_batch_with_retries(
            contract_address=contract.address,
            web3=web3,
            from_block=batch_from_block,
            to_block=batch_to_block,
        )
        if len(logs) > 0:
            logger.info("found %s events in batch", len(logs))
            parsed_events = []
            for log in logs:
                parsed = None
                for event in contract.events:
                    try:
                        parsed = event().process_log(log)
                        if parsed is not None:
                            break
                    except MismatchedABI:
                        pass
                if not parsed:
                    raise ValueError(
                        f"could not parse event {log} for contract {contract.address}"
                    )
                parsed_events.append(parsed)
            ret.extend(parsed_events)
        batch_from_block = batch_to_block + 1
    logger.info("found %s events in total", len(ret))
    return ret


def get_event_batch_with_retries(event, from_block, to_block, *, retries=6):
    original_retries = retries
    while True:
        try:
            return event.get_logs(
                fromBlock=from_block,
                toBlock=to_block,
            )
        except ValueError as e:
            if retries <= 0:
                raise e
            logger.warning("error in get_all_entries: %s, retrying (%s)", e, retries)
            retries -= 1
            attempt = original_retries - retries
            exponential_sleep(attempt)


def get_log_batch_with_retries(
    web3: Web3, contract_address: str, from_block, to_block, *, retries=6
):
    original_retries = retries
    while True:
        try:
            return web3.eth.get_logs(
                dict(
                    address=contract_address,
                    fromBlock=from_block,
                    toBlock=to_block,
                )
            )
        except ValueError as e:
            if retries <= 0:
                raise e
            logger.warning("error in web3.eth.get_logs: %s, retrying (%s)", e, retries)
            retries -= 1
            attempt = original_retries - retries
            exponential_sleep(attempt)


def exponential_sleep(attempt, max_sleep_time=512.0):
    sleep_time = min(2 ** (attempt + 2), max_sleep_time)
    sleep(sleep_time)


def retryable(
    *, max_attempts: int = 10, exceptions: Tuple[Type[Exception]] = (Exception,)
):
    def decorator(func):
        @functools.wraps(func)
        def wrapped(*args, **kwargs):
            attempt = 0
            while True:
                try:
                    return func(*args, **kwargs)
                except exceptions as e:
                    if attempt >= max_attempts:
                        logger.exception(
                            "max attempts (%s) exhausted for error: %s", max_attempts, e
                        )
                        raise
                    logger.warning(
                        "Retryable error (attempt: %s/%s): %s",
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
    return code != b"\x00" and code != b""


def call_sequentially(*funcs: Callable, retry: bool = False) -> List[Any]:
    res = []
    for func in funcs:
        if hasattr(func, "call"):
            res.append(func.call())
        else:
            res.append(func())
    return res


def call_concurrently(*funcs: Callable, retry: bool = False) -> List[Any]:
    def _call():
        futures = []
        with ThreadPoolExecutor() as executor:
            for func in funcs:
                if hasattr(func, "call"):
                    futures.append(executor.submit(func.call))
                else:
                    futures.append(executor.submit(func))
        return [f.result() for f in futures]

    if retry:
        _call = retryable()(_call)

    return _call()


def get_rsk_balance_from_db(
    dbsession: Session, *, address: str, target_time: datetime
) -> Decimal:
    logger.info("Getting balance for %s at %s, from db", address, target_time)
    target_block = get_closest_block(dbsession, "rsk_mainnet", target_time)

    if is_checksum_address(address):
        address = address.lower()

    address_bookkeeper = dbsession.execute(
        select(RskAddressBookkeeper).where(
            RskAddressBookkeeper.address.has(address=address)
        )
    ).scalar_one()
    if (
        address_bookkeeper.start < address_bookkeeper.lowest_scanned
        or address_bookkeeper.next_to_scan_high <= target_block.block_number
    ):
        logger.warning(
            "Address %s not fully scanned when querying balance at %s",
            address,
            target_time,
        )

    to_values = dbsession.execute(
        select(sql_func.sum(RskTxTrace.value)).where(
            RskTxTrace.to_address == address,
            RskTxTrace.error.is_(None),
            RskTxTrace.block_number <= target_block.block_number,
        )
    ).scalar()

    from_values = dbsession.execute(
        select(sql_func.sum(RskTxTrace.value)).where(
            RskTxTrace.from_address == address,
            RskTxTrace.error.is_(None),
            RskTxTrace.block_number <= target_block.block_number,
        )
    ).scalar()

    return to_values - from_values


def get_closest_block(
    dbsession: Session,
    chain_name: str,
    wanted_datetime: datetime,
    *,
    not_after: bool = True,
    allowed_diff_seconds: int = 10 * 60,
) -> BlockInfo:
    wanted_timestamp = int(wanted_datetime.timestamp())
    logger.debug("Wanted timestamp: %s", wanted_timestamp)

    block_chain_meta = (
        dbsession.query(BlockChain).filter(BlockChain.name == "rsk").scalar()
    )
    rsk_id = block_chain_meta.id
    if block_chain_meta is None:
        raise LookupError("Block chain meta not found")

    closest_block = dbsession.execute(
        select(BlockInfo)
        .where(
            BlockInfo.block_chain_id == rsk_id, BlockInfo.timestamp <= wanted_datetime
        )
        .order_by(BlockInfo.timestamp.desc())
        .limit(1)
    ).scalar_one_or_none()

    if closest_block is not None:
        if (
            abs(closest_block.timestamp.timestamp() - wanted_timestamp)
            <= allowed_diff_seconds
        ):
            return closest_block
        # else attempt to get better block from by using web3
    web3 = get_web3(chain_name)
    end_block_number = web3.eth.block_number

    start_block_number = 1
    logger.debug("Bisecting between %s and %s", start_block_number, end_block_number)
    closest_diff = 2**256 - 1
    while start_block_number <= end_block_number:
        target_block_number = (start_block_number + end_block_number) // 2
        block: BlockData | BlockInfo = web3.eth.get_block(target_block_number)
        block_timestamp = block["timestamp"]

        block = BlockInfo(
            block_number=block["number"],
            timestamp=datetime.fromtimestamp(block["timestamp"], timezone.utc),
            block_chain_id=-1,
        )

        diff = block_timestamp - wanted_timestamp
        logger.debug(
            "target: %s, timestamp: %s, diff %s",
            target_block_number,
            block_timestamp,
            diff,
        )

        # Only update block when diff actually gets lower
        # This is only necessary in the last steps of the bisect, but we might as well do it every round
        if abs(diff) < closest_diff:
            closest_diff = abs(diff)
            closest_block = block

        if block_timestamp > wanted_timestamp:
            # block is after wanted, move end
            end_block_number = block["block_number"] - 1
        elif block_timestamp < wanted_timestamp:
            # block is before wanted, move start
            start_block_number = block["block_number"] + 1
        else:
            # timestamps are exactly the same, just return block
            return block

    if closest_block is None:
        raise LookupError(
            "Unable to determine block closest to " + wanted_datetime.isoformat()
        )

    logger.debug(
        "closest timestamp: %s, diff: %s",
        closest_block["timestamp"],
        closest_diff,
    )

    if not_after and closest_block["timestamp"] > wanted_datetime:
        logger.debug(
            "Block is after wanted timestamp and not_after=True, returning previous block"
        )
        prev_block = web3.eth.get_block(closest_block["block_number"] - 1)
        return BlockInfo(
            block_number=prev_block["number"],
            timestamp=datetime.fromtimestamp(prev_block["timestamp"]),
            block_chain_id=-1,
        )

    return closest_block
