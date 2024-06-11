from dataclasses import dataclass
from decimal import Decimal
from enum import Enum
from typing import List
from datetime import datetime, timezone
import logging

from sqlalchemy.orm import Session
from sqlalchemy import select, func
from eth_utils import to_checksum_address
from pyramid.view import view_config

from bridge_monitor.models import BtcWallet, RskAddress, PendingBtcWalletTransaction

from bridge_monitor.rpc.rpc import (
    get_btc_wallet_balance_at_date,
    send_rpc_request,
    RPC_URL,
)
from bridge_monitor.business_logic.utils import get_rsk_balance_from_db, get_web3

logger = logging.getLogger(__name__)


@dataclass
class BalanceDisplay:
    name: str
    balance_api: Decimal
    balance_db: Decimal
    chain_name: str
    pending_total: Decimal = Decimal("0")
    address: str = ""


@view_config(
    route_name="balances",
    renderer="bridge_monitor:templates/balances.jinja2",
)
def get_balances(request):
    dbsession: Session = request.dbsession
    chain_env = request.registry.get("chain_env", "mainnet")
    chain_name = f"rsk_{chain_env}"
    w3 = get_web3(chain_name)
    btc_wallets = dbsession.execute(select(BtcWallet)).scalars().all()
    rsk_addresses = dbsession.execute(select(RskAddress)).scalars().all()

    displays: List[BalanceDisplay] = []
    logger.info("Fetching balances for btc wallets")
    for wallet in btc_wallets:
        if RPC_URL is not None:
            response = send_rpc_request(
                "getbalance", [], f"{RPC_URL}/wallet/{wallet.name}", id="getbalance"
            ).json()
        else:
            logger.error("No bitcoin rpc url specified")
            response = {"result": 0}
        displays.append(
            BalanceDisplay(
                name=wallet.name,
                balance_db=get_btc_wallet_balance_at_date(
                    dbsession, wallet.name, datetime.now(tz=timezone.utc)
                ),
                balance_api=Decimal(str(response["result"])),
                chain_name="btc",
                pending_total=get_btc_pending_tx_total(dbsession, wallet.name),
            )
        )

    logger.info("Fetching balances for rsk addresses")

    for address in rsk_addresses:
        displays.append(
            BalanceDisplay(
                name=address.name,
                balance_db=get_rsk_balance_from_db(
                    dbsession,
                    address=address.address,
                    target_time=datetime.now(tz=timezone.utc),
                ),
                balance_api=w3.eth.get_balance(to_checksum_address(address.address)) / Decimal("1e18"),
                chain_name="rsk",
                address=address.address,
            )
        )
    for d in displays:
        d.balance_api = d.balance_api.normalize()
        d.balance_db = d.balance_db.normalize()
        d.pending_total = d.pending_total.normalize()

    return {
        "displays": displays,
    }


def get_btc_pending_tx_total(dbsession: Session, wallet_name: str) -> Decimal:
    total = dbsession.execute(
        select(func.sum(PendingBtcWalletTransaction.net_change)).where(
            PendingBtcWalletTransaction.wallet.has(name=wallet_name)
        )
    ).scalar()
    return total if total is not None else Decimal("0")
