import logging
import csv
import dataclasses
import json
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from types import SimpleNamespace
from typing import (
    Any,
    List,
    Literal,
    NamedTuple,
    Optional,
)

from dateutil.relativedelta import relativedelta
from eth_utils import to_checksum_address
from pyramid.httpexceptions import HTTPBadRequest
from pyramid.request import Request
from pyramid.response import Response
from pyramid.view import view_config
from sqlalchemy import func
from sqlalchemy.orm import Session, joinedload
from web3 import Web3
from web3.types import BlockData

from bridge_monitor.models.pnl import ProfitCalculation
from bridge_monitor.models.fastbtc_in import FastBTCInTransfer
from bridge_monitor.business_logic.utils import (
    get_closest_block,
    get_web3,
)

from .utils import parse_time_range


logger = logging.getLogger(__name__)


@dataclasses.dataclass
class SanityCheckRow:
    name: str
    start_balance: Decimal = Decimal(0)
    end_balance: Decimal = Decimal(0)
    manual_in: Decimal = Decimal(0)
    manual_out: Decimal = Decimal(0)


@dataclasses.dataclass
class PnlRow:
    name: str
    volume_btc: Decimal
    gross_profit_btc: Decimal
    cost_btc: Decimal
    net_profit_btc: Decimal


@dataclasses.dataclass
class TotalRow:
    name: str
    amount: Decimal
    type: Literal['cost', 'profit']


@view_config(route_name='sanity_check', renderer='bridge_monitor:templates/sanity_check.jinja2')
def sanity_check(request: Request):
    dbsession: Session = request.dbsession
    chain_env = request.registry.get('chain_env', 'mainnet')
    chain = f'rsk_{chain_env}'
    if chain != 'rsk_mainnet':
        return Response("sanity check is only available for rsk_mainnet")

    web3 = get_web3(chain)
    bidi_fastbtc_contract_address = to_checksum_address('0x1a8e78b41bc5ab9ebb6996136622b9b41a601b5c')
    fastbtc_in_contract_address = to_checksum_address('0xe43cafbdd6674df708ce9dff8762af356c2b454d')  # managedwallet

    start, end, errors, query_filters_by_model = parse_time_range(
        request=request,
        models=[ProfitCalculation],
        default='this_month',
    )

    start_block = get_closest_block(
        chain_name=chain,
        wanted_datetime=datetime(start.year, start.month, start.day),
    )
    end_block = get_closest_block(
        chain_name=chain,
        #wanted_datetime=datetime(end.year, end.month, end.day, 23, 59, 59, 999999),
        #not_before=True,
        wanted_datetime=datetime(end.year, end.month, end.day) + timedelta(days=1),
    )
    start_block_number = start_block['number']
    end_block_number = end_block['number']

    block_times = {
        'rsk': {
            'start': {
                'block_number': start_block['number'],
                'block_time': datetime.fromtimestamp(start_block['timestamp']),
            },
            'end': {
                'block_number': end_block['number'],
                'block_time': datetime.fromtimestamp(end_block['timestamp']),
            },
        }
    }

    # PnL:= user-fees - tx_cost - failing_tx_cost
    calculations_by_service = dbsession.query(
        ProfitCalculation.service,
        func.sum(ProfitCalculation.volume_btc).label('volume_btc'),
        func.sum(ProfitCalculation.gross_profit_btc).label('gross_profit_btc'),
        func.sum(ProfitCalculation.cost_btc).label('cost_btc'),
        func.sum(ProfitCalculation.net_profit_btc).label('net_profit_btc'),
    ).filter(
        ProfitCalculation.config_chain == chain,
        *query_filters_by_model[ProfitCalculation],
    ).group_by(
        ProfitCalculation.service,
    ).order_by(
        ProfitCalculation.service,
    ).all()

    pnl_rows = [
        PnlRow(
            name=service,
            volume_btc=volume_btc,
            gross_profit_btc=gross_profit_btc,
            cost_btc=cost_btc,
            net_profit_btc=net_profit_btc,
        )
        for service, volume_btc, gross_profit_btc, cost_btc, net_profit_btc in calculations_by_service
    ]

    rows = [
        SanityCheckRow(
            name='rsk_peg_in',
            start_balance=get_rsk_balance_at_block(web3, fastbtc_in_contract_address, start_block_number),
            end_balance=get_rsk_balance_at_block(web3, fastbtc_in_contract_address, end_block_number),
        ),
        SanityCheckRow(
            name='rsk_peg_out',
            start_balance=get_rsk_balance_at_block(web3, bidi_fastbtc_contract_address, start_block_number),
            end_balance=get_rsk_balance_at_block(web3, bidi_fastbtc_contract_address, end_block_number),
        ),
    ]
    print(rows)



    totals = {
        # PnL := user - fees - tx_cost - failing_tx_cost  (failing tx cost ignored)
        'pnl': sum(
            (r.net_profit_btc for r in pnl_rows),
            start=Decimal(0),
        ),
        # manual_out:= withdrawals for operation cost or payrolls
        'manual_out': sum(
            (r.manual_out for r in rows),
            start=Decimal(0),
        ),
        # manual_in:=deposits from xchequer or oder system components (eg watcher)
        'manual_in': sum(
            (r.manual_in for r in rows),
            start=Decimal(0),
        ),
        # Start/End_balance:= Btc_peg_in+Btc_peg_out+Rsk_peg_in+Rsk_peg_out+Btc_backup_wallet
        'start_balance': sum(
            (r.start_balance for r in rows),
            start=Decimal(0),
        ),
        'end_balance': sum(
            (r.end_balance for r in rows),
            start=Decimal(0),
        ),
        # Rsk_tx_cost:=federator_tx_cost peg_in + federator_tx_cost_peg_out
        # ignore for now
        'rsk_tx_cost': Decimal(0),
        # failing_tx_cost:=approx 10$ per day (paid by federator wallets, ignore for the moment)
    }
    sanity_check_formula = '{end_balance} - {start_balance} + {pnl} + {manual_in} - {manual_out} - {rsk_tx_cost}'
    sanity_check_expanded = sanity_check_formula.format(
        **totals,
    )
    # EVIL EVAL! :D
    sanity_check_value = eval(sanity_check_expanded)


    class JsonEncoder(json.JSONEncoder):
        def default(self, o):
            if isinstance(o, Decimal):
                return str(o)
            if isinstance(o, (datetime, date)):
                return o.isoformat()
            return super().default(o)

    return {
        'start': start,
        'end': end,
        'block_times': json.dumps(block_times, indent='  ', cls=JsonEncoder),
        'rows': rows,
        'pnl_rows': pnl_rows,
        'totals': totals,
        'totals_json': json.dumps(totals, indent='  ', cls=JsonEncoder),
        'sanity_check': {
            'formula': sanity_check_formula,
            'expanded': sanity_check_expanded,
            'value': sanity_check_value,
        }
    }


def get_rsk_balance_at_block(web3, address, block_number) -> Decimal:
    balance = web3.eth.get_balance(address, block_number)
    print(address, block_number, balance)
    return Decimal(balance) / Decimal(10) ** 18
