from dataclasses import dataclass
from decimal import Decimal
from typing import List
from datetime import datetime

from sqlalchemy.orm import Session
from sqlalchemy import select
from eth_utils import to_checksum_address
from pyramid.view import view_config

from bridge_monitor.models import BtcWallet, RskAddress
from bridge_monitor.rpc.rpc import get_btc_wallet_balance_at_date, send_rpc_request, RPC_URL, RPC_USER, RPC_PASSWORD
from bridge_monitor.business_logic.utils import get_rsk_balance_from_db, get_web3


@dataclass
class BalanceDisplay:
    name: str
    balance: Decimal
    chain_name: str
    method: str         # "db" / "api"
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
    for wallet in btc_wallets:
        displays.append(BalanceDisplay(
            name=wallet.name,
            balance=get_btc_wallet_balance_at_date(dbsession, wallet.name, datetime.now()),
            chain_name="btc",
            method="db",
            )
        )

        response = send_rpc_request("getbalance", [], f"{RPC_URL}/wallet/{wallet.name}", id="getbalance").json()
        displays.append(BalanceDisplay(
            name=wallet.name,
            balance=Decimal(Decimal(response["result"]) / Decimal("1e8")),
            chain_name="btc",
            method="api",
            )
        )

    for address in rsk_addresses:
        displays.append(BalanceDisplay(
            name=address.name,
            balance=get_rsk_balance_from_db(dbsession, address=address.address, target_time=datetime.now()),
            chain_name="rsk",
            method="db",
            address=address.address,
            )
        )

        displays.append(BalanceDisplay(
            name=address.name,
            balance=w3.eth.get_balance(to_checksum_address(address.address)) / Decimal("1e18"),
            chain_name="rsk",
            method="api",
            address=address.address,
            )
        )

    return {
        "displays": displays,
    }
