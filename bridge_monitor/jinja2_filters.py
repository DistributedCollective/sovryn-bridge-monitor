from pyramid.config import Configurator
from markupsafe import Markup
from dotenv import load_dotenv
import os

load_dotenv()


def get_from_env(env_name, default="") -> str:
    return os.environ.get(env_name, default)


def explorer_tx_link(value, chain):
    explorer_url = _get_explorer_tx_url(chain, value)
    if not explorer_url:
        return value
    return Markup('<a href="%s" target="_blank">%s</a>') % (explorer_url, value)


def _get_explorer_tx_url(chain, tx_id):
    if chain == "bitcoin_mainnet":
        return f"https://www.blockchain.com/btc/tx/{tx_id}"
    elif chain == "bitcoin_testnet":
        return f"https://www.blockchain.com/btc-testnet/tx/{tx_id}"
    elif chain == "rsk_mainnet":
        return f"https://explorer.rsk.co/tx/{tx_id}"
    elif chain == "rsk_testnet":
        return f"https://explorer.testnet.rsk.co/tx/{tx_id}"
    return None


# used in replenisher template, could be refactored
def includeme(config: Configurator):
    # This must be deferred, see
    # https://docs.pylonsproject.org/projects/pyramid_jinja2/en/latest/api.html#pyramid_jinja2.get_jinja2_environment
    def setup_jinja2_environment():
        environment = config.get_jinja2_environment()
        environment.filters["explorer_tx_link"] = explorer_tx_link
        environment.filters["get_from_env"] = get_from_env

    config.action(None, setup_jinja2_environment, order=9999)
