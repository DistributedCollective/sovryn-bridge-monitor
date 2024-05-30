from dataclasses import dataclass
from decimal import Decimal
from enum import Enum
from typing import List
from datetime import datetime, timezone
import logging

from sqlalchemy.orm import Session
from sqlalchemy import select
from eth_utils import to_checksum_address
from pyramid.view import view_config

from bridge_monitor.models import BtcWallet, RskAddress

from bridge_monitor.rpc.rpc import (
    get_btc_wallet_balance_at_date,
    send_rpc_request,
    RPC_URL,
)
from bridge_monitor.business_logic.utils import get_rsk_balance_from_db, get_web3

logger = logging.getLogger(__name__)


class DisplayMethods(str, Enum):
    DB = "DB"
    API = "API"


@dataclass
class BalanceDisplay:
    name: str
    balance: Decimal
    chain_name: str
    method: DisplayMethods
    address: str = ""


@view_config(
    route_name="balances",
    renderer="bridge_monitor:templates/balances.jinja2",
)
def get_balances(request):

    dbsession: Session = request.dbsession
    # chain_env = request.registry.get("chain_env", "mainnet")
    # chain_name = f"rsk_{chain_env}"
    w3 = get_web3("local_node")
    btc_wallets = dbsession.execute(select(BtcWallet)).scalars().all()
    rsk_addresses = dbsession.execute(select(RskAddress)).scalars().all()

    displays: List[BalanceDisplay] = []
    logger.info("Fetching balances for btc wallets")
    for wallet in btc_wallets:

        displays.append(
            BalanceDisplay(
                name=wallet.name,
                balance=get_btc_wallet_balance_at_date(
                    dbsession, wallet.name, datetime.now(tz=timezone.utc)
                ),
                chain_name="btc",
                method=DisplayMethods.DB,
            )
        )

        response = send_rpc_request(
            "getbalance", [], f"{RPC_URL}/wallet/{wallet.name}", id="getbalance"
        ).json()
        displays.append(
            BalanceDisplay(
                name=wallet.name,
                balance=Decimal(str(response["result"])),
                chain_name="btc",
                method=DisplayMethods.API,
            )
        )
    logger.info("Fetching balances for rsk addresses")

    for address in rsk_addresses:
      
        displays.append(
            BalanceDisplay(
                name=address.name,
                balance=get_rsk_balance_from_db(
                    dbsession,
                    address=address.address,
                    target_time=datetime.now(tz=timezone.utc),
                ),
                chain_name="rsk",
                method=DisplayMethods.DB,
                address=address.address,
            )
        )

        displays.append(
            BalanceDisplay(
                name=address.name,
                balance=w3.eth.get_balance(to_checksum_address(address.address))
                / Decimal("1e18"),
                chain_name="rsk",
                method=DisplayMethods.API,
                address=address.address,
            )
        )
    for d in displays:
        d.balance = d.balance.normalize()

    return {
        "displays": displays,
        "display_methods": DisplayMethods,
    }
