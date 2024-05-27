import dataclasses
import logging
from datetime import (
    datetime,
    timedelta,
    timezone,
)
from decimal import Decimal

from eth_utils import to_checksum_address
from pyramid.httpexceptions import HTTPBadRequest
from pyramid.request import Request
from pyramid.view import view_config
from sqlalchemy import func
from sqlalchemy.orm import Session

from bridge_monitor.business_logic.utils import (
    get_closest_block,
    get_web3,
)
from bridge_monitor.models.pnl import ProfitCalculation
from .utils import parse_time_range
from ..rpc.rpc import get_btc_wallet_balance_at_date
from ..business_logic.utils import get_rsk_manual_transfers, get_btc_manual_transfers

logger = logging.getLogger(__name__)


@dataclasses.dataclass
class PnlRow:
    name: str
    volume_btc: Decimal
    gross_profit_btc: Decimal
    cost_btc: Decimal
    net_profit_btc: Decimal


@view_config(
    route_name="sanity_check", renderer="bridge_monitor:templates/sanity_check.jinja2"
)
def sanity_check(request: Request):
    dbsession: Session = request.dbsession
    chain = get_chain(request)

    bidi_fastbtc_contract_address = to_checksum_address(
        "0x1a8e78b41bc5ab9ebb6996136622b9b41a601b5c"
    )
    fastbtc_in_contract_address = to_checksum_address(
        "0xe43cafbdd6674df708ce9dff8762af356c2b454d"
    )  # managedwallet

    start, end, errors = parse_time_range(
        request=request,
        models=[ProfitCalculation],
        default="this_month",
    )

    # PnL:= user-fees - tx_cost - failing_tx_cost
    pnl_rows = get_pnl_rows(
        dbsession=dbsession,
        chain=chain,
        start=start,
        end=end,
    )
    pnl_total = sum(
        (r.net_profit_btc for r in pnl_rows),
        start=Decimal(0),
    )
    ret = {
        "start": start,
        "end": end,
        "pnl_rows": pnl_rows,
    }
    if request.method == "POST":
        totals = {
            # PnL := user - fees - tx_cost - failing_tx_cost  (failing tx cost ignored)
            "pnl": pnl_total,
            # Start/End_balance:= Btc_peg_in+Btc_peg_out+Rsk_peg_in+Rsk_peg_out+Btc_backup_wallet
            "start_balance": sum(
                (
                    rsk_balance_at_time(
                        dbsession, start, bidi_fastbtc_contract_address, chain
                    )["balance"],
                    rsk_balance_at_time(
                        dbsession, start, fastbtc_in_contract_address, chain
                    )["balance"],
                    get_btc_wallet_balance_at_date(dbsession, "fastbtc-out", start),
                    get_btc_wallet_balance_at_date(dbsession, "fastbtc-in", start),
                    get_btc_wallet_balance_at_date(dbsession, "btc-backup", start),
                )
            ),
            "end_balance": sum(
                (
                    rsk_balance_at_time(
                        dbsession, end, bidi_fastbtc_contract_address, chain
                    )["balance"],
                    rsk_balance_at_time(
                        dbsession, end, fastbtc_in_contract_address, chain
                    )["balance"],
                    get_btc_wallet_balance_at_date(dbsession, "fastbtc-out", end),
                    get_btc_wallet_balance_at_date(dbsession, "fastbtc-in", end),
                    get_btc_wallet_balance_at_date(dbsession, "btc-backup", end),
                )
            ),
            # manual_out:= withdrawals for operation cost or payrolls
            "manual_out": Decimal("0"),
            # manual_in:=deposits from xchequer or other system components (eg watcher)
            "manual_in": Decimal("0"),
            # Rsk_tx_cost:=federator_tx_cost peg_in + federator_tx_cost_peg_out
            # ignore for now
            "rsk_tx_cost": Decimal(0),
            # failing_tx_cost:=approx 10$ per day (paid by federator wallets, ignore for the moment)
        }
        # calculating manual transfers after above to make sure btc wallet tx table is up to date
        manual_rsk_result = get_rsk_manual_transfers(
            dbsession, start_time=start, target_time=end
        )
        manual_btc_result = get_btc_manual_transfers(
            dbsession, start_time=start, target_time=end
        )
        totals["manual_out"] = (
            manual_btc_result["manual_out"] + manual_rsk_result["manual_out"]
        )

        totals["manual_in"] = (
            manual_btc_result["manual_in"] + manual_rsk_result["manual_in"]
        )
        for key, value in totals.items():
            logger.info("%s: %s", key, value)
        sanity_check_formula = "{end_balance} - {start_balance} - {pnl} - {manual_in} + {manual_out} + {rsk_tx_cost}"

        sanity_check_value = (
            totals["end_balance"]
            - totals["start_balance"]
            - totals["pnl"]
            - totals["manual_in"]
            + totals["manual_out"]
            + totals["rsk_tx_cost"]
        )
        logger.info("sanity check value: %s", sanity_check_value)
        ret.update(
            {
                "totals": totals,
                "sanity_check": {
                    "formula": sanity_check_formula,
                    "expanded_formula": sanity_check_formula.format(**totals),
                    "value": sanity_check_value,
                },
            }
        )
    return ret


def rsk_balance_at_time(
    dbsession: Session, time: datetime, address: str, chain_name: str = "rsk_mainnet"
):
    block = get_closest_block(
        chain_name=chain_name,
        wanted_datetime=time,
        dbsession=dbsession,
    )
    balance_wei = get_rsk_balance_at_block(
        web3=get_web3(chain_name),
        address=address,
        block_number=block["block_number"],
    )

    return {
        "block_number": block["block_number"],
        "block_time": block["timestamp"].isoformat(),
        "address": address,
        "balance_wei": balance_wei,
        "balance_decimal": format(balance_wei / Decimal(10) ** 18, ".6f"),
        "balance": balance_wei / Decimal(10) ** 18,
    }


def get_pnl_rows(
    *,
    dbsession: Session,
    chain: str,
    start: datetime,
    end: datetime,
):
    time_filter = []
    if start:
        time_filter.append(
            ProfitCalculation.timestamp
            >= datetime(start.year, start.month, start.day, tzinfo=timezone.utc)
        )
    if end:
        time_filter.append(
            ProfitCalculation.timestamp
            < datetime(end.year, end.month, end.day, tzinfo=timezone.utc)
            + timedelta(days=1)
        )

    calculations_by_service = (
        dbsession.query(
            ProfitCalculation.service,
            func.sum(ProfitCalculation.volume_btc).label("volume_btc"),
            func.sum(ProfitCalculation.gross_profit_btc).label("gross_profit_btc"),
            func.sum(ProfitCalculation.cost_btc).label("cost_btc"),
            func.sum(ProfitCalculation.net_profit_btc).label("net_profit_btc"),
        )
        .filter(
            ProfitCalculation.config_chain == chain,
            *time_filter,
        )
        .group_by(
            ProfitCalculation.service,
        )
        .order_by(
            ProfitCalculation.service,
        )
        .all()
    )

    return [
        PnlRow(
            name=service,
            volume_btc=volume_btc,
            gross_profit_btc=gross_profit_btc,
            cost_btc=cost_btc,
            net_profit_btc=net_profit_btc,
        )
        for service, volume_btc, gross_profit_btc, cost_btc, net_profit_btc in calculations_by_service
    ]


def get_rsk_balance_at_block(web3, address, block_number) -> int:
    balance = web3.eth.get_balance(address, block_number)
    logger.info(
        "rsk balance for %s at block %s: %s wei", address, block_number, balance
    )
    return balance


def get_chain(request: Request) -> str:
    chain_env = request.registry.get("chain_env", "mainnet")
    chain = f"rsk_{chain_env}"
    if chain != "rsk_mainnet":
        raise HTTPBadRequest("sanity check is only available for rsk_mainnet")
    return chain


def includeme(config):
    config.add_route("sanity_check", "/sanity-check/")
    config.add_route("rsk_balance_at_time", "/rsk-balance-at-time/")
