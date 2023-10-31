import logging
import requests

logger = logging.getLogger(__name__)


def get(*parts, testnet):
    if testnet:
        base_url = "https://blockstream.info/testnet/api/"
    else:
        base_url = "https://blockstream.info/api/"
    api_url = base_url + "/".join(str(part) for part in parts)
    logger.debug("Getting bitcoin tx from %s", api_url)
    response = requests.get(api_url)
    response.raise_for_status()
    return response.json()


def get_transaction(tx_id, *, testnet):
    return get("tx", tx_id, testnet=testnet)