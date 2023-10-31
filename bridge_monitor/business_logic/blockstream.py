import logging
import requests
from .utils import retryable

logger = logging.getLogger(__name__)


@retryable(max_attempts=5, exceptions=(requests.HTTPError,))
def get(*parts, testnet):
    if testnet:
        base_url = "https://blockstream.info/testnet/api/"
    else:
        base_url = "https://blockstream.info/api/"
    api_url = base_url + "/".join(str(part) for part in parts)
    logger.debug("GET %s", api_url)
    response = requests.get(api_url)
    response.raise_for_status()
    return response.json()


def get_transaction(tx_id, *, testnet):
    return get("tx", tx_id, testnet=testnet)

def get_address(address, *, testnet):
    return get("address", address, testnet=testnet)


def get_confirmed_transactions_page(address, *, testnet, last_seen_txid=None):
    parts = ["address", address, "txs", "chain"]
    if last_seen_txid:
        parts.append(last_seen_txid)
    return get(*parts, testnet=testnet)


def get_confirmed_transactions(address, *, testnet, before_txid=None, after_txid=None):
    """
    Yield transactions of address, newest first, until after_txid is found.
    """
    while True:
        transactions = get_confirmed_transactions_page(
            address=address,
            testnet=testnet,
            last_seen_txid=before_txid,
        )

        if not transactions:
            return

        for tx in transactions:
            if after_txid is not None and tx['txid'] == after_txid:
                return
            yield tx
            before_txid = tx['txid']
