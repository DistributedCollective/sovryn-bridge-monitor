import dataclasses
import logging
from datetime import (
    datetime,
    timedelta,
    timezone,
)
from decimal import Decimal
from typing import (
    Optional,
)

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
from ..business_logic.utils import update_chain_info_rsk
from ..rpc.rpc import get_btc_wallet_balance_at_date

logger = logging.getLogger(__name__)


@dataclasses.dataclass
class PnlRow:
    name: str
    volume_btc: Decimal
    gross_profit_btc: Decimal
    cost_btc: Decimal
    net_profit_btc: Decimal


@dataclasses.dataclass
class FormVariable:
    name: str
    title: str
    value: Optional[Decimal]
    value_getter_url: Optional[str] = None
    help_text: Optional[str] = None

    @classmethod
    def from_params(
        cls,
        *,
        params: dict,
        name: str,
        title: Optional[str] = None,
        help_text: Optional[str] = None,
        value_getter_url: Optional[str] = None,
        default=None,
    ):
        if default is not None:
            default = Decimal(default)
        if not title:
            title = name
        value = params.get(name, default)
        if value is None or value == "":
            value = None
        else:
            value = Decimal(value)
        return cls(
            name=name,
            title=title,
            value=value,
            value_getter_url=value_getter_url,
            help_text=help_text,
        )


# @view_config(route_name='sanity_check_new', renderer='bridge_monitor:templates/sanity_check.jinja2')
def new_sanity_check(request: Request):
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

        def getval(name):
            raise NotImplementedError

        totals = {
            # PnL := user - fees - tx_cost - failing_tx_cost  (failing tx cost ignored)
            "pnl": pnl_total,
            # manual_out:= withdrawals for operation cost or payrolls
            "manual_out": getval("manual_out"),
            # manual_in:=deposits from xchequer or other system components (eg watcher)
            "manual_in": getval("manual_in"),
            # Start/End_balance:= Btc_peg_in+Btc_peg_out+Rsk_peg_in+Rsk_peg_out+Btc_backup_wallet
            "start_balance": sum(
                (
                    rsk_balance_at_time(
                        dbsession, start, bidi_fastbtc_contract_address, chain
                    )["balance_decimal"],
                    rsk_balance_at_time(
                        dbsession, start, fastbtc_in_contract_address, chain
                    )["balance_decimal"],
                    get_btc_wallet_balance_at_date(dbsession, "fastbtc-out", start),
                    get_btc_wallet_balance_at_date(dbsession, "fastbtc-in", start),
                    get_btc_wallet_balance_at_date(dbsession, "btc-backup", start),
                )
            ),
            "end_balance": sum(
                (
                    rsk_balance_at_time(
                        dbsession, end, bidi_fastbtc_contract_address, chain
                    )["balance_decimal"],
                    rsk_balance_at_time(
                        dbsession, end, fastbtc_in_contract_address, chain
                    )["balance_decimal"],
                    get_btc_wallet_balance_at_date(dbsession, "fastbtc-out", end),
                    get_btc_wallet_balance_at_date(dbsession, "fastbtc-in", end),
                    get_btc_wallet_balance_at_date(dbsession, "btc-backup", end),
                )
            ),
            # Rsk_tx_cost:=federator_tx_cost peg_in + federator_tx_cost_peg_out
            # ignore for now
            "rsk_tx_cost": Decimal(0),
            # failing_tx_cost:=approx 10$ per day (paid by federator wallets, ignore for the moment)
        }
        sanity_check_formula = "{end_balance} - {start_balance} + {pnl} + {manual_in} - {manual_out} - {rsk_tx_cost}"

        sanity_check_value = (
            totals["end_balance"]
            - totals["start_balance"]
            + totals["pnl"]
            + totals["manual_in"]
            - totals["manual_out"]
            - totals["rsk_tx_cost"]
        )
        ret.update(
            {
                "totals": totals,
                "sanity_check": {
                    "formula": sanity_check_formula,
                    "value": sanity_check_value,
                },
            }
        )
    return ret


@view_config(
    route_name="sanity_check", renderer="bridge_monitor:templates/sanity_check.jinja2"
)
def sanity_check(request: Request):
    dbsession: Session = request.dbsession
    chain = get_chain(request)
    update_chain_info_rsk(dbsession, chain)
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

    # variables
    form_variables = [
        # PnL := user - fees - tx_cost - failing_tx_cost  (failing tx cost ignored)
        FormVariable.from_params(
            params=request.params,
            name="pnl",
            default=pnl_total,
            help_text="FastBTC profit/loss (user - fees - tx_cost), calculated automatically",
        ),
        # manual_out:= withdrawals for operation cost or payrolls
        FormVariable.from_params(
            params=request.params,
            name="manual_out",
            help_text="withdrawals for operation cost or payrolls",
        ),
        # manual_in:=deposits from xchequer or oder system components (eg watcher)
        FormVariable.from_params(
            params=request.params,
            name="manual_in",
            help_text="deposits from xchequer or other system components (e.g. watcher)",
        ),
        # Start/End_balance:= Btc_peg_in+Btc_peg_out+Rsk_peg_in+Rsk_peg_out+Btc_backup_wallet
        # start
        FormVariable.from_params(
            params=request.params,
            name="start_balance_btc_peg_in",
        ),
        FormVariable.from_params(
            params=request.params,
            name="start_balance_btc_peg_out",
        ),
        FormVariable.from_params(
            params=request.params,
            name="start_balance_btc_backup_wallet",
        ),
        FormVariable.from_params(
            params=request.params,
            name="start_balance_rsk_peg_in",
            help_text=f"RSK balance of {fastbtc_in_contract_address} at {start}",
            value_getter_url=request.route_url(
                "rsk_balance_at_time",
                _query={
                    "address": fastbtc_in_contract_address,
                    "time": start.isoformat(),
                },
            ),
        ),
        FormVariable.from_params(
            params=request.params,
            name="start_balance_rsk_peg_out",
            help_text=f"RSK balance of {bidi_fastbtc_contract_address} at {start}",
            value_getter_url=request.route_url(
                "rsk_balance_at_time",
                _query={
                    "address": bidi_fastbtc_contract_address,
                    "time": start.isoformat(),
                },
            ),
        ),
        FormVariable.from_params(
            params=request.params,
            name="end_balance_btc_peg_in",
        ),
        FormVariable.from_params(
            params=request.params,
            name="end_balance_btc_peg_out",
        ),
        FormVariable.from_params(
            params=request.params,
            name="end_balance_btc_backup_wallet",
        ),
        FormVariable.from_params(
            params=request.params,
            name="end_balance_rsk_peg_in",
            help_text=f"RSK balance of {fastbtc_in_contract_address} at {end}",
            value_getter_url=request.route_url(
                "rsk_balance_at_time",
                _query={
                    "address": fastbtc_in_contract_address,
                    "time": end.isoformat(),
                },
            ),
        ),
        FormVariable.from_params(
            params=request.params,
            name="end_balance_rsk_peg_out",
            help_text=f"RSK balance of {bidi_fastbtc_contract_address} at {end}",
            value_getter_url=request.route_url(
                "rsk_balance_at_time",
                _query={
                    "address": bidi_fastbtc_contract_address,
                    "time": end.isoformat(),
                },
            ),
        ),
    ]
    names = [var.name for var in form_variables]
    assert len(set(names)) == len(form_variables), "duplicate form variable names"

    ret = {
        "start": start,
        "end": end,
        "pnl_rows": pnl_rows,
        "form_variables": form_variables,
    }

    if request.method == "POST":
        vars_by_name = {v.name: v for v in form_variables}

        def getval(name):
            value = vars_by_name[name].value
            if not value:
                return Decimal(0)
            return Decimal(value)

        totals = {
            # PnL := user - fees - tx_cost - failing_tx_cost  (failing tx cost ignored)
            "pnl": getval("pnl"),
            # manual_out:= withdrawals for operation cost or payrolls
            "manual_out": getval("manual_out"),
            # manual_in:=deposits from xchequer or other system components (eg watcher)
            "manual_in": getval("manual_in"),
            # Start/End_balance:= Btc_peg_in+Btc_peg_out+Rsk_peg_in+Rsk_peg_out+Btc_backup_wallet
            "start_balance": sum(
                getval(name) for name in names if name.startswith("start_balance_")
            ),
            "end_balance": sum(
                getval(name) for name in names if name.startswith("end_balance_")
            ),
            # Rsk_tx_cost:=federator_tx_cost peg_in + federator_tx_cost_peg_out
            # ignore for now
            "rsk_tx_cost": Decimal(0),
            # failing_tx_cost:=approx 10$ per day (paid by federator wallets, ignore for the moment)
        }
        sanity_check_formula = "{end_balance} - {start_balance} + {pnl} + {manual_in} - {manual_out} - {rsk_tx_cost}"
        sanity_check_expanded = sanity_check_formula.format(
            **totals,
        )
        # EVIL EVAL! :D
        sanity_check_value = eval(sanity_check_expanded)

        ret.update(
            {
                "totals": totals,
                "sanity_check": {
                    "formula": sanity_check_formula,
                    "expanded": sanity_check_expanded,
                    "value": sanity_check_value,
                },
            }
        )
    return ret


def rsk_balance_at_time(
    dbsession: Session, time: datetime, address: str, chain_name: str = "rsk_mainnet"
):
    time = datetime.fromisoformat(time)

    block = get_closest_block(
        chain_name=chain_name,
        wanted_datetime=datetime(time.year, time.month, time.day),
        dbsession=dbsession,
    )
    balance_wei = get_rsk_balance_at_block(
        web3=get_web3(chain_name),
        address=address,
        block_number=block["number"],
    )

    return {
        "block_number": block["number"],
        "block_time": datetime.fromtimestamp(
            block["timestamp"], timezone.utc
        ).isoformat(),
        "address": address,
        "balance_wei": balance_wei,
        "balance_decimal": format(balance_wei / Decimal(10) ** 18, ".6f"),
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
