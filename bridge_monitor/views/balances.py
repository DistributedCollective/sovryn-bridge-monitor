from dataclasses import dataclass
from decimal import Decimal
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
from bridge_monitor.business_logic.utils import (
    get_rsk_balance_from_db,
    get_web3,
    get_closest_block,
)
import bridge_monitor.views.sanity_check as sanity_check

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

    target_date = request.params.get("target_date", "")
    fetch_btc_from_api = False

    if target_date:
        target_date = datetime.fromisoformat(target_date).replace(
            hour=0, minute=0, second=0, tzinfo=timezone.utc
        )
    else:
        target_date = datetime.now(tz=timezone.utc)
        fetch_btc_from_api = True

    closest_rsk_block = get_closest_block(
        dbsession, chain_name, target_date
    ).block_number

    displays: List[BalanceDisplay] = []
    logger.info("Fetching balances for btc wallets")
    for wallet in btc_wallets:
        if RPC_URL is not None and fetch_btc_from_api:
            response = send_rpc_request(
                "getbalance", [], f"{RPC_URL}/wallet/{wallet.name}", id="getbalance"
            ).json()
        elif not fetch_btc_from_api:
            response = {"result": Decimal(0)}
        else:
            logger.error("No bitcoin rpc url specified")
            response = {"result": Decimal(0)}

        displays.append(
            BalanceDisplay(
                name=wallet.name,
                balance_db=get_btc_wallet_balance_at_date(
                    dbsession, wallet.name, target_date=target_date
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
                    target_time=target_date,
                ),
                balance_api=sanity_check.get_rsk_balance_at_block(
                    w3, to_checksum_address(address.address), closest_rsk_block
                )
                / Decimal(10) ** 18,
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
        "target_date": target_date,
    }


def get_btc_pending_tx_total(dbsession: Session, wallet_name: str) -> Decimal:
    total = dbsession.execute(
        select(func.sum(PendingBtcWalletTransaction.net_change)).where(
            PendingBtcWalletTransaction.wallet.has(name=wallet_name)
        )
    ).scalar()
    return total if total is not None else Decimal("0")
