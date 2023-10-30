from types import SimpleNamespace
from pyramid.view import view_config
from sqlalchemy.orm import Session
from sqlalchemy import func
from datetime import datetime, timezone
from dateutil.relativedelta import relativedelta
from urllib.parse import urlencode


from bridge_monitor.models.pnl import ProfitCalculation, PnLTransaction
from bridge_monitor.business_logic.key_value_store import KeyValueStore

@view_config(route_name='pnl', renderer='bridge_monitor:templates/pnl.jinja2')
def pnl(request):
    dbsession: Session = request.dbsession
    chain_env = request.registry.get('chain_env', 'mainnet')
    chain = f'rsk_{chain_env}'

    errors = []
    start = None
    end = None
    try:
        if start_str := request.params.get('start'):
            start = datetime.fromisoformat(start_str)
    except TypeError:
        errors.append('Invalid start date')
    try:
        if end_str := request.params.get('end'):
            end = datetime.fromisoformat(end_str)
    except TypeError:
        errors.append('Invalid end date')

    time_filter = []
    if start:
        time_filter.append(ProfitCalculation.timestamp >= start)
    if end:
        time_filter.append(ProfitCalculation.timestamp < end)

    calculations_by_service = dbsession.query(
        ProfitCalculation.service,
        func.sum(ProfitCalculation.volume_btc).label('volume_btc'),
        func.sum(ProfitCalculation.gross_profit_btc).label('gross_profit_btc'),
        func.sum(ProfitCalculation.cost_btc).label('cost_btc'),
        func.sum(ProfitCalculation.net_profit_btc).label('net_profit_btc'),
    ).filter(
        ProfitCalculation.config_chain == chain,
        *time_filter,
    ).group_by(
        ProfitCalculation.service,
    ).order_by(
        ProfitCalculation.service,
    ).all()

    earliest_fastbtc_in_timestamp = dbsession.query(
        func.min(ProfitCalculation.timestamp)
    ).filter(
        ProfitCalculation.config_chain == chain,
        ProfitCalculation.service == 'fastbtc_in',
    ).scalar()
    earliest_bidi_fastbtc_timestamp = dbsession.query(
        func.min(ProfitCalculation.timestamp)
    ).filter(
        ProfitCalculation.config_chain == chain,
        ProfitCalculation.service == 'bidi_fastbtc',
    ).scalar()
    earliest_timestamp = min(
        earliest_fastbtc_in_timestamp or datetime.max.replace(tzinfo=timezone.utc),
        earliest_bidi_fastbtc_timestamp or datetime.max.replace(tzinfo=timezone.utc),
    )

    time_filter_options = _get_time_filter_options(earliest_timestamp)

    totals = SimpleNamespace(
        service='TOTAL',
        volume_btc=sum(c.volume_btc for c in calculations_by_service),
        gross_profit_btc=sum(c.gross_profit_btc for c in calculations_by_service),
        cost_btc=sum(c.cost_btc for c in calculations_by_service),
        net_profit_btc=sum(c.net_profit_btc for c in calculations_by_service),
    )

    return {
        'by_service': calculations_by_service,
        'totals': totals,
        'time_filter_options': time_filter_options,
        'start': start,
        'end': end,
        'earliest_timestamps': {
            'fastbtc_in': earliest_fastbtc_in_timestamp,
            'bidi_fastbtc': earliest_bidi_fastbtc_timestamp,
        }
    }



def _get_time_filter_options(earliest_timestamp: datetime):
    current_timestamp = datetime.now(timezone.utc)
    time_filter_options = [
        {
            'label': 'ALL',
            'query': {},
        }
    ]
    while current_timestamp >= earliest_timestamp.replace(day=1, hour=0, minute=0, second=0, microsecond=0):
        start = current_timestamp.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        end = start + relativedelta(months=1)
        time_filter_options.append({
            'query': {
                'start': start.isoformat(),
                'end': end.isoformat(),
            },
            'label': start.strftime('%b %Y'),
        })
        current_timestamp -= relativedelta(months=1)
    return time_filter_options